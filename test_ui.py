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
                app.destroy()


if __name__ == "__main__":
    unittest.main()
