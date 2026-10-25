import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("catalog_builder", ROOT / "scripts/build_catalog.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def message(pid=1, text='Фильм "Тест (2001)"', video=True, album=None):
    return dict(id=pid, text=text, video=video, album=album, bytes=20 if video else 0,
                duration=100, date="2026-10-25T10:00:00+00:00", edited_at=None)


def snapshot(messages):
    return dict(channel="zubarefffwatch", channel_id=3785873801, messages=messages,
                complete=True, fetched_at="2026-10-26T00:00:00+00:00")


class CatalogueTests(unittest.TestCase):
    def test_flattened_fields_do_not_leak(self):
        meta = b.parse_meta('Фильм "Тест (2001)" Краткое описание: Сюжет Жанр: драма, комедия Режиссер: Иван Иванов В главных ролях: Актёр Один Страна: США Кинопоиск: 7.5/10 IMDb: 6.4/10 Оценка Зубарева: 8/10 Приятного просмотра!')
        self.assertEqual(meta["genre"], "драма, комедия")
        self.assertEqual(meta["director"], "Иван Иванов")
        self.assertEqual(meta["cast"], "Актёр Один")
        self.assertEqual(meta["oz"], "8/10")
        self.assertEqual(meta["kp"], 7.5)

    def test_ranges_and_uncertain_scores(self):
        self.assertEqual(b.parse_rating("что-то 7-8/10"), (None, [7., 8.]))
        self.assertEqual(b.parse_rating("Твердая 8, если даже не 9/10."), (None, [8., 9.]))
        self.assertEqual(b.parse_rating("нравится"), (None, None))

    def test_open_quote_and_animation(self):
        meta=b.parse_meta('Фильм "Пол (2011)\nЖанр: мультфильм, комедия')
        self.assertEqual(meta["title"], "Пол (2011)")
        self.assertEqual(meta["kind"], "animation")
        nested=b.parse_meta('Фильм "007: Координаты «Скайфолл» (2012)"')
        self.assertEqual(nested["title"],'007: Координаты «Скайфолл» (2012)')
        self.assertEqual(nested["year"],2012)

    def test_album_is_one_record(self):
        data=b.build(snapshot([message(album="a"),message(2,"",album="a")]),[],[])
        self.assertEqual(len(data["items"]),1)
        self.assertEqual(data["items"][0]["parts"],2)

    def test_copyright_preserves_title_and_disables_link(self):
        old=[dict(id=1,text='Фильм "Тест (2001)"',meta=dict(title="Тест (2001)"))]
        data=b.build(snapshot([message(text="This message couldn't be displayed on your device due to copyright infringement.",video=False)]),old,[])
        post=data["items"][0]
        self.assertEqual(post["meta"]["title"],"Тест (2001)")
        self.assertEqual(post["status"],"blocked")
        self.assertIsNone(post["url"])
        self.assertEqual(data["changes"][0]["type"],"blocked")

    def test_removed_post_and_restoration(self):
        first=b.build(snapshot([message(),message(2,'Фильм "Другой (2002)"')]),[],[])
        # Keep overall history count so this exercises record deletion, not export protection.
        second=b.build(snapshot([message(3,"объявление",False),message(2,'Фильм "Другой (2002)"')]),[],[],first)
        deleted=next(p for p in second["items"] if p["id"]==1)
        self.assertEqual(deleted["status"],"deleted")
        third=b.build(snapshot([message(),message(2,'Фильм "Другой (2002)"')]),[],[],second)
        self.assertEqual(next(p for p in third["items"] if p["id"]==1)["status"],"available")
        self.assertIn("restored",[e["type"] for e in third["changes"]])

    def test_reality_type_and_change_history_stable_on_repeat(self):
        source=snapshot([message(text="Мама в 16\n6 сезон 3 серия")])
        first=b.build(source,[],[])
        second=b.build(source,[],[],first)
        self.assertEqual(second["items"][0]["meta"]["kind"],"reality")
        self.assertEqual(first["items"],second["items"])
        self.assertEqual(first["changes"],second["changes"])

    def test_partial_album(self):
        data=b.build(snapshot([message(album="a"),message(2,"copyright infringement",False),message(3,"",album="a")]),[],[])
        self.assertEqual(data["items"][0]["status"],"partial")

    def test_missing_last_part_stays_partial_until_restored(self):
        full=snapshot([message(album="a"),message(2,"",album="a"),message(3,"заметка",False)])
        first=b.build(full,[],[])
        missing=snapshot([message(album="a"),message(4,"заметка",False),message(3,"заметка",False)])
        second=b.build(missing,[],[],first)
        self.assertEqual(second["items"][0]["status"],"partial")
        third=b.build(missing,[],[],second)
        self.assertEqual(third["items"][0]["status"],"partial")
        self.assertEqual(first["items"][0]["expected_message_ids"],third["items"][0]["expected_message_ids"])
        restored=b.build(full,[],[],third)
        self.assertEqual(restored["items"][0]["status"],"available")

    def test_bad_snapshot_never_looks_like_deletions(self):
        for data in (snapshot([]),{**snapshot([message()]),"channel":"wrong"},{**snapshot([message()]),"complete":False}):
            with self.assertRaises(ValueError):b.build(data,[],[])
        first=b.build(snapshot([message(i,text=f'Фильм "Тест {i} (2001)"') for i in range(1,11)]),[],[])
        with self.assertRaises(ValueError):b.build(snapshot([message()]),[],[],first)

    def test_shipped_data_consistency(self):
        data=json.loads((ROOT/"catalog.json").read_text(encoding="utf-8"))
        items=data["items"]
        self.assertEqual(len({p["id"] for p in items}),len(items))
        self.assertEqual(len(items),data["stats"]["records"])
        self.assertEqual(sum(p["status"]=="available" for p in items),data["stats"]["available"])
        self.assertFalse(data["review"])
        for post in items:
            self.assertTrue(post["meta"]["title"])
            if post["status"]=="available":self.assertEqual(post["url"],f'https://t.me/zubarefffwatch/{post["id"]}')
            if post["status"] in {"blocked","deleted"}:self.assertIsNone(post["url"])
            self.assertNotIn("Режиссер:",post["meta"]["genre"])
        self.assertEqual(json.loads((ROOT/"posts.json").read_text(encoding="utf-8")),items)


if __name__ == "__main__":
    unittest.main()
