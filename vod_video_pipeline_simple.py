# vod_video_pipeline_simple.py
# Требует: yt-dlp и ffmpeg в PATH.
# Функция export: async def download_and_send(context, chat_id, progress_message_id, vod_url, vod_id, fmt)
# Поддерживает fmt == "vod_video". Проверяет is_cancelled(context) из handlers_state.
# Скачивает чанки по 20 минут, держит максимум 2 чанка на диске, параллельно отправляет в Telegram.
# По окончании возвращает (meta, stats, files, public_html_url) минимальные объекты, совместимые с _runner().

import os
import math
import tempfile
import shutil
import subprocess
import asyncio
from typing import Tuple, List, Dict, Any
from handlers_state import is_cancelled  # функция проекта
import shlex

CHUNK_MINUTES_DEFAULT = 20
QUEUE_MAX = 2


def _shquote(s: str) -> str:
    return shlex.quote(s)


def _run_blocking(cmd: str, cwd: str | None = None) -> Tuple[int, str]:
    """Запускается в executor — синхронный subprocess.run."""
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd)
    out = proc.stdout.decode(errors="replace")
    return proc.returncode, out


async def _probe_duration(loop, vod_url: str) -> float:
    cmd = f"yt-dlp -J {_shquote(vod_url)}"
    rc, out = await loop.run_in_executor(None, _run_blocking, cmd, None)
    if rc != 0:
        raise RuntimeError("yt-dlp probe failed:\n" + out[:1000])
    import json
    info = json.loads(out)
    duration = info.get("duration")
    if duration is None:
        ds = info.get("duration_string")
        if not ds:
            raise RuntimeError("Не удалось узнать длительность VOD")
        parts = list(map(int, ds.split(":")))
        duration = 0
        for p in parts:
            duration = duration * 60 + p
    return float(duration)


def _format_hhmmss(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _download_segment_blocking(vod_url: str, start_s: float, duration_s: float, out_path: str, work_dir: str) -> None:
    """Выполняется в executor. Использует yt-dlp --download-sections для точного выреза."""
    start = _format_hhmmss(start_s)
    end = _format_hhmmss(start_s + duration_s)
    out_template = out_path  # yt-dlp сам добавляет расширение, поэтому дальше проверяем
    cmd = (
        f'yt-dlp -f "bestvideo+bestaudio/best" -N 8 -o {_shquote(out_template)} '
        f'--remux-video mp4 --download-sections "*{start}-{end}" {_shquote(vod_url)}'
    )
    rc, out = _run_blocking(cmd, work_dir)
    if rc != 0:
        raise RuntimeError("yt-dlp failed: " + (out[:1000] if out else "no output"))
    # yt-dlp может записать файл с суффиксом; найдем файл, начинающийся с basename(out_path)
    if os.path.exists(out_path):
        return
    base = os.path.basename(out_path).split(".")[0]
    for p in os.listdir(work_dir):
        if p.startswith(base):
            candidate = os.path.join(work_dir, p)
            try:
                os.replace(candidate, out_path)
            except Exception:
                shutil.copy(candidate, out_path)
                os.remove(candidate)
            return
    raise RuntimeError("Не найден файл после yt-dlp для " + out_path)


async def download_and_send(context, chat_id: int, progress_message_id: int, vod_url: str, vod_id: str, fmt: str):
    """
    Основной вход для вызова из handlers_vod._runner.
    Работает только если fmt == "vod_video". В остальных случаях бросает RuntimeError.
    """
    if fmt != "vod_video":
        raise RuntimeError("vod_video_pipeline_simple: unsupported fmt")

    loop = asyncio.get_running_loop()
    # проверяем длительность
    duration = await _probe_duration(loop, vod_url)
    if duration <= 0:
        raise RuntimeError("CHAT_EMPTY")  # совместимость с ожиданиями _runner()
    chunk_seconds = CHUNK_MINUTES_DEFAULT * 60
    total_chunks = math.ceil(duration / chunk_seconds)

    work_dir = tempfile.mkdtemp(prefix="vod_chunks_")
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAX)
    sent_files: List[str] = []

    # downloader coroutine
    async def _downloader():
        try:
            for idx in range(total_chunks):
                if is_cancelled(context):
                    break
                # ensure queue has space (Queue.put will wait if full)
                start = idx * chunk_seconds
                this_duration = min(chunk_seconds, duration - start)
                out_name = os.path.join(work_dir, f"chunk_{idx:03d}.mp4")
                # download blocking in executor
                await loop.run_in_executor(None, _download_segment_blocking, vod_url, start, this_duration, out_name, work_dir)
                if is_cancelled(context):
                    # cleanup partial
                    try:
                        os.remove(out_name)
                    except Exception:
                        pass
                    break
                # put path into queue (will wait if full)
                await queue.put(out_name)
            # signal sender no more files
            await queue.put(None)  # sentinel
        except Exception as e:
            # on error, propagate by putting sentinel and re-raising
            try:
                await queue.put(None)
            except Exception:
                pass
            raise

    # sender coroutine
    async def _sender():
        while True:
            item = await queue.get()

            if item is None:
                queue.task_done()
                break

            if is_cancelled(context):
                try:
                    os.remove(item)
                except Exception:
                    pass
                queue.task_done()
                break

            try:
                with open(item, "rb") as f:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120
                    )
                sent_files.append(os.path.basename(item))
            finally:
                try:
                    os.remove(item)
                except Exception:
                    pass

            queue.task_done()

        return

    # run both coroutines concurrently
    try:
        dl_task = asyncio.create_task(_downloader())
        send_task = asyncio.create_task(_sender())

        await dl_task
        await send_task
        # if cancelled by flag -> raise
        if is_cancelled(context):
            raise RuntimeError("Загрузка была отменена.")
    except Exception as e:
        raise
    finally:
        # cleanup work_dir
        try:
            shutil.rmtree(work_dir)
        except Exception:
            pass

    # build minimal results for cache/runner compatibility
    meta: Dict[str, Any] = {"length_seconds": int(duration)}
    stats: Dict[str, Any] = {}
    files: List[str] = sent_files
    public_html_url = None
    return meta, stats, files, public_html_url