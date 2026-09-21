"""Real Tk window smoke test. Uses a temporary database, never user data."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import LearningMap
from library import DEFAULT_BORDER, DEFAULT_COLORS
from storage import KINDS
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


    def test_right_click_menu_on_module_and_pan_on_empty_canvas(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "menu.db")
            try:
                app.update()
                app.demo()
                app.update()
                target = app.store.nodes()[2]["id"]
                self.assertEqual(app.node_under(SimpleNamespace(x=3, y=3)), None)
                x, y = app.transform(*app.positions[target])
                self.assertEqual(app.node_under(SimpleNamespace(x=x, y=y)), target)
                with patch.object(app, "open_node_menu") as opened:
                    # A right click on a module records the target for the release handler.
                    app.canvas_press_right(SimpleNamespace(x=x, y=y, x_root=11, y_root=22))
                    self.assertEqual(app.menu_request[0], target)
                    self.assertIsNone(app.drag)
                    # Releasing without moving opens the menu at the pointer position.
                    app.canvas_release_right(SimpleNamespace(x=x + 2, y=y - 1))
                    self.assertEqual(opened.call_args[0], (target, 11, 22))
                    self.assertIsNone(app.menu_request)
                    # A right drag across the canvas is still a pan, not a menu.
                    app.canvas_press_right(SimpleNamespace(x=x, y=y, x_root=11, y_root=22))
                    app.canvas_release_right(SimpleNamespace(x=x + 60, y=y))
                    self.assertEqual(opened.call_count, 1)
                app.canvas_press_right(SimpleNamespace(x=3, y=3, x_root=0, y_root=0))
                self.assertIsNone(app.menu_request)
                self.assertEqual(app.drag[0], "pan")
                app.canvas_release_right(SimpleNamespace(x=3, y=3))
                # The menu offers deletion, and running it removes the module.
                app.select(target)
                menu = app.node_menu()
                labels = [menu.entrycget(index, "label") if menu.type(index) != "separator" else ""
                          for index in range(menu.index("end") + 1)]
                self.assertIn("删除这个模块", labels)
                delete_index = labels.index("删除这个模块")
                self.assertEqual(menu.type(delete_index), "command")
                with patch("app.messagebox.askyesno", return_value=True):
                    menu.invoke(delete_index)
                self.assertNotIn(target, [node["id"] for node in app.store.nodes()])
                # 注意力机制 carried a→c, b→c and c→d; all three cascade away.
                self.assertEqual(len(app.store.edges()), 3)
            finally:
                app.store.close()
                app.library.close()
                app.destroy()

    def test_dragging_snaps_to_neighbours_and_shows_guides(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "guides.db")
            try:
                app.update()
                app.demo()
                app.update()
                anchor, moving = app.store.nodes()[0]["id"], app.store.nodes()[1]["id"]
                # 线性代数 and 概率基础 share a column in the automatic layout.
                self.assertEqual(app.positions[anchor][0], app.positions[moving][0])
                # At 100% one world unit is one pixel, so the 7 unit tolerance is unambiguous.
                app.scale_factor = 1.0
                self.assertEqual(app.snap_position(moving, 135, 240), ((130, 240), [("v", 130)]))
                self.assertEqual(app.snap_position(moving, 630, 240), ((630, 240), []))
                app.select(moving)
                app.drag = ("node", moving, 0, 0, *app.positions[moving])
                app.canvas_motion(SimpleNamespace(x=4, y=0))
                self.assertEqual(app.positions[moving][0], app.positions[anchor][0])
                self.assertEqual(app.guides, [("v", app.positions[anchor][0])])
                app.draw()
                self.assertTrue(app.canvas.find_withtag("guide"))
                app.canvas_release(None)
                self.assertEqual(app.guides, [])
                app.draw()
                self.assertFalse(app.canvas.find_withtag("guide"))
                self.assertEqual(app.store.node(moving)["x"], app.store.node(anchor)["x"])
            finally:
                app.store.close()
                app.library.close()
                app.destroy()

    def test_appearance_settings_apply_and_persist_per_map(self):
        with TestDirectory() as directory:
            app = LearningMap(Path(directory) / "appearance.db")
            try:
                app.update()
                app.demo()
                app.update()
                dialog = app.edit_appearance()
                self.assertEqual(dialog.selected, DEFAULT_COLORS)
                self.assertEqual(dialog.border_value(), DEFAULT_BORDER)
                self.assertEqual(dialog.values(), dialog.initial)
                dialog.selected["论文"] = "#FF0000"
                dialog.border.set(4.1)
                dialog.repaint()
                self.assertEqual(dialog.border_value(), 4.0)
                self.assertEqual(dialog.border_label.cget("text"), "4 px")
                self.assertNotEqual(dialog.values(), dialog.initial)
                dialog.submit()
                self.assertEqual(app.kind_colors["论文"], "#ff0000")
                self.assertEqual(app.border_width, 4.0)
                paper = next(node for node in app.store.nodes() if node["kind"] == "论文")
                app.scale_factor = 1.0
                app.draw()
                def outlines(node_id):
                    return {app.canvas.itemcget(item, "outline").lower()
                            for item in app.canvas.find_withtag(f"node:{node_id}")
                            if app.canvas.type(item) == "polygon"}
                def border_width(node_id, color):
                    return {app.canvas.itemcget(item, "width")
                            for item in app.canvas.find_withtag(f"node:{node_id}")
                            if app.canvas.type(item) == "polygon"
                            and app.canvas.itemcget(item, "outline").lower() == color}
                self.assertIn("#ff0000", outlines(paper["id"]))
                self.assertEqual(border_width(paper["id"], "#ff0000"), {"4.0"})
                # Selecting keeps the type colour and adds a ring outside the card instead.
                app.select(paper["id"])
                app.draw()
                self.assertIn("#ff0000", outlines(paper["id"]))
                self.assertIn("#6296ff", outlines(paper["id"]))
                self.assertEqual(border_width(paper["id"], "#ff0000"), {"4.0"})
                # The border follows the zoom exactly as the user set it at 100%.
                app.zoom(SimpleNamespace(x=0, y=0, delta=-120))
                app.draw()
                self.assertLess(float(border_width(paper["id"], "#ff0000").pop()), 4.0)
                app.fit()
                reopened = app.edit_appearance()
                self.assertEqual(reopened.selected["论文"], "#ff0000")
                self.assertEqual(reopened.border_value(), 4.0)
                reopened.reset()
                self.assertEqual(reopened.selected, DEFAULT_COLORS)
                self.assertEqual(reopened.border_value(), DEFAULT_BORDER)
                reopened.destroy()
                other = app.library.create("外观独立的地图")
                self.assertEqual(app.library.kind_colors(other), DEFAULT_COLORS)
                self.assertEqual(app.library.border_width(other), DEFAULT_BORDER)
                app.open_map(other)
                self.assertEqual(app.kind_colors, DEFAULT_COLORS)
                self.assertEqual(app.border_width, DEFAULT_BORDER)
                app.open_map("default")
                self.assertEqual(app.kind_colors["论文"], "#ff0000")
                self.assertEqual(app.border_width, 4.0)
                self.assertEqual(len([node for node in app.store.nodes() if node["kind"] == "论文"]), 2)
            finally:
                app.store.close()
                app.library.close()
                app.destroy()


if __name__ == "__main__":
    unittest.main()
