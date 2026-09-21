import sqlite3
import unittest
from pathlib import Path

from library import DEFAULT_BORDER, DEFAULT_COLORS, MapLibrary, THEMES
from storage import Store
from test_support import TestDirectory


class LibraryTests(unittest.TestCase):
    def test_existing_data_new_blank_map_and_restart(self):
        with TestDirectory() as directory:
            original = Path(directory) / "learning_map.db"
            store = Store(original)
            store.seed_demo()
            old_data = store.snapshot()
            store.close()
            library = MapLibrary(original)
            try:
                self.assertEqual(library.path("default"), original.resolve())
                new_id = library.create("数学学习")
                other = Store(library.path(new_id))
                self.assertEqual(other.nodes(), [])
                self.assertEqual(other.edges(), [])
                other.create_node("新知识")
                other.restore(old_data)
                other.delete_node(1)
                other.close()
                store = Store(original)
                self.assertEqual(store.snapshot(), old_data)
                store.close()
                library.set_theme(new_id, THEMES[2])
                library.rename(new_id, "高等数学")
                library.activate(new_id)
            finally:
                library.close()
            library = MapLibrary(original)
            try:
                self.assertEqual(library.active_id, new_id)
                self.assertEqual(library.get(new_id)["title"], "高等数学")
                self.assertEqual(library.get(new_id)["theme"], THEMES[2])
                self.assertEqual(library.get("default")["theme"], THEMES[0])
            finally:
                library.close()

    def test_names_and_creation_rollback(self):
        with TestDirectory() as directory:
            library = MapLibrary(Path(directory) / "map.db")
            try:
                mid = library.create("Test")
                for title in ("", "  ", "test", "x" * 51):
                    with self.assertRaises(ValueError):
                        library.create(title)
                with self.assertRaises(ValueError):
                    library.rename(mid, "我的第一张地图")
                self.assertEqual(len(library.maps()), 2)
                self.assertEqual(library.active_id, "default")
                self.assertEqual(library.get(mid)["title"], "Test")
            finally:
                library.close()


    def test_kind_colours_survive_restart_and_migrate_older_catalogs(self):
        with TestDirectory() as directory:
            original = Path(directory) / "learning_map.db"
            catalog = original.with_suffix(".library.db")
            # A catalog written before content colours existed has no such column.
            db = sqlite3.connect(catalog)
            with db:
                db.execute("CREATE TABLE maps (id TEXT PRIMARY KEY, title TEXT NOT NULL UNIQUE, theme TEXT NOT NULL)")
                db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("INSERT INTO maps VALUES ('default','旧地图',?)", (THEMES[0],))
                db.execute("INSERT INTO settings VALUES ('active','default')")
            db.close()
            library = MapLibrary(original)
            try:
                self.assertEqual(library.kind_colors("default"), DEFAULT_COLORS)
                library.set_kind_colors("default", {"论文": "#123ABC"})
                colours = library.kind_colors("default")
                self.assertEqual(colours["论文"], "#123abc")
                self.assertEqual(colours["知识点"], DEFAULT_COLORS["知识点"])
                other = library.create("另一张地图")
                self.assertEqual(library.kind_colors(other), DEFAULT_COLORS)
                for bad in ({"论文": "red"}, {"小说": "#123456"}, {"论文": 1}):
                    with self.assertRaises(ValueError):
                        library.set_kind_colors(other, bad)
                self.assertEqual(library.kind_colors(other), DEFAULT_COLORS)
                with library.db:
                    library.db.execute("UPDATE maps SET colors='not json' WHERE id=?", (other,))
                self.assertEqual(library.kind_colors(other), DEFAULT_COLORS)
            finally:
                library.close()
            library = MapLibrary(original)
            try:
                self.assertEqual(library.kind_colors("default")["论文"], "#123abc")
                self.assertEqual(library.kind_colors(other), DEFAULT_COLORS)
                self.assertEqual(library.get(other)["title"], "另一张地图")
            finally:
                library.close()

    def test_border_width_defaults_migrates_and_rejects_junk(self):
        with TestDirectory() as directory:
            original = Path(directory) / "learning_map.db"
            catalog = original.with_suffix(".library.db")
            # A catalog written before appearance settings existed has neither column.
            db = sqlite3.connect(catalog)
            with db:
                db.execute("CREATE TABLE maps (id TEXT PRIMARY KEY, title TEXT NOT NULL UNIQUE, theme TEXT NOT NULL)")
                db.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("INSERT INTO maps VALUES ('default','旧地图',?)", (THEMES[0],))
                db.execute("INSERT INTO settings VALUES ('active','default')")
            db.close()
            library = MapLibrary(original)
            try:
                self.assertEqual([row[1] for row in library.db.execute("PRAGMA table_info(maps)")],
                                 ["id", "title", "theme", "colors", "border"])
                self.assertEqual(library.border_width("default"), DEFAULT_BORDER)
                for value in (1, 1.5, 3.0, 6):
                    library.set_border_width("default", value)
                    self.assertEqual(library.border_width("default"), float(value))
                for bad in (0.5, 6.5, 0, "3", None, True, float("nan"), float("inf")):
                    with self.assertRaises(ValueError):
                        library.set_border_width("default", bad)
                self.assertEqual(library.border_width("default"), 6.0)
                other = library.create("另一张地图")
                self.assertEqual(library.border_width(other), DEFAULT_BORDER)
                # Corrupt stored values fall back to the default instead of breaking drawing.
                for junk in ("wide", 99, -1):
                    with library.db:
                        library.db.execute("UPDATE maps SET border=? WHERE id=?", (junk, other))
                    self.assertEqual(library.border_width(other), DEFAULT_BORDER)
            finally:
                library.close()
            library = MapLibrary(original)
            try:
                self.assertEqual(library.border_width("default"), 6.0)
            finally:
                library.close()


if __name__ == "__main__":
    unittest.main()
