import copy
import json
import unittest
from pathlib import Path

from storage import Store
from test_support import TestDirectory


class StoreTests(unittest.TestCase):
    def test_create_connected_node_rolls_back_on_connection_failure(self):
        anchor = self.store.create_node("目标")
        self.store.db.execute("CREATE TRIGGER reject_edges BEFORE INSERT ON edges BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_connected_node(anchor, "before", "前置")
        self.assertEqual(len(self.store.nodes()), 1)
        self.assertEqual(self.store.edges(), [])

    def setUp(self):
        self.temp = TestDirectory()
        self.path = Path(self.temp.name) / "map.db"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_save_reopen_and_layout(self):
        a = self.store.create_node("概率", notes="条件概率\n中文笔记", resources="D:/论文/a.pdf")
        b = self.store.create_node("论文", kind="论文")
        self.store.add_edge(a, b, "前置依赖")
        self.store.update_node(a, state="已完成", mastery="熟练")
        self.store.layout()
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.node(a)["notes"], "条件概率\n中文笔记")
        self.assertEqual(self.store.node(a)["mastery"], "熟练")
        self.assertLess(self.store.node(a)["x"], self.store.node(b)["x"])
        self.assertEqual(len(self.store.edges()), 1)

    def test_dependency_cycle_and_other_relations(self):
        a, b, c = [self.store.create_node(n) for n in "ABC"]
        self.store.add_edge(a, b, "前置依赖")
        self.store.add_edge(b, c, "前置依赖")
        with self.assertRaisesRegex(ValueError, "循环"):
            self.store.add_edge(c, a, "前置依赖")
        self.store.add_edge(c, a, "进阶延伸")
        self.store.add_edge(b, a, "相关内容")
        with self.assertRaisesRegex(ValueError, "已经存在"):
            self.store.add_edge(a, b, "相关内容")
        with self.assertRaises(ValueError):
            self.store.add_edge(a, a, "前置依赖")
        with self.assertRaises(ValueError):
            self.store.add_edge(a, 999, "前置依赖")

    def test_delete_cascade_restore_and_export(self):
        self.store.seed_demo()
        snapshot = self.store.snapshot()
        path = Path(self.temp.name) / "地图.json"
        self.store.export(path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), snapshot)
        victim = snapshot["nodes"][2]["id"]
        self.store.delete_node(victim)
        self.assertFalse(any(victim in (e["source"], e["target"]) for e in self.store.edges()))
        self.store.restore(snapshot)
        self.assertEqual(self.store.snapshot(), snapshot)
        self.assertGreater(self.store.create_node("新模块"), max(n["id"] for n in snapshot["nodes"]))

    def test_invalid_import_never_changes_current_data(self):
        self.store.seed_demo()
        original = self.store.snapshot()
        variants = []
        bad = copy.deepcopy(original)
        bad["nodes"][0]["title"] = " "
        variants.append(bad)
        bad = copy.deepcopy(original)
        bad["nodes"][0]["x"] = float("nan")
        variants.append(bad)
        bad = copy.deepcopy(original)
        bad["edges"][0]["target"] = 999
        variants.append(bad)
        bad = copy.deepcopy(original)
        bad["edges"].append(dict(id=100, source=4, target=1, kind="前置依赖"))
        variants.append(bad)
        bad = copy.deepcopy(original)
        bad["nodes"][0]["id"] = True
        variants.append(bad)
        bad = copy.deepcopy(original)
        bad["edges"].append(dict(id=100, source=2, target=1, kind="相关内容"))
        variants.append(bad)
        for data in variants:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    self.store.restore(data)
                self.assertEqual(self.store.snapshot(), original)

    def test_diamond_dependencies_and_related_reverse_import(self):
        a, b, c, d = [self.store.create_node(n) for n in "ABCD"]
        for source, target in ((a, b), (a, c), (b, d), (c, d)):
            self.store.add_edge(source, target, "前置依赖")
        self.store.layout()
        self.assertEqual(self.store.node(b)["x"], self.store.node(c)["x"])
        self.assertLess(self.store.node(c)["x"], self.store.node(d)["x"])
        data = self.store.snapshot()
        data["edges"].append(dict(id=100, source=d, target=a, kind="相关内容"))
        self.store.restore(data)
        with self.assertRaisesRegex(ValueError, "已经存在"):
            self.store.add_edge(a, d, "相关内容")


if __name__ == "__main__":
    unittest.main()
