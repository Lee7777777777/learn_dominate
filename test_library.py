import unittest
from pathlib import Path

from library import MapLibrary, THEMES
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


if __name__ == "__main__":
    unittest.main()
