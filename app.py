"""Learning Map — a dependency-free Python desktop application."""
from __future__ import annotations

import argparse
import json
import math
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from storage import KINDS, MASTERY, RELATIONS, STATES, Store
from library import MapLibrary, THEMES

BASE = Path(__file__).resolve().parent
COLORS = {"未开始": ("#f1f5f9", "#64748b"), "学习中": ("#eff6ff", "#2563eb"), "已完成": ("#ecfdf5", "#059669")}
EDGE_COLORS = {"前置依赖": "#64748b", "进阶延伸": "#8b5cf6", "相关内容": "#0d9488"}
BACKGROUNDS = {
    "晴空点阵": ("#f3f7fc", "#d4deec", "#526580", "#ffffff", "#e0e8f3"),
    "暖纸网格": ("#faf7f0", "#e8e1d4", "#81705a", "#fffdf8", "#e8e0d1"),
    "午夜星空": ("#182338", "#2d3d58", "#a5b8d6", "#25344e", "#111c2e"),
}


class LearningMap(tk.Tk):
    def __init__(self, database=BASE / "data" / "learning_map.db"):
        super().__init__()
        self.title("知路 · 学习地图")
        self.geometry("1440x900")
        self.minsize(1120, 780)
        self.configure(bg="#f5f7fb")
        self.library = MapLibrary(database)
        self.map_id = self.library.active_id
        self.store = Store(self.library.path(self.map_id))
        self.selected = None
        self.loaded_form = None
        self.undo_stack = []
        self.scale_factor, self.offset_x, self.offset_y = 1.0, 30.0, 60.0
        self.drag = None
        self.positions = {}
        self.visible = set()
        self._build_ui()
        self.refresh_map_picker()
        self.bind("<Control-s>", lambda e: self.save())
        self.bind("<Control-n>", lambda e: self.new_node())
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.after(100, self.fit)

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10))
        style.configure("TFrame", background="#f5f7fb")
        style.configure("TLabel", background="#f5f7fb", foreground="#334155")
        style.configure("TButton", padding=(10, 6), background="#ffffff", foreground="#334155", borderwidth=0)
        style.map("TButton", background=[("active", "#e8eef8")])
        style.configure("TNotebook", background="#f5f7fb", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(8, 8), background="#e9eef6", borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#2563eb")])
        style.configure("Accent.TButton", background="#2563eb", foreground="white")
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.configure("Treeview", rowheight=32, background="white", fieldbackground="white", borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9))
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#1e40af")])

        header = tk.Frame(self, bg="#12223b", height=76)
        header.pack(fill="x")
        tk.Label(header, text="知路", font=("Microsoft YaHei UI", 23, "bold"), fg="white", bg="#12223b").pack(side="left", padx=(22, 14), pady=10)
        tk.Label(header, text="LEARNING MAP  /  把知识连成自己的学习路线", font=("Microsoft YaHei UI", 10), fg="#b6c6de", bg="#12223b").pack(side="left")
        tk.Label(header, text="本地存储 · 无需登录", fg="#94a8c4", bg="#12223b").pack(side="right", padx=24)

        maps_bar = ttk.Frame(self, padding=(16, 10, 16, 0))
        maps_bar.pack(fill="x")
        ttk.Label(maps_bar, text="学习空间", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=(0, 12))
        self.map_name = tk.StringVar()
        self.map_picker = ttk.Combobox(maps_bar, textvariable=self.map_name, state="readonly", width=24)
        self.map_picker.pack(side="left", padx=(0, 8))
        self.map_picker.bind("<<ComboboxSelected>>", self.switch_map)
        ttk.Button(maps_bar, text="＋ 新建地图", command=self.new_map, style="Accent.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(maps_bar, text="重命名", command=self.rename_map).pack(side="left")
        self.theme = tk.StringVar(value=self.library.get(self.map_id)["theme"])
        theme_picker = ttk.Combobox(maps_bar, textvariable=self.theme, values=THEMES, state="readonly", width=11)
        theme_picker.pack(side="right")
        theme_picker.bind("<<ComboboxSelected>>", self.change_theme)
        ttk.Label(maps_bar, text="画布背景", foreground="#64748b").pack(side="right", padx=10)

        bar = ttk.Frame(self, padding=(16, 10))
        bar.pack(fill="x")
        for text, command, accent in (("＋ 新建模块", self.new_node, True), ("建立关系", self.relation_dialog, False), ("保存修改  Ctrl+S", self.save, False)):
            ttk.Button(bar, text=text, command=command, style="Accent.TButton" if accent else "TButton").pack(side="left", padx=(0, 8))
        for text, command in (("导出备份", self.export_file), ("导入地图", self.import_file), ("撤销删除 / 导入", self.undo)):
            ttk.Button(bar, text=text, command=command).pack(side="right", padx=(8, 0))

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, padding=(18, 10), foreground="#64748b").pack(side="bottom", fill="x")
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=16)
        left, center, right = ttk.Frame(panes, width=235), ttk.Frame(panes), ttk.Frame(panes, width=330)
        panes.add(left, weight=0)
        panes.add(center, weight=1)
        panes.add(right, weight=0)

        ttk.Label(left, text="我的学习模块", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        self.query = tk.StringVar()
        self.search_entry = ttk.Entry(left, textvariable=self.query)
        self.search_entry.pack(fill="x", padx=(0, 8))
        ttk.Label(left, text="搜索名称、标签或简介", foreground="#94a3b8", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(4, 8))
        filters = ttk.Frame(left)
        filters.pack(fill="x", padx=(0, 8))
        self.kind_filter, self.state_filter = tk.StringVar(value="全部类型"), tk.StringVar(value="全部状态")
        for var, vals in ((self.kind_filter, ("全部类型",) + KINDS), (self.state_filter, ("全部状态",) + STATES)):
            box = ttk.Combobox(filters, textvariable=var, values=vals, state="readonly", width=9)
            box.pack(side="left", expand=True, fill="x", padx=(0, 4))
            box.bind("<<ComboboxSelected>>", lambda e: self.refresh_list_and_graph())
        listing = ttk.Frame(left)
        self.node_list = ttk.Treeview(listing, columns=("state",), show="tree headings", selectmode="browse")
        self.node_list.heading("#0", text="模块")
        self.node_list.heading("state", text="状态")
        self.node_list.column("#0", width=130, minwidth=90)
        self.node_list.column("state", width=65, minwidth=60, stretch=False)
        self.node_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.node_list.yview)
        scroll.pack(side="right", fill="y")
        self.node_list.configure(yscrollcommand=scroll.set)
        self.node_list.bind("<<TreeviewSelect>>", self.list_selected)
        ttk.Button(left, text="清除筛选", command=self.clear_filters).pack(side="bottom", fill="x", padx=(0, 8), pady=(0, 10))
        ttk.Button(left, text="载入示例地图", command=self.demo).pack(side="bottom", fill="x", padx=(0, 8), pady=(0, 8))
        listing.pack(fill="both", expand=True, pady=10, padx=(0, 8))
        self.query.trace_add("write", lambda *a: self.refresh_list_and_graph())

        graph_bar = ttk.Frame(center)
        graph_bar.pack(fill="x", pady=(0, 8))
        ttk.Button(graph_bar, text="自动排列", command=self.auto_layout).pack(side="left")
        ttk.Button(graph_bar, text="适应视图", command=self.fit).pack(side="left", padx=5)
        self.focus_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(graph_bar, text="聚焦当前模块", variable=self.focus_only, command=self.focus_changed).pack(side="left")
        self.canvas = tk.Canvas(center, background="#ffffff", highlightthickness=1, highlightbackground="#dce3ed")
        self.canvas.pack(fill="both", expand=True, padx=(0, 10))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<ButtonPress-3>", self.pan_press)
        self.canvas.bind("<B3-Motion>", self.canvas_motion)
        self.canvas.bind("<ButtonRelease-3>", self.canvas_release)
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<Button-4>", lambda e: self.zoom(e, 1.1))
        self.canvas.bind("<Button-5>", lambda e: self.zoom(e, 1 / 1.1))
        ttk.Label(center, text="实线 → 前置依赖    紫虚线 → 进阶延伸    绿点线 — 相关内容", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(8, 2))
        ttk.Label(center, text="拖动模块调整位置 · 拖动空白平移 · 滚轮缩放", foreground="#94a3b8", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(0, 10))

        self.detail_title = ttk.Label(right, text="模块详情", font=("Microsoft YaHei UI", 12, "bold"))
        self.detail_title.pack(anchor="w", pady=(0, 10))
        self.notebook = ttk.Notebook(right)
        info, writing, connections = (ttk.Frame(self.notebook, padding=12) for _ in range(3))
        # A scrollable inspector keeps all fields reachable on smaller displays.
        info_page = info
        info_page.configure(padding=0)
        inspector = tk.Canvas(info_page, highlightthickness=0, background="#f5f7fb", width=280)
        inspector_scroll = ttk.Scrollbar(info_page, command=inspector.yview)
        inspector.configure(yscrollcommand=inspector_scroll.set)
        inspector_scroll.pack(side="right", fill="y")
        inspector.pack(side="left", fill="both", expand=True)
        info = ttk.Frame(inspector, padding=12)
        info_window = inspector.create_window(0, 0, window=info, anchor="nw")
        info.bind("<Configure>", lambda e: inspector.configure(scrollregion=inspector.bbox("all")))
        inspector.bind("<Configure>", lambda e: inspector.itemconfigure(info_window, width=e.width))
        self.notebook.add(info_page, text="基本信息")
        self.notebook.add(writing, text="笔记 / 资料")
        self.notebook.add(connections, text="模块关系")
        self.form_vars = {k: tk.StringVar() for k in ("title", "kind", "state", "mastery", "tags")}
        for label, key, options in (("模块名称 *", "title", None), ("模块类型", "kind", KINDS), ("学习状态", "state", STATES), ("掌握程度", "mastery", MASTERY), ("标签（用逗号分隔）", "tags", None)):
            ttk.Label(info, text=label).pack(anchor="w", pady=(4, 4))
            widget = ttk.Combobox(info, textvariable=self.form_vars[key], values=options, state="readonly") if options else ttk.Entry(info, textvariable=self.form_vars[key])
            widget.pack(fill="x")
        ttk.Label(info, text="简介 / 学习目标").pack(anchor="w", pady=(14, 5))
        self.summary = self.text_area(info, height=3)
        self.updated = ttk.Label(info, text="先从左侧选择或新建一个模块", foreground="#94a3b8", wraplength=280, font=("Microsoft YaHei UI", 9))
        self.updated.pack(anchor="w", pady=6)
        ttk.Label(writing, text="学习笔记 / 待解决问题").pack(anchor="w", pady=(0, 6))
        self.notes = self.text_area(writing, height=6, expand=True)
        ttk.Label(writing, text="参考资料（每行一个链接或文件路径）", wraplength=270).pack(anchor="w", pady=(14, 6))
        self.resources = self.text_area(writing, height=3)
        ttk.Label(writing, text="笔记和资料随模块保存；本地文件只保存路径。", foreground="#94a3b8", wraplength=270, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=10)
        ttk.Label(connections, text="箭头从前置内容指向后续内容。\n相关内容是双向关系。", wraplength=280).pack(anchor="w", pady=(0, 10))
        self.edge_list = ttk.Treeview(connections, columns=("label",), show="headings", selectmode="browse", height=10)
        self.edge_list.heading("label", text="当前模块的连接")
        self.edge_list.column("label", width=255)
        self.edge_list.bind("<Double-1>", self.visit_neighbor)
        ttk.Label(connections, text="双击关系可跳转到相连模块。", foreground="#94a3b8", font=("Microsoft YaHei UI", 9)).pack(side="bottom", anchor="w")
        ttk.Button(connections, text="删除选中的关系", command=self.delete_relation).pack(side="bottom", fill="x", pady=8)
        self.edge_list.pack(fill="both", expand=True)
        actions = ttk.Frame(right)
        ttk.Button(right, text="删除当前模块", command=self.delete_node).pack(side="bottom", fill="x", pady=(0, 10))
        actions.pack(side="bottom", fill="x", pady=10)
        ttk.Button(actions, text="＋ 前置模块", command=lambda: self.new_node("before")).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(actions, text="＋ 延伸模块", command=lambda: self.new_node("after")).pack(side="left", expand=True, fill="x")
        self.notebook.pack(fill="both", expand=True)

    def refresh_map_picker(self):
        self.map_choices = {m["title"]: m["id"] for m in self.library.maps()}
        self.map_picker.configure(values=list(self.map_choices))
        current = self.library.get(self.map_id)
        self.map_name.set(current["title"])
        self.theme.set(current["theme"])
        self.title(f"知路 · {current['title']}")

    def open_map(self, map_id):
        if map_id == self.map_id:
            return
        path = self.library.path(map_id)
        if not path.exists():
            raise ValueError("地图文件不存在，请恢复备份后重试。")
        next_store = Store(path)
        try:
            self.library.activate(map_id)
        except Exception:
            next_store.close()
            raise
        self.store.close()
        self.store = next_store
        self.map_id = map_id
        self.selected = None
        self.loaded_form = None
        self.undo_stack = []
        self.drag = None
        self.scale_factor, self.offset_x, self.offset_y = 1.0, 30.0, 60.0
        self.refresh_map_picker()
        self.clear_filters()
        self.load_detail()
        self.fit()

    def switch_map(self, event=None):
        target = self.map_choices.get(self.map_name.get())
        if target is None or target == self.map_id:
            return
        if not self.ensure_saved():
            self.refresh_map_picker()
            return
        try:
            self.open_map(target)
        except (OSError, ValueError) as error:
            self.refresh_map_picker()
            messagebox.showerror("切换失败", str(error), parent=self)

    def new_map(self):
        if not self.ensure_saved():
            return
        title = simpledialog.askstring("新建空白地图", "为新的学习地图命名：\n已有地图会保留，可随时切换回来。", parent=self)
        if title is None:
            return
        try:
            self.open_map(self.library.create(title))
            self.status.set(f"已创建空白地图「{title.strip()}」，点击「新建模块」开始。")
        except (OSError, ValueError) as error:
            messagebox.showerror("新建失败", str(error), parent=self)

    def rename_map(self):
        title = simpledialog.askstring("重命名地图", "新的地图名称：", initialvalue=self.map_name.get(), parent=self)
        if title is not None:
            try:
                self.library.rename(self.map_id, title)
                self.refresh_map_picker()
            except ValueError as error:
                messagebox.showerror("重命名失败", str(error), parent=self)

    def change_theme(self, event=None):
        self.library.set_theme(self.map_id, self.theme.get())
        self.draw()

    @staticmethod
    def text_area(parent, height, expand=False):
        frame = ttk.Frame(parent)
        frame.pack(fill="both" if expand else "x", expand=expand)
        text = tk.Text(frame, height=height, width=25, wrap="word", undo=True, font=("Microsoft YaHei UI", 10), relief="flat", highlightthickness=1, highlightbackground="#dce3ed", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return text

    def form_data(self):
        data = {k: var.get() for k, var in self.form_vars.items()}
        data.update(summary=self.summary.get("1.0", "end-1c"), notes=self.notes.get("1.0", "end-1c"), resources=self.resources.get("1.0", "end-1c"))
        return data

    def ensure_saved(self):
        if self.selected and self.loaded_form is not None and self.form_data() != self.loaded_form:
            answer = messagebox.askyesnocancel("保存修改", "当前模块有未保存的修改，是否保存？", parent=self)
            if answer is None:
                return False
            if answer:
                return self.save()
        return True

    def save(self):
        if self.selected is None:
            self.status.set("请先选择或新建模块。")
            return False
        try:
            self.store.update_node(self.selected, **self.form_data())
        except ValueError as error:
            messagebox.showerror("无法保存", str(error), parent=self)
            return False
        self.load_detail()
        self.refresh_list_and_graph()
        self.status.set("已保存：" + self.store.node(self.selected)["title"])
        return True

    def refresh(self):
        self.refresh_list_and_graph()
        self.load_detail()

    def refresh_list_and_graph(self):
        nodes = self.store.nodes()
        query = self.query.get().strip().casefold()
        filtered = [n for n in nodes if (not query or query in (n["title"] + " " + n["tags"] + " " + n["summary"]).casefold()) and (self.kind_filter.get() == "全部类型" or n["kind"] == self.kind_filter.get()) and (self.state_filter.get() == "全部状态" or n["state"] == self.state_filter.get())]
        self.node_list.delete(*self.node_list.get_children())
        for node in filtered:
            self.node_list.insert("", "end", iid=str(node["id"]), text=node["title"], values=(node["state"],))
        if self.selected and self.node_list.exists(str(self.selected)):
            self.node_list.selection_set(str(self.selected))
        self.visible = {n["id"] for n in filtered}
        if self.focus_only.get() and self.selected:
            neighbors = {self.selected}
            for edge in self.store.edges():
                if self.selected in (edge["source"], edge["target"]):
                    neighbors.update((edge["source"], edge["target"]))
            self.visible &= neighbors
        self.positions = {n["id"]: (n["x"], n["y"]) for n in nodes}
        self.draw()
        completed = sum(n["state"] == "已完成" for n in nodes)
        self.status.set(f"{len(nodes)} 个模块 · {len(self.store.edges())} 条关系 · 已完成 {completed} 个 · 当前显示 {len(self.visible)} 个")

    def load_detail(self):
        node = self.store.node(self.selected) if self.selected else None
        if not node:
            self.selected = None
        for key, var in self.form_vars.items():
            var.set(node[key] if node else "")
        for key, text in (("summary", self.summary), ("notes", self.notes), ("resources", self.resources)):
            text.delete("1.0", "end")
            text.insert("1.0", node[key] if node else "")
            text.edit_reset()
        self.loaded_form = self.form_data() if node else None
        self.detail_title.configure(text="模块详情" if node else "选择一个模块开始")
        self.updated.configure(text=f"最近保存：{node['updated_at'].replace('T', ' ')}" if node else "点击「新建模块」，或载入示例地图。")
        self.edge_list.delete(*self.edge_list.get_children())
        names = {n["id"]: n["title"] for n in self.store.nodes()}
        for edge in self.store.edges():
            if self.selected not in (edge["source"], edge["target"]):
                continue
            outgoing = edge["source"] == self.selected
            other = edge["target"] if outgoing else edge["source"]
            direction = "↔" if edge["kind"] == "相关内容" else ("→" if outgoing else "←")
            self.edge_list.insert("", "end", iid=str(edge["id"]), values=(f"{direction} {names[other]} · {edge['kind']}",))

    def select(self, node_id):
        if self.selected == node_id:
            return True
        if not self.ensure_saved():
            if self.selected and self.node_list.exists(str(self.selected)):
                self.node_list.selection_set(str(self.selected))
            return False
        self.selected = node_id
        self.load_detail()
        self.refresh_list_and_graph()
        return True

    def list_selected(self, event=None):
        selection = self.node_list.selection()
        if selection:
            self.select(int(selection[0]))

    def new_node(self, relative=None):
        if relative and not self.selected:
            self.status.set("先选择一个模块，再为它添加前置或延伸模块。")
            return
        if not self.ensure_saved():
            return
        title = simpledialog.askstring("新建模块", "输入模块名称：", parent=self)
        if title is None:
            return
        title = title.strip()
        if not title:
            messagebox.showerror("名称为空", "请输入模块名称。", parent=self)
            return
        if any(n["title"] == title for n in self.store.nodes()):
            if not messagebox.askyesno("发现同名模块", "已有同名模块，可通过「建立关系」复用它。仍要创建一个新的同名模块吗？", parent=self):
                return
        old = self.selected
        if relative:
            x, y = self.positions[old]
            x += -270 if relative == "before" else 270
            occupied = list(self.positions.values())
            while any(abs(x - px) < 200 and abs(y - py) < 95 for px, py in occupied):
                y += 140
        else:
            count = len(self.store.nodes())
            x, y = 130 + (count % 3) * 270, 100 + (count // 3) * 140
        nid = self.store.create_node(title, x=x, y=y)
        if relative == "before":
            self.store.add_edge(nid, old, "前置依赖")
        elif relative == "after":
            self.store.add_edge(old, nid, "进阶延伸")
        self.selected = nid
        self.clear_filters()
        self.load_detail()
        self.fit()

    def relation_dialog(self):
        if not self.ensure_saved():
            return
        nodes = self.store.nodes()
        if len(nodes) < 2:
            messagebox.showinfo("建立关系", "请先创建至少两个模块。", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("建立模块关系")
        dialog.geometry("480x340")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        labels = {f"{n['title']}  [#{n['id']}]": n["id"] for n in nodes}
        values = list(labels)
        selected_index = next((i for i, n in enumerate(nodes) if n["id"] == self.selected), 0)
        source = tk.StringVar(value=values[selected_index])
        target = tk.StringVar(value=values[(selected_index + 1) % len(values)])
        kind = tk.StringVar(value=RELATIONS[0])
        for title, var, options in (("起点模块 A", source, values), ("关系类型", kind, RELATIONS), ("终点模块 B", target, values)):
            ttk.Label(frame, text=title).pack(anchor="w", pady=(0, 4))
            ttk.Combobox(frame, textvariable=var, values=options, state="readonly").pack(fill="x", pady=(0, 10))
        ttk.Label(frame, text="前置依赖：A 是学习 B 的前提。\n进阶延伸：学完 A 可以继续学 B。", foreground="#64748b").pack(anchor="w")

        def commit():
            try:
                self.store.add_edge(labels[source.get()], labels[target.get()], kind.get())
            except ValueError as error:
                messagebox.showerror("无法建立关系", str(error), parent=dialog)
                return
            dialog.destroy()
            self.refresh()
        ttk.Button(frame, text="建立关系", style="Accent.TButton", command=commit).pack(anchor="e", pady=(10, 0))

    def remember(self):
        self.undo_stack.append(self.store.snapshot())
        self.undo_stack = self.undo_stack[-10:]

    def delete_node(self):
        if not self.selected or not self.ensure_saved():
            return
        name = self.store.node(self.selected)["title"]
        if not messagebox.askyesno("删除模块", f"删除「{name}」及其所有连接？\n可以通过顶部按钮撤销。", parent=self):
            return
        self.remember()
        self.store.delete_node(self.selected)
        self.selected = None
        self.refresh()

    def delete_relation(self):
        selection = self.edge_list.selection()
        if not selection or not self.ensure_saved():
            return
        self.remember()
        self.store.delete_edge(int(selection[0]))
        self.refresh()

    def undo(self):
        if not self.undo_stack:
            self.status.set("没有可撤销的删除或导入操作。")
            return
        if not self.ensure_saved():
            return
        if not messagebox.askyesno("恢复操作前的地图", "将恢复到最近一次删除或导入之前的完整地图。\n该操作之后新增或修改的内容也会回退。继续吗？", parent=self):
            return
        self.backup()
        self.store.restore(self.undo_stack[-1])
        self.undo_stack.pop()
        self.selected = None
        self.refresh()
        self.fit()
        self.status.set("已恢复操作前的地图；恢复前的当前数据已自动备份。")

    def visit_neighbor(self, event=None):
        selection = self.edge_list.selection()
        if selection:
            edge = next((e for e in self.store.edges() if e["id"] == int(selection[0])), None)
            if edge:
                self.select(edge["target"] if edge["source"] == self.selected else edge["source"])

    def clear_filters(self):
        self.query.set("")
        self.kind_filter.set("全部类型")
        self.state_filter.set("全部状态")
        self.focus_only.set(False)
        self.refresh_list_and_graph()

    def focus_changed(self):
        if self.focus_only.get() and not self.selected:
            self.focus_only.set(False)
            self.status.set("请先选择要聚焦的模块。")
            return
        self.refresh_list_and_graph()
        self.fit()

    def backup(self):
        folder = self.library.original.parent / "backups" / self.map_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
        self.store.export(path)
        return path

    def export_file(self):
        if not self.ensure_saved():
            return
        path = filedialog.asksaveasfilename(parent=self, title="导出完整学习地图", defaultextension=".json", initialfile="学习地图.json", filetypes=[("学习地图 JSON", "*.json")])
        if path:
            try:
                reserved = {self.library.path(m['id']).resolve() for m in self.library.maps()}
                reserved.add(self.library.original.with_suffix(".library.db"))
                if Path(path).resolve() in reserved:
                    raise ValueError("不能覆盖地图数据库或地图目录。")
                self.store.export(path)
                self.status.set("已导出完整地图：" + path)
            except (OSError, ValueError) as error:
                messagebox.showerror("导出失败", str(error), parent=self)

    def import_file(self):
        if not self.ensure_saved():
            return
        path = filedialog.askopenfilename(parent=self, title="导入学习地图", filetypes=[("学习地图 JSON", "*.json")])
        if not path:
            return
        try:
            if Path(path).stat().st_size > 20 * 1024 * 1024:
                raise ValueError("导入文件超过 20 MB。")
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            Store.validate_snapshot(data)
            if not messagebox.askyesno("替换当前地图", f"导入 {len(data['nodes'])} 个模块和 {len(data['edges'])} 条关系，替换「{self.map_name.get()}」？\n其他地图不受影响。当前地图会先备份，也可撤销导入。", parent=self):
                return
            self.backup()
            self.remember()
            self.store.restore(data)
        except (OSError, ValueError) as error:
            messagebox.showerror("导入失败", str(error), parent=self)
            return
        self.selected = None
        self.clear_filters()
        self.refresh()
        self.fit()

    def demo(self):
        if self.store.nodes():
            messagebox.showinfo("载入示例", "示例只在地图为空时载入，避免影响已有内容。", parent=self)
            return
        self.store.seed_demo()
        self.refresh()
        self.fit()

    def auto_layout(self):
        self.store.layout()
        self.refresh_list_and_graph()
        self.fit()

    def transform(self, x, y):
        return x * self.scale_factor + self.offset_x, y * self.scale_factor + self.offset_y

    def fit(self):
        points = [self.positions[i] for i in self.visible if i in self.positions]
        if not points:
            self.draw()
            return
        x1, x2 = min(p[0] for p in points) - 110, max(p[0] for p in points) + 110
        y1, y2 = min(p[1] for p in points) - 55, max(p[1] for p in points) + 55
        width, height = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
        self.scale_factor = min(1.25, max(.15, min((width - 50) / (x2 - x1), (height - 70) / (y2 - y1))))
        self.offset_x = width / 2 - (x1 + x2) / 2 * self.scale_factor
        self.offset_y = height / 2 - (y1 + y2) / 2 * self.scale_factor
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        s = self.scale_factor
        bg, grid, muted, card, shadow = BACKGROUNDS[self.theme.get()]
        dark = self.theme.get() == "午夜星空"
        self.canvas.configure(background=bg)
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        # World-aligned texture, bounded density even when zoomed far out.
        step = 28 * s
        while step < 22:
            step *= 2
        if self.theme.get() == "暖纸网格":
            for x in range(round(self.offset_x % step), width, max(1, round(step))):
                self.canvas.create_line(x, 0, x, height, fill=grid, tags="background")
            for y in range(round(self.offset_y % step), height, max(1, round(step))):
                self.canvas.create_line(0, y, width, y, fill=grid, tags="background")
        else:
            for x in range(round(self.offset_x % step), width, max(1, round(step))):
                for y in range(round(self.offset_y % step), height, max(1, round(step))):
                    self.canvas.create_oval(x, y, x + 2, y + 2, fill=grid, outline="", tags="background")
        if not self.visible:
            has_nodes = bool(self.positions)
            cx, cy = width / 2, height / 2
            half = min(200, max(100, width / 2 - 24))
            self.rounded_rect(cx - half, cy - 113, cx + half, cy + 113, 20, fill=card, outline=grid)
            self.canvas.create_text(cx, cy - 65, text="◇  从这里，连接新的知识", fill="#9bbcff" if dark else "#2563eb", font=("Microsoft YaHei UI", 13, "bold"))
            self.canvas.create_text(cx, cy - 10, text="没有匹配的模块，试试清除筛选" if has_nodes else "这是一张属于你的空白地图\n添加论文、知识点，逐步连接学习路线", fill=muted, font=("Microsoft YaHei UI", 10), justify="center", width=half * 2 - 24)
            self.rounded_rect(cx - 85, cy + 40, cx + 85, cy + 78, 10, fill="#2563eb", outline="", tags="empty-action")
            self.canvas.create_text(cx, cy + 59, text="清除筛选" if has_nodes else "＋ 添加第一个模块", fill="white", font=("Microsoft YaHei UI", 10), tags="empty-action")
            return
        edges = [e for e in self.store.edges() if e["source"] in self.visible and e["target"] in self.visible]
        groups = {}
        for edge in edges:
            groups.setdefault(tuple(sorted((edge["source"], edge["target"]))), []).append(edge)
        for group in groups.values():
            for index, edge in enumerate(group):
                a, b = self.positions[edge["source"]], self.positions[edge["target"]]
                dx, dy = b[0] - a[0], b[1] - a[1]
                if not dx and not dy:
                    continue
                ratio = min(100 / abs(dx) if dx else math.inf, 44 / abs(dy) if dy else math.inf, .45)
                start = self.transform(a[0] + dx * ratio, a[1] + dy * ratio)
                end = self.transform(b[0] - dx * ratio, b[1] - dy * ratio)
                # Separate multiple relationship types between the same pair.
                length = math.hypot(dx, dy)
                bend = (index - (len(group) - 1) / 2) * 40 * s
                # Canonical direction keeps opposite arrows on distinct curves.
                sign = 1 if edge["source"] < edge["target"] else -1
                mid = ((start[0] + end[0]) / 2 - dy / length * bend * sign, (start[1] + end[1]) / 2 + dx / length * bend * sign)
                color = {"前置依赖": "#9badc8", "进阶延伸": "#b69bff", "相关内容": "#52cdb7"}[edge["kind"]] if dark else EDGE_COLORS[edge["kind"]]
                options = dict(fill=color, width=max(1, 1.8 * s), arrow="none" if edge["kind"] == "相关内容" else "last", arrowshape=(9, 11, 4), smooth=True)
                if edge["kind"] != "前置依赖":
                    options["dash"] = (7, 4) if edge["kind"] == "进阶延伸" else (2, 5)
                self.canvas.create_line(*start, *mid, *end, **options)
        for node in self.store.nodes():
            nid = node["id"]
            if nid not in self.visible:
                continue
            x, y = self.transform(*self.positions[nid])
            w, h = 100 * s, 44 * s
            fill, accent = COLORS[node["state"]]
            tag = f"node:{nid}"
            if dark:
                accent = {"未开始": "#adbed5", "学习中": "#8ab5ff", "已完成": "#65dab9"}[node["state"]]
            self.rounded_rect(x - w + 2, y - h + 5, x + w + 2, y + h + 5, 12 * s, fill=shadow, outline="", tags=tag)
            self.rounded_rect(x - w, y - h, x + w, y + h, 12 * s, fill=card, outline="#6296ff" if nid == self.selected else grid, width=2 if nid == self.selected else 1, tags=tag)
            self.canvas.create_oval(x - w + 13*s, y + 23*s, x - w + 19*s, y + 29*s, fill=accent, outline="", tags=tag)
            title = node["title"] if len(node["title"]) <= 24 else node["title"][:23] + "…"
            self.canvas.create_text(x, y - 11 * s, text=title, width=180 * s, font=("Microsoft YaHei UI", max(7, round(11 * s)), "bold"), fill="#edf3ff" if dark else "#1e293b", tags=tag)
            self.canvas.create_text(x, y + 26 * s, text=f"{node['kind']}  ·  {node['state']}", font=("Microsoft YaHei UI", max(6, round(9 * s))), fill=accent, tags=tag)
        self.rounded_rect(10, 10, 132, 38, 8, fill=card, outline=grid)
        self.canvas.create_text(22, 24, anchor="w", text=f"{round(s * 100)}%  ·  {len(self.visible)} 个模块", fill=muted, font=("Microsoft YaHei UI", 9))

    def rounded_rect(self, x1, y1, x2, y2, radius, **options):
        r = min(radius, (x2-x1)/2, (y2-y1)/2)
        points = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.canvas.create_polygon(points, smooth=True, splinesteps=20, **options)

    def canvas_press(self, event):
        current = self.canvas.find_withtag("current")
        tags = self.canvas.gettags(current[0]) if current else ()
        if "empty-action" in tags:
            self.clear_filters() if self.positions else self.new_node()
            return
        node_tag = next((tag for tag in tags if tag.startswith("node:")), None)
        if node_tag:
            nid = int(node_tag.split(":")[1])
            if self.select(nid):
                self.drag = ("node", nid, event.x, event.y, *self.positions[nid])
        else:
            self.pan_press(event)

    def pan_press(self, event):
        self.drag = ("pan", None, event.x, event.y, self.offset_x, self.offset_y)
        self.canvas.configure(cursor="fleur")

    def canvas_motion(self, event):
        if not self.drag:
            return
        kind, nid, sx, sy, x, y = self.drag
        if kind == "node":
            self.positions[nid] = (x + (event.x - sx) / self.scale_factor, y + (event.y - sy) / self.scale_factor)
        else:
            self.offset_x, self.offset_y = x + event.x - sx, y + event.y - sy
        self.draw()

    def canvas_release(self, event):
        if self.drag and self.drag[0] == "node":
            nid = self.drag[1]
            self.store.set_positions({nid: self.positions[nid]})
        self.drag = None
        self.canvas.configure(cursor="")

    def zoom(self, event, factor=None):
        if self.drag:
            return
        factor = factor or (1.1 if event.delta > 0 else 1 / 1.1)
        new_scale = min(2.5, max(.15, self.scale_factor * factor))
        ratio = new_scale / self.scale_factor
        self.offset_x = event.x - (event.x - self.offset_x) * ratio
        self.offset_y = event.y - (event.y - self.offset_y) * ratio
        self.scale_factor = new_scale
        self.draw()

    def report_callback_exception(self, exc, value, traceback):
        import logging
        logging.error("UI action failed", exc_info=(exc, value, traceback))
        messagebox.showerror("操作未完成", f"{value}\n\n数据文件：{self.store.path}", parent=self)

    def close(self):
        if self.ensure_saved():
            self.store.close()
            self.library.close()
            self.destroy()


def main():
    parser = argparse.ArgumentParser(description="知路 · 本地学习地图")
    parser.add_argument("--db", type=Path, default=BASE / "data" / "learning_map.db", help="指定 SQLite 数据文件")
    args = parser.parse_args()
    app = LearningMap(args.db)
    app.mainloop()


if __name__ == "__main__":
    main()
