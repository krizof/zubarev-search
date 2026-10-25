"""Build one verified catalogue from a complete Telegram history snapshot."""
from collections import defaultdict, Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = "zubarefffwatch"
LABELS = r"(?:Краткое описание|Жанр|Режисс[её]р|В главных ролях|Страна|Продолжительность|(?:Рейтинг\s*)?Кинопоиск|IMDb|Оценк[ау] Зубарева|Приятного просмотра|Дата стрима|Дата\s*:|Лучшие Новости|ЛУЧШИЕ НОВОСТИ)"
GENRES = {"боевик": "Боевик", "приключения": "Приключения", "триллер": "Триллер", "детектив": "Детектив",
          "криминал": "Криминал", "фантастика": "Фантастика", "фэнтези": "Фэнтези", "ужасы": "Ужасы",
          "комедия": "Комедия", "драма": "Драма", "мультфильм": "Мультфильмы", "семейный": "Семейный",
          "мелодрама": "Мелодрама", "спорт": "Спорт", "военный": "Военный", "история": "История",
          "биография": "Биография", "мюзикл": "Мюзикл", "вестерн": "Вестерн", "документальный": "Документальный"}


def read(path, fallback):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def field(text, label):
    match = re.search(label + r"\s*:\s*(.*?)(?=\n|\s+" + LABELS + r"|$)", text, re.I)
    return match[1].strip() if match else ""


def number(text, label):
    match = re.search(label + r"\s*:?\s*(\d+(?:[.,]\d+)?)\s*/?\s*10?", text, re.I)
    return float(match[1].replace(",", ".")) if match else None


def parse_rating(raw):
    # Never turn an ambiguous 7–8/10 into a made-up precise rating.
    interval = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*/\s*10", raw)
    if interval:
        values = [float(x.replace(",", ".")) for x in interval.groups()]
        return None, values
    uncertain = re.search(r"(\d+(?:[.,]\d+)?),?\s+если(?:\s+даже)?\s+не\s+(\d+(?:[.,]\d+)?)\s*/\s*10", raw, re.I)
    if uncertain:
        return None, sorted(float(x.replace(",", ".")) for x in uncertain.groups())
    match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:/\s*10|из\s+10)", raw, re.I)
    if match:
        value = float(match[1].replace(",", "."))
        return (value if 0 <= value <= 11 else None), None
    return None, None


def stream_date(text):
    match = re.search(r"Дата(?:\s+стрима)?\s*[:;]\s*(\d{1,2})[/.:]([\w]+)[/.:](\d{2,4})", text, re.I)
    if not match:
        return None
    day, month, year = match.groups()
    months = {name: i for i, name in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
    month = month.lower().replace("м", "m")
    month = int(month) if month.isdigit() else months.get(month)
    try:
        return datetime(2000 + int(year) if len(year) == 2 else int(year), month, int(day), tzinfo=timezone.utc).date().isoformat()
    except (ValueError, TypeError):
        return None


def parse_meta(text, fallback=None):
    fallback = fallback or {}
    match = re.match(r'^\s*(?:Мультфильм|Фильм)\s*(["«“])', text, re.I)
    if match:
        closer = {'"': '"', "«": "»", "“": "”"}[match[1]]
        title = text[match.end():].splitlines()[0].split(closer, 1)[0].strip()
    else:
        title = fallback.get("title", "")
    kind = "animation" if text.lstrip().lower().startswith("мультфильм") else fallback.get("kind", "film")
    first = text.splitlines()[0].strip() if text.strip() else ""
    if not match:
        if re.match(r"(?:Мама|Беременна)\s+в\s+16", first, re.I):
            kind = "reality"
        elif re.match(r"Игра|The Last of Us|Uncharted", first, re.I):
            kind = "game"
        elif re.match(r"IRL|stream:|Баня|Гуляет|Чиловый|(?:Зубарев смотрит )?Страшные короткометражки|Аукцион", first, re.I):
            kind = "stream"
    if not title:
        first = text.splitlines()[0].strip() if text.strip() else ""
        if re.match(r"(?:Мама|Беременна)\s+в\s+16", first, re.I):
            kind = "reality"
        elif re.match(r"Игра|The Last of Us|Uncharted", first, re.I):
            kind = "game"
        elif re.match(r"IRL|stream:|Баня|Гуляет|Чиловый|(?:Зубарев смотрит )?Страшные короткометражки|Аукцион", first, re.I):
            kind = "stream"
        else:
            return None
        title = re.sub(r"\s*#(?:low|старый.*|новый.*)$", "", first).strip()
        if kind == "reality" and len(text.splitlines()) > 1:
            episode = text.splitlines()[1].strip()
            if re.search(r"сезон|серия|выпуск", episode, re.I):
                title += " · " + episode
    year = re.search(r"\((19\d{2}|20\d{2})\)", title)
    genre = field(text, "Жанр")
    if "мультфильм" in genre.lower():
        kind = "animation"
    raw = field(text, "Оценк[ау] Зубарева")
    score, score_range = parse_rating(raw)
    return {"title": title, "year": int(year[1]) if year else fallback.get("year"), "kind": kind,
            "description": field(text, "Краткое описание"), "genre": genre,
            "director": field(text, "Режисс[её]р"), "cast": field(text, "В главных ролях"),
            "country": field(text, "Страна"), "runtime": field(text, "Продолжительность"),
            "kp": number(text, "Кинопоиск"), "imdb": number(text, "IMDb"), "oz": raw,
            "score": score, "score_range": score_range,
            "guest": fallback.get("guest", ""), "stream_date": stream_date(text)}


def fingerprint(post):
    keys = ("text", "meta", "status", "message_ids", "bytes", "categories")
    return hashlib.sha256(json.dumps({k: post.get(k) for k in keys}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build(snapshot, legacy_posts, legacy_genres, previous=None, overrides=None):
    if snapshot.get("channel") != CHANNEL or snapshot.get("channel_id") != 3785873801:
        raise ValueError("Не тот канал. Обновление остановлено.")
    messages = snapshot.get("messages", [])
    if not snapshot.get("complete") or not messages or len({m['id'] for m in messages}) != len(messages):
        raise ValueError("История неполная или содержит дубли. Каталог не изменён.")
    old_items = previous.get("items", []) if previous else []
    # Protect against a partial export being mistaken for mass deletions.
    if previous and len(messages) < previous["stats"]["messages"] * .8:
        raise ValueError("Исчезло больше 20% истории. Нужна ручная проверка, каталог не изменён.")
    old_by = {p["id"]: p for p in old_items}
    legacy = {p["id"]: p for p in legacy_posts if p.get("meta", {}).get("title")}
    legacy.update(old_by)
    curated = defaultdict(set)
    for group in legacy_genres:
        if group["name"] == "Новинки и вне подборок":
            continue
        for item in group["items"]:
            if item.get("id"):
                curated[item["id"]].add(group["name"])
    grouped = defaultdict(list)
    by_id = {m["id"]: m for m in messages}
    for message in messages:
        grouped[message["album"] or str(message["id"])].append(message)
    items, review = [], []
    used = set()
    for group in grouped.values():
        group.sort(key=lambda m: m["id"])
        caption = next((m for m in group if m["text"] and (m["video"] or m["id"] in legacy)), None)
        if not caption:
            continue
        pid = caption["id"]
        old = legacy.get(pid, {})
        blocked = "copyright infringement" in caption["text"].lower()
        text = old.get("text", "") if blocked else caption["text"]
        override = (overrides or {}).get(str(pid))
        related = legacy.get(override["related_to"], {}) if override else {}
        meta = parse_meta(text, related.get("meta", {}) if override else old.get("meta", {}))
        if override and meta:
            related_meta = parse_meta(related.get("text", ""), related.get("meta", {}))
            if related_meta:
                meta = {**related_meta, "version": override["version"]}
        if not meta:
            if sum(m.get("duration") or 0 for m in group) >= 1200:
                review.append({"id": pid, "text": text[:200], "reason": "Длинное видео без распознанного названия"})
            continue
        live = [m for m in group if m["video"]]
        expected_ids = set(old.get("expected_message_ids", old.get("message_ids", []))) | {m["id"] for m in live}
        status = "blocked" if blocked else "available" if live else "unavailable"
        # A placeholder within known album boundaries proves one part is unavailable.
        gaps = [by_id.get(i) for i in range(group[0]["id"], group[-1]["id"] + 1)]
        if live and any(m and "copyright infringement" in m["text"].lower() for m in gaps):
            status = "partial"
        if live and expected_ids - {m["id"] for m in live}:
            status = "partial"
        categories = set(curated.get(pid, ()))
        if old.get("categories"):
            categories.update(old["categories"])
        categories.update(name for key, name in GENRES.items() if key in re.split(r"\s*,\s*", meta["genre"].lower()))
        if meta["kind"] == "animation":
            categories.add("Мультфильмы")
        special = {"reality": "Реалити-шоу", "game": "Игры", "stream": "Стримы и IRL"}
        if meta["kind"] in special:
            categories.add(special[meta["kind"]])
        items.append({"id": pid, "date": old.get("date") or caption["date"], "posted_at": caption["date"],
                      "edited_at": caption.get("edited_at"), "text": text, "meta": meta,
                      "categories": sorted(categories), "status": status,
                      "reason": "Ограничено Telegram по авторским правам" if blocked else "Часть записи недоступна" if status == "partial" else "Видео отсутствует в сообщении" if not live else "",
                      "message_ids": [m["id"] for m in live], "expected_message_ids": sorted(expected_ids), "parts": len(live),
                      "bytes": sum(m["bytes"] for m in live), "duration": round(sum(m.get("duration") or 0 for m in live)),
                      "url": f"https://t.me/{CHANNEL}/{pid}" if live else None})
        used.add(pid)
    # Retain known posts that disappeared entirely, including their last known metadata.
    for pid, old in legacy.items():
        if pid in used:
            continue
        if pid in by_id:
            raise ValueError(f"Не удалось распознать известную запись {pid}. Каталог не изменён.")
        meta = parse_meta(old["text"], old["meta"])
        items.append({**old, "meta": meta, "status": "deleted", "url": None, "message_ids": [], "parts": 0,
                      "bytes": 0, "duration": 0, "reason": "Запись удалена из канала", "categories": old.get("categories", sorted(curated[pid]))})
    items.sort(key=lambda p: p["id"], reverse=True)
    checked_at = snapshot["fetched_at"]
    baseline = old_by or {p["id"]: p for p in legacy_posts if p.get("meta", {}).get("title")}
    events = list(previous.get("changes", [])) if previous else []
    for post in items:
        prior = baseline.get(post["id"])
        event = None
        if not prior:
            event = "added"
        elif post["status"] != prior.get("status", "available"):
            event = "restored" if post["status"] == "available" else post["status"]
        elif old_by and fingerprint(prior) != fingerprint(post):
            event = "edited"
        if event:
            events.insert(0, {"id": post["id"], "type": event, "detected_at": checked_at,
                              "title": post["meta"]["title"], "reason": post["reason"]})
    events.sort(key=lambda e: (e["detected_at"], e["id"]), reverse=True)
    counts = Counter(p["status"] for p in items)
    stats = {"records": len(items), "available": counts["available"], "unavailable": len(items) - counts["available"],
             "films": sum(p["meta"]["kind"] in {"film", "animation"} for p in items),
             "unique_films": len({p["meta"]["title"] for p in items if p["meta"]["kind"] in {"film", "animation"}}),
             "streams": sum(p["meta"]["kind"] not in {"film", "animation"} for p in items),
             "messages": len(messages), "video_parts": sum(p["parts"] for p in items),
             "copyright_messages": sum("copyright infringement" in m["text"].lower() for m in messages),
             "bytes": sum(p["bytes"] for p in items), "duration": sum(p["duration"] for p in items),
             "statuses": dict(counts)}
    return {"schema": 1, "channel": CHANNEL, "channel_id": 3785873801, "checked_at": checked_at,
            "baseline_note": "Изменения относительно каталога от 2 октября 2026 года. Дата проверки не является датой удаления.",
            "stats": stats, "items": items, "changes": events[:1000], "review": review}


def main():
    snapshot = read(ROOT / ".local/channel.json", {})
    # Baselines remain local; the public catalogue stores only curated record information.
    baseline = ROOT / ".local/legacy-posts.json"
    if not baseline.exists():
        baseline.write_text(json.dumps(read(ROOT / "posts.json", []), ensure_ascii=False), encoding="utf-8")
    genres_baseline = ROOT / ".local/legacy-genres.json"
    if not genres_baseline.exists():
        genres_baseline.write_text(json.dumps(read(ROOT / "genres.json", []), ensure_ascii=False), encoding="utf-8")
    result = build(snapshot, read(baseline, []), read(genres_baseline, []), read(ROOT / "catalog.json", None),
                   read(ROOT / "metadata-overrides.json", {}))
    destination = ROOT / "catalog.json"
    tmp = destination.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(destination)
    # Keep older clients consistent with the same verified source, too.
    compatibility = {
        "posts.json": result["items"],
        "ratings.json": [{"id": p["id"], "title": p["meta"]["title"], "score": p["meta"]["score"],
                          "raw": p["meta"]["oz"], "date": p["date"][:10]}
                         for p in result["items"] if p["meta"]["score"] is not None and p["status"] == "available"],
        "genres.json": [{"name": name, "em": "", "cat": None,
                         "items": [{"id": p["id"], "t": p["meta"]["title"], "b": int(p["status"] != "available")}
                                   for p in result["items"] if name in p["categories"]]}
                        for name in sorted({c for p in result["items"] for c in p["categories"]})],
    }
    for name, value in compatibility.items():
        path = ROOT / name
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        temporary.replace(path)
    print(json.dumps(result["stats"], ensure_ascii=False, indent=2))
    print(f"На ручную проверку: {len(result['review'])}. Каталог обновлён.")


if __name__ == "__main__":
    main()
