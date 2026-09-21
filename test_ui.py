"""Real Tk window smoke test. Uses a temporary database, never user data."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import LearningMap
from test_support import TestDirectory


class UITests(unittest.TestCase):
    def test_content_editor_validation_editing_reuse_and_continue(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "edit.db")
            try:
                app.update()
                dialog = app.new_node()
                dialog.submit()
                self.assertTrue(dialog.winfo_exists())
                self.assertTrue(dialog.error.get())
                self.assertEqual(app.store.nodes(), [])
                dialog.fields["title"].set("我的论文")
                dialog.fields["kind"].set("论文")
                dialog.texts["notes"].insert("end", "第一条笔记")
                dialog.submit()
                anchor = app.selected
                self.assertEqual(app.store.node(anchor)["notes"], "第一条笔记")
                dialog = app.new_node("before")
                dialog.fields["title"].set("基础 A")
                dialog.keep_adding.set(True)
                dialog.submit()
                first = app.selected
                self.assertTrue(dialog.winfo_exists())
                dialog.fields["title"].set("基础 B")
                dialog.keep_adding.set(False)
                dialog.submit()
                second = app.selected
                self.assertEqual({(e["source"],e["target"]) for e in app.store.edges()}, {(first,anchor),(second,anchor)})
                app.select(anchor)
                dialog = app.edit_node()
                dialog.texts["notes"].insert("end", "\n补充理解")
                dialog.submit()
                self.assertIn("补充理解", app.store.node(anchor)["notes"])
                dialog = app.new_node()
                dialog.fields["title"].set("基础 A")
                dialog.submit()
                self.assertTrue(dialog.winfo_exists())
                self.assertEqual(len(app.store.nodes()), 3)
                dialog.cancel()
                self.assertTrue(dialog.winfo_exists())
                dialog.cancel()
                self.assertFalse(dialog.winfo_exists())
                # Reusing a prerequisite in reverse would form a cycle, without adding a node.
                app.select(first)
                dialog = app.new_node("before")
                dialog.mode.set("existing")
                dialog.change_mode()
                dialog.existing_choice.set(next(k for k,v in dialog.existing.items() if v == anchor))
                dialog.submit()
                self.assertIn("循环", dialog.error.get())
                self.assertEqual(len(app.store.nodes()), 3)
                dialog.existing_choice.set(next(k for k,v in dialog.existing.items() if v == second))
                dialog.submit()
                self.assertEqual(len(app.store.nodes()), 3)
                self.assertEqual(len(app.store.edges()), 3)
                relation = app.relation_dialog()
                relation.target.set(relation.source.get())
                relation.submit()
                self.assertIn("自身", relation.error.get())
                relation.destroy()
            finally:
                app.store.close()
                app.library.close()
                app.destroy()

    def test_map_dialog_and_small_window_footer(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "dialogs.db")
            try:
                app.geometry("1120x780")
                app.update()
                dialog = app.new_map()
                dialog.name.set("新地图")
                dialog.theme.set("午夜星空")
                dialog.submit()
                self.assertEqual(app.map_name.get(), "新地图")
                self.assertEqual(app.theme.get(), "午夜星空")
                for relative in (None, "before", "after"):
                    if relative:
                        app.select(app.store.nodes()[0]["id"])
                    dialog = app.new_node(relative)
                    dialog.geometry("760x620")
                    app.update()
                    self.assertGreaterEqual(dialog.submit_button.winfo_height(), 39)
                    self.assertLessEqual(dialog.submit_button.winfo_rooty()+40, dialog.winfo_rooty()+dialog.winfo_height())
                    dialog.fields["title"].set("内容 " + str(relative))
                    dialog.submit()
            finally:
                app.store.close()
                app.library.close()
                app.destroy()

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
                dialog = app.new_node("before")
                dialog.fields["title"].set("新的前置知识")
                dialog.submit()
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
                with patch("app.messagebox.askyesnocancel", return_value=True):
                    dialog = app.new_map()
                dialog.name.set("新的学习路线")
                dialog.submit()
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
                dialog = app.new_node()
                dialog.fields["title"].set("新模块")
                dialog.submit()
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
