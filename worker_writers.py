from pathlib import Path
from typing import List, Dict


async def send_writer_file(context, chat_id: int, writer) -> List[Dict[str, str]]:
    sent_files: List[Dict[str, str]] = []
    p = writer.paths[0]

    with p.open("rb") as f:
        msg = await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=p.name
        )

    if msg and msg.document:
        sent_files.append({
            "file_id": msg.document.file_id,
            "file_name": p.name
        })

    # удаляем сообщение с документом после получения file_id
    try:
        await msg.delete()
    except Exception:
        pass

    return sent_files


def cleanup_writer_files(writer):
    try:
        for p in getattr(writer, "paths", []):
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass