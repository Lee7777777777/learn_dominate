"""Real Tk window smoke test. Uses a temporary database, never user data."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import LearningMap
from test_support import TestDirectory


class UITests(unittest.TestCase):
    def test_learning_flow(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "test.db")
            try:
                app.update()
                app.demo()
                app.update()
                self.assertEqual(len(app.visible), 6)
                nid = app.store.nodes()[0]["id"]
                app.select(nid)
                app.notes.insert("end", "实际窗口编辑笔记")
                self.assertTrue(app.save())
                self.assertIn("实际窗口", app.store.node(nid)["notes"])
                app.form_vars["title"].set("未保存标题")
                with patch("app.messagebox.askyesnocancel", return_value=None):
                    self.assertFalse(app.select(nid + 1))
                self.assertEqual(app.selected, nid)
                with patch("app.messagebox.askyesnocancel", return_value=False):
                    self.assertTrue(app.select(nid + 1))
                self.assertEqual(app.store.node(nid)["title"], "线性代数")
                app.query.set("Transformer")
                app.update()
                self.assertEqual(len(app.visible), 1)
                app.clear_filters()
                app.select(nid)
                app.focus_only.set(True)
                app.focus_changed()
                self.assertEqual(len(app.visible), 3)
                app.clear_filters()
                original = app.positions[nid]
                app.drag = ("node", nid, 0, 0, *original)
                app.canvas_motion(SimpleNamespace(x=40, y=20))
                app.canvas_release(None)
                self.assertNotEqual(app.store.node(nid)["x"], original[0])
                with patch("app.simpledialog.askstring", return_value="新的前置知识"):
                    app.new_node("before")
                self.assertTrue(any(e["source"] == app.selected and e["target"] == nid for e in app.store.edges()))
                with patch("app.messagebox.askyesno", return_value=True):
                    app.delete_node()
                    app.undo()
                self.assertEqual(len(app.store.nodes()), 7)
                app.relation_dialog()
                app.update()
                dialogs = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]
                self.assertEqual(len(dialogs), 1)
                dialogs[0].destroy()
                app.geometry("1120x740")
                app.update()
                self.assertGreater(app.canvas.winfo_width(), 350)
                self.assertTrue(app.resources.winfo_exists())
                for tab in range(3):
                    app.notebook.select(tab)
                    app.update()
                    # Inactive notebook pages are intentionally unmapped.
                    for widget in app.winfo_children():
                        if widget.winfo_class() != "Toplevel":
                            def visible_buttons(parent):
                                for child in parent.winfo_children():
                                    if child.winfo_ismapped():
                                        if child.winfo_class() == "TButton":
                                            self.assertGreaterEqual(child.winfo_height(), 30, child.cget("text"))
                                        visible_buttons(child)
                            visible_buttons(widget)
            finally:
                app.store.close()
                app.library.close()
                app.destroy()

    def test_new_map_switch_cancel_and_background(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "test.db")
            try:
                app.update()
                app.demo()
                app.select(1)
                app.notes.insert("end", "还未保存的笔记")
                with patch("app.messagebox.askyesnocancel", return_value=None):
                    app.new_map()
                self.assertEqual(len(app.library.maps()), 1)
                with patch("app.messagebox.askyesnocancel", return_value=True), patch("app.simpledialog.askstring", return_value="新的学习路线"):
                    app.new_map()
                self.assertEqual(app.store.nodes(), [])
                self.assertEqual(app.store.edges(), [])
                self.assertEqual(app.visible, set())
                self.assertIsNone(app.selected)
                self.assertEqual(app.notes.get("1.0", "end-1c"), "")
                self.assertTrue(app.canvas.find_withtag("empty-action"))
                new_map = app.map_id
                app.theme.set("午夜星空")
                app.change_theme()
                self.assertEqual(app.canvas.cget("background"), "#182338")
                with patch("app.simpledialog.askstring", return_value="新模块"):
                    app.new_node()
                app.notes.insert("end", "未保存")
                app.map_name.set("我的第一张地图")
                with patch("app.messagebox.askyesnocancel", return_value=None):
                    app.switch_map()
                self.assertEqual(app.map_id, new_map)
                self.assertEqual(app.map_name.get(), "新的学习路线")
                app.map_name.set("我的第一张地图")
                with patch("app.messagebox.askyesnocancel", return_value=True):
                    app.switch_map()
                self.assertEqual(len(app.store.nodes()), 6)
                self.assertIn("还未保存的笔记", app.store.node(1)["notes"])
                app.map_name.set("新的学习路线")
                app.switch_map()
                self.assertEqual(len(app.store.nodes()), 1)
                self.assertEqual(app.theme.get(), "午夜星空")
                self.assertEqual(app.undo_stack, [])
                for theme in ("晴空点阵", "暖纸网格", "午夜星空"):
                    app.theme.set(theme)
                    app.change_theme()
                    app.zoom(SimpleNamespace(x=100, y=100, delta=120))
                    self.assertTrue(app.canvas.find_withtag("background"))
            finally:
                app.store.close()
                app.library.close()
                app.destroy()


if __name__ == "__main__":
    unittest.main()
