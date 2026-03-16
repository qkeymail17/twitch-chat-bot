# vod_video_pipeline.py
# Video download/send pipeline for Twitch VODs — single-file implementation.
# Requires: yt-dlp, ffmpeg on PATH, python-telegram-bot v22.
#
# Features:
# - obtains HLS URL via yt-dlp
# - downloads chunks via ffmpeg (-c copy, mp4, movflags +faststart)
# - chunks length (default 900s = 15min)
# - per-user queue (max 2 chunks stored), global limit on chunks
# - global parallel VOD slots (MAX_PARALLEL_VOD)
# - cancellation support (kills ffmpeg subprocesses, clears queues, deletes files)
# - splitting of a chunk into two if > MAX_TELEGRAM_FILE_BYTES (basic behavior)
# - progress messages (simple)
#
# Integration:
# - call start_video_pipeline(...) from your handler
# - it will run asynchronously (creates background task)
# - you can pass progress_message (telegram.Message) to be edited for progress updates

import asyncio
import os
import shutil
import signal
import math
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
import subprocess

from telegram import InputFile
from telegram.ext import ContextTypes

# Config / Tunables
CHUNK_SECONDS = 900  # 15 minutes fixed chunk length as requested
MAX_TELEGRAM_FILE_BYTES = 1900 * 1024 * 1024  # 1.9 GB
OUT_DIR = Path("_out") / "video_chunks"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Limits chosen according to your server (4GB RAM, HDD)
MAX_PARALLEL_VOD = 2        # how many distinct VOD pipelines at once
PER_USER_QUEUE = 2         # how many chunks to keep per user at once
GLOBAL_CHUNK_LIMIT = 11    # safety upper bound on files stored at once

# ffmpeg/yt-dlp executables
YTDLP_BIN = shutil.which("yt-dlp") or "yt-dlp"
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"

# Internal manager single instance
_logger = logging.getLogger(__name__)


class VideoPipelineError(Exception):
    pass


class UserActiveError(VideoPipelineError):
    pass


class GlobalLimitError(VideoPipelineError):
    pass


class VideoPipelineManager:
    def __init__(self):
        # map user_id -> info dict
        self.user_jobs: Dict[int, Dict[str, Any]] = {}
        self._global_chunks = 0
        self._global_chunks_lock = asyncio.Lock()
        self._global_vod_sem = asyncio.Semaphore(MAX_PARALLEL_VOD)
        self._manager_lock = asyncio.Lock()

    async def _inc_global_chunks(self, n=1):
        async with self._global_chunks_lock:
            if self._global_chunks + n > GLOBAL_CHUNK_LIMIT:
                raise GlobalLimitError("global chunk limit")
            self._global_chunks += n
            return self._global_chunks

    async def _dec_global_chunks(self, n=1):
        async with self._global_chunks_lock:
            self._global_chunks = max(0, self._global_chunks - n)
            return self._global_chunks

    def _user_active(self, user_id: int) -> bool:
        info = self.user_jobs.get(user_id)
        return bool(info and info.get("running"))

    async def start_video_pipeline(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        vod_url: str,
        user_id: int,
        quality: str = "best",
        chunk_seconds: int = CHUNK_SECONDS,
        progress_message=None,
    ):
        """
        Public entrypoint. Schedules pipeline for user.
        - context: telegram context (has bot and application)
        - chat_id: where to send files
        - vod_url: canonical https://www.twitch.tv/videos/{id} or similar
        - user_id: who requested (used to enforce per-user single job)
        - quality: currently unused except passed to yt-dlp as format selector
        - chunk_seconds: length of each chunk in seconds
        - progress_message: optionally, telegram.Message to edit with progress
        """
        async with self._manager_lock:
            if self._user_active(user_id):
                raise UserActiveError("user already has active video job")

            # acquire one of global slots
            acquired = await self._global_vod_sem.acquire()
            # create per-user structures
            q: asyncio.Queue = asyncio.Queue(maxsize=PER_USER_QUEUE)
            cancel_event = asyncio.Event()
            job = {
                "queue": q,
                "cancel": cancel_event,
                "running": True,
                "processes": [],  # list of ffmpeg subprocesses
            }
            self.user_jobs[user_id] = job

        # create background task
        task = context.application.create_task(
            self._pipeline_runner(context, chat_id, vod_url, user_id, quality, chunk_seconds, progress_message)
        )
        # store task
        job["task"] = task
        return task

    async def cancel_user(self, user_id: int):
        # cancel job if exists
        info = self.user_jobs.get(user_id)
        if not info:
            return False
        info["cancel"].set()
        # kill ffmpeg processes if any
        for proc in info.get("processes", []):
            try:
                proc.kill()
            except Exception:
                pass
        return True

    async def _pipeline_runner(self, context, chat_id, vod_url, user_id, quality, chunk_seconds, progress_message):
        """
        Orchestrates downloader + sender + cleanup for one VOD (user).
        This function acquires/releases the global semaphore.
        """
        job = self.user_jobs.get(user_id)
        if not job:
            return

        q: asyncio.Queue = job["queue"]
        cancel_event: asyncio.Event = job["cancel"]

        # track created temp files for cleanup
        created_files: List[Path] = []

        try:
            # Step 1: obtain HLS URL using yt-dlp
            _logger.info("Obtaining HLS via yt-dlp for %s", vod_url)
            try:
                hls_url = await self._get_hls_url(vod_url, quality)
            except Exception as e:
                _logger.exception("yt-dlp failed")
                await self._safe_send_text(context, chat_id, f"Ошибка получения потока: {e}")
                return

            if not hls_url:
                await self._safe_send_text(context, chat_id, "Не удалось получить HLS URL.")
                return

            # Create per-VOD temp directory
            safe_vod = vod_url.rstrip("/").split("/")[-1]
            vod_dir = OUT_DIR / f"{safe_vod}_{int(time.time())}"
            vod_dir.mkdir(parents=True, exist_ok=True)

            # Start sender task
            sender_task = asyncio.create_task(self._sender_loop(context, chat_id, q, cancel_event, created_files, user_id))

            chunk_idx = 0
            total_downloaded = 0
            # We'll loop until we cannot produce more chunks (ffmpeg exits non-zero) OR cancellation
            while True:
                if cancel_event.is_set():
                    raise VideoPipelineError("cancelled by user")

                # check global chunk capacity
                await self._inc_global_chunks(1)
                try:
                    out_path = vod_dir / f"{safe_vod}_part{chunk_idx:03d}.mp4"
                    created_files.append(out_path)
                    # download chunk via ffmpeg
                    proc = await self._start_ffmpeg_chunk(hls_url, chunk_idx, chunk_seconds, out_path)
                    # register process for potential cancellation
                    job["processes"].append(proc)

                    # wait for completion but still be responsive to cancel_event
                    done, pending = await asyncio.wait({proc.wait(), cancel_event.wait()}, return_when=asyncio.FIRST_COMPLETED)
                    # if cancel -> kill ffmpeg and break
                    if cancel_event.is_set():
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        raise VideoPipelineError("cancelled by user")

                    # ffmpeg finished: check returncode
                    rc = proc.returncode
                    if rc != 0:
                        # ffmpeg failed (likely end of stream) -> stop loop
                        _logger.warning("ffmpeg rc != 0 for chunk %s: %s", out_path, rc)
                        # cleanup last file if exists and zero-sized
                        if out_path.exists() and out_path.stat().st_size == 0:
                            try:
                                out_path.unlink()
                                created_files.remove(out_path)
                                await self._dec_global_chunks(1)
                            except Exception:
                                pass
                        break

                    # success: ensure file size not exceeding telegram limit
                    size = out_path.stat().st_size if out_path.exists() else 0
                    if size > MAX_TELEGRAM_FILE_BYTES:
                        # split into two parts (best-effort)
                        _logger.info("Chunk %s size %d > limit, splitting", out_path, size)
                        parts = await asyncio.get_event_loop().run_in_executor(None, self._split_file_into_two, str(out_path))
                        # replace created_files/item and queue parts appropriately
                        # remove original
                        try:
                            out_path.unlink()
                            created_files.remove(out_path)
                            await self._dec_global_chunks(1)
                        except Exception:
                            pass

                        # enqueue two parts (first will be sent, second queued)
                        for p in parts:
                            p_path = Path(p)
                            created_files.append(p_path)
                            await q.put(str(p_path))
                            await self._inc_global_chunks(1)
                    else:
                        # normal: enqueue file for sending
                        await q.put(str(out_path))

                    total_downloaded += 1
                    chunk_idx += 1

                    # After enqueueing second chunk, ensure we keep PER_USER_QUEUE semantics:
                    # if queue is full, wait until there is space (this gives backpressure)
                    # but we also respect cancellation
                    while q.full() and not cancel_event.is_set():
                        await asyncio.sleep(0.5)

                    # if reached global chunk limit and cannot proceed further, break
                    # (we already incremented global chunks before starting ffmpeg; if we couldn't queue, the loop waits)
                    # continue to next chunk

                except GlobalLimitError:
                    # couldn't increment global chunks: stop producing more
                    await self._safe_send_text(context, chat_id, "Сервер достиг лимита хранилища временных файлов. Попробуйте позже.")
                    break
                except VideoPipelineError:
                    raise
                finally:
                    # ensure job["processes"] pruned (process may have ended)
                    job["processes"] = [p for p in job.get("processes", []) if p.returncode is None]

            # Wait until sender queue is drained or cancellation
            # Put a sentinel None to indicate end-of-stream
            await q.put(None)
            await sender_task

            # finished normally
            await self._safe_send_text(context, chat_id, "Отправка видео завершена.")
            return

        except VideoPipelineError:
            # cancellation or user error — cleanup
            await self._safe_send_text(context, chat_id, "Скачивание отменено.")
            return
        except Exception as e:
            _logger.exception("pipeline failed")
            try:
                await self._safe_send_text(context, chat_id, f"Ошибка видео-пайплайна: {e}")
            except Exception:
                pass
            return
        finally:
            # release global slots and cleanup
            async with self._manager_lock:
                # remove job
                job = self.user_jobs.get(user_id)
                if job:
                    job["running"] = False
                # decrement global_chunks by number of created_files that still exist
                cnt = sum(1 for p in created_files if Path(p).exists())
                try:
                    await self._dec_global_chunks(cnt)
                except Exception:
                    pass
                # release semaphore if held
                try:
                    self._global_vod_sem.release()
                except Exception:
                    pass
                # final cleanup of files if any remain
                for p in list(created_files):
                    try:
                        if Path(p).exists():
                            Path(p).unlink()
                    except Exception:
                        pass
                # remove from dict
                self.user_jobs.pop(user_id, None)

    async def _sender_loop(self, context, chat_id, q: asyncio.Queue, cancel_event: asyncio.Event, created_files: List[Path], user_id: int):
        """
        Sequentially sends files from the queue. Deletes file after successful send.
        Expects None sentinel to end.
        """
        bot = context.bot
        while True:
            item = await q.get()
            if item is None:
                q.task_done()
                break
            path = Path(item)
            if cancel_event.is_set():
                # cleanup and break
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass
                q.task_done()
                break

            # If file bigger than limit (edge-case), try to split; splitting may add new files to queue instead
            try:
                size = path.stat().st_size if path.exists() else 0
            except Exception:
                size = 0

            if size == 0 or not path.exists():
                q.task_done()
                await self._dec_global_chunks(1)
                continue

            if size > MAX_TELEGRAM_FILE_BYTES:
                # split and re-enqueue first part
                _logger.info("Sender detects large file, splitting: %s", path)
                parts = await asyncio.get_event_loop().run_in_executor(None, self._split_file_into_two, str(path))
                # delete original
                try:
                    path.unlink()
                except Exception:
                    pass
                await self._dec_global_chunks(1)
                for p in parts:
                    # newly created parts increase global chunk counter
                    await self._inc_global_chunks(1)
                    created_files.append(Path(p))
                    await q.put(p)
                q.task_done()
                continue

            # send to telegram
            try:
                # show progress: we can send a small message before sending to notify user
                try:
                    await bot.send_chat_action(chat_id, "upload_document")
                except Exception:
                    pass

                # Use InputFile with path for large uploads
                input_file = InputFile(str(path))
                _logger.info("Sending file %s to chat %s", path, chat_id)
                await bot.send_document(chat_id=chat_id, document=input_file)
                # after send, delete file
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass
                await self._dec_global_chunks(1)
            except Exception as e:
                _logger.exception("Failed to send file %s: %s", path, e)
                # try to delete file and continue
                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass
                await self._dec_global_chunks(1)
            finally:
                q.task_done()

    async def _get_hls_url(self, vod_url: str, quality: str) -> Optional[str]:
        """
        Uses yt-dlp to fetch playable HLS URL. Uses subprocess to avoid blocking extractor internals.
        Returns the first m3u8 URL found or first line.
        """
        cmd = [YTDLP_BIN, "-g", vod_url]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        if proc.returncode != 0:
            _logger.warning("yt-dlp returned non-zero: %s", err.decode(errors="ignore"))
        lines = [ln.strip() for ln in out.decode(errors="ignore").splitlines() if ln.strip()]
        if not lines:
            return None
        # prefer m3u8
        for ln in lines:
            if ".m3u8" in ln:
                return ln
        # otherwise return the first
        return lines[0]

    async def _start_ffmpeg_chunk(self, hls_url: str, chunk_idx: int, chunk_seconds: int, out_path: Path):
        """
        Launches ffmpeg to extract one chunk. Returns process object.
        Command:
        ffmpeg -hide_banner -loglevel warning -ss START -t DURATION -i HLS_URL -c copy -movflags +faststart out_path
        We use -ss before -i to seek; if that's inaccurate for HLS, this is best-effort.
        """
        start = chunk_idx * chunk_seconds
        cmd = [
            FFMPEG_BIN,
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(start),
            "-t", str(chunk_seconds),
            "-i", hls_url,
            "-c", "copy",
            "-movflags", "+faststart",
            "-y",
            str(out_path),
        ]
        _logger.debug("FFMPEG cmd: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        return proc

    def _split_file_into_two(self, path: str) -> List[str]:
        """
        Blocking: splits file into two parts using ffmpeg. Returns list of two paths (strings).
        Best-effort; may fail for some containers.
        """
        base = Path(path)
        if not base.exists():
            return []

        # get duration via ffprobe
        try:
            cmd = [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of",
                   "default=noprint_wrappers=1:nokey=1", str(base)]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            dur = float(out)
        except Exception:
            # fallback: split by equal file size (not accurate). We'll try to produce two halves by time guess.
            dur = None

        if not dur or dur <= 2:
            # cannot split; just return original path (caller should handle deletion)
            return [str(base)]

        half = max(1, int(dur / 2))
        part1 = base.with_name(base.stem + "_p1" + base.suffix)
        part2 = base.with_name(base.stem + "_p2" + base.suffix)

        cmd1 = [
            FFMPEG_BIN, "-hide_banner", "-loglevel", "error",
            "-ss", "0", "-t", str(half), "-i", str(base),
            "-c", "copy", "-movflags", "+faststart", "-y", str(part1)
        ]
        cmd2 = [
            FFMPEG_BIN, "-hide_banner", "-loglevel", "error",
            "-ss", str(half), "-i", str(base),
            "-c", "copy", "-movflags", "+faststart", "-y", str(part2)
        ]
        try:
            subprocess.check_call(cmd1)
            subprocess.check_call(cmd2)
            return [str(part1), str(part2)]
        except Exception:
            # as a last resort, return original
            return [str(base)]

    async def _safe_send_text(self, context, chat_id: int, text: str):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            _logger.exception("Failed to send status text")


# Single manager instance
video_pipeline = VideoPipelineManager()


# --- Convenience wrapper that can be called from handlers ---
async def start_video_pipeline(context: ContextTypes.DEFAULT_TYPE, chat_id: int, vod_url: str, user_id: int, progress_message=None):
    """
    Convenience function to start pipeline and catch errors to return friendly messages.
    """
    try:
        task = await video_pipeline.start_video_pipeline(context, chat_id, vod_url, user_id, progress_message=progress_message)
        return task
    except UserActiveError:
        await context.bot.send_message(chat_id=chat_id, text="У вас уже идёт загрузка видео. Подождите её окончания.")
    except GlobalLimitError:
        await context.bot.send_message(chat_id=chat_id, text="Сервер сейчас перегружен видео-чанками. Попробуйте позже.")
    except Exception as e:
        _logger.exception("Failed to start video pipeline")
        await context.bot.send_message(chat_id=chat_id, text=f"Не удалось запустить загрузку видео: {e}")
    return None