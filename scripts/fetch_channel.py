"""Read channel history using the existing local account. Never publishes messages.

The session key is read into memory; no credentials or Telegram session enter Git.
"""
import argparse
import asyncio
import configparser
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import MemorySession

ROOT = Path(__file__).resolve().parents[1]


async def fetch(config_path, session_path, channel):
    config = configparser.ConfigParser(interpolation=None)
    config.read(config_path, encoding="utf-8-sig")
    with sqlite3.connect(session_path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT dc_id, server_address, port, auth_key FROM sessions LIMIT 1").fetchone()
    if not row:
        raise RuntimeError("Сохранённая сессия Telegram пуста. Войди в Киноконвейер.")
    session = MemorySession()
    session.set_dc(*row[:3])
    session.auth_key = AuthKey(row[3])
    client = TelegramClient(session, config.getint("telegram", "api_id"),
                            config.get("telegram", "api_hash"), receive_updates=False)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Сессия Telegram требует входа через Киноконвейер.")
        entity = await client.get_entity(channel)
        if entity.username != channel.lstrip("@"):
            raise RuntimeError("Имя канала не совпало. Каталог не изменён.")
        messages = []
        async for message in client.iter_messages(entity):
            if getattr(message, "action", None):
                continue
            links = []
            for item in message.entities or []:
                if getattr(item, "url", None):
                    links.append(item.url)
            file = message.file
            messages.append({"id": message.id, "date": message.date.isoformat(),
                             "edited_at": message.edit_date.isoformat() if message.edit_date else None,
                             "text": message.message or "", "album": str(message.grouped_id) if message.grouped_id else None,
                             "video": bool(message.video), "photo": bool(message.photo),
                             "bytes": file.size if file else 0, "duration": file.duration if file else None,
                             "links": links})
            if len(messages) % 500 == 0:
                print(f"Прочитано сообщений: {len(messages)}", flush=True)
        if not messages:
            raise RuntimeError("Telegram вернул пустую историю. Каталог не изменён.")
        return {"channel": entity.username, "channel_id": entity.id, "title": entity.title,
                "fetched_at": datetime.now(timezone.utc).isoformat(), "complete": True,
                "messages": messages}
    finally:
        await client.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", default="zubarefffwatch")
    parser.add_argument("--config", type=Path, default=ROOT.parent / "ТГ_Загрузчик" / "config.ini")
    parser.add_argument("--session", type=Path, default=ROOT.parent / "ТГ_Загрузчик" / "session.session")
    args = parser.parse_args()
    result = asyncio.run(fetch(args.config, args.session, args.channel))
    destination = ROOT / ".local" / "channel.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Канал @{result['channel']}: {len(result['messages'])} сообщений. Снимок сохранён локально.")


if __name__ == "__main__":
    main()
