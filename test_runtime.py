import os
import unittest
from pathlib import Path
from unittest.mock import patch

from library import MapLibrary
from runtime import migrate_legacy, user_data_dir
from storage import Store
from test_support import TestDirectory


class RuntimeTests(unittest.TestCase):
    def test_packaged_data_does_not_depend_on_executable_version(self):
        with TestDirectory() as folder:
            with patch('runtime.sys.frozen', True, create=True), patch.dict(os.environ, LOCALAPPDATA=folder):
                with patch('runtime.sys.executable', str(Path(folder) / 'v1' / 'ZhiLu.exe')):
                    old = user_data_dir()
                with patch('runtime.sys.executable', str(Path(folder) / 'v2' / 'ZhiLu.exe')):
                    self.assertEqual(old, user_data_dir())
                self.assertEqual(old, Path(folder) / 'ZhiLu' / 'data')

    def test_migrate_all_maps_without_overwriting_or_removing_originals(self):
        with TestDirectory() as folder:
            source, target = Path(folder) / 'old', Path(folder) / 'new' / 'data'
            store = Store(source / 'learning_map.db')
            store.seed_demo()
            original = store.snapshot()
            store.close()
            library = MapLibrary(source / 'learning_map.db')
            mid = library.create('另一张地图')
            other = Store(library.path(mid))
            other.create_node('我的笔记', notes='不可以丢失')
            other.close()
            library.activate(mid)
            library.set_theme(mid, '午夜星空')
            library.close()
            self.assertTrue(migrate_legacy(source, target))
            migrated = MapLibrary(target / 'learning_map.db')
            try:
                self.assertEqual(migrated.active_id, mid)
                self.assertEqual(migrated.get(mid)['theme'], '午夜星空')
                other = Store(migrated.path(mid))
                self.assertEqual(other.nodes()[0]['notes'], '不可以丢失')
                other.close()
            finally:
                migrated.close()
            self.assertFalse(migrate_legacy(source, target))
            store = Store(source / 'learning_map.db')
            self.assertEqual(store.snapshot(), original)
            store.close()
