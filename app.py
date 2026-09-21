"""Learning Map — a dependency-free Python desktop application."""
from __future__ import annotations

import argparse
import json
import math
import logging
import webbrowser
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from storage import KINDS, MASTERY, RELATIONS, STATES, Store
from library import DEFAULT_BORDER, DEFAULT_COLORS, MapLibrary, THEMES
from runtime import RELEASE_URL, prepare_data_dir
from version import __version__
from dialogs import AppearanceDialog, ContentDialog, MapDialog, RelationDialog, SoftButton, bind_form_scroll

BASE = Path(__file__).resolve().parent
STATE_COLORS = {"未开始": "#64748b", "学习中": "#2563eb", "已完成": "#059669"}
STATE_COLORS_DARK = {"未开始": "#adbed5", "学习中": "#8ab5ff", "已完成": "#65dab9"}
EDGE_COLORS = {"前置依赖": "#64748b", "进阶延伸": "#8b5cf6", "相关内容": "#0d9488"}
EDGE_COLORS_DARK = {"前置依赖": "#9badc8", "进阶延伸": "#b69bff", "相关内容": "#52cdb7"}
GUIDE_COLOR = "#ff4f9a"
# Node geometry in world units, shared by drawing and alignment snapping.
NODE_HALF_WIDTH, NODE_HALF_HEIGHT, GUIDE_TOLERANCE = 100, 44, 7
BACKGROUNDS = {
    "晴空点阵": ("#f3f7fc", "#d4deec", "#526580", "#ffffff", "#e0e8f3"),
    "暖纸网格": ("#faf7f0", "#e8e1d4", "#81705a", "#fffdf8", "#e8e0d1"),
    "午夜星空": ("#182338", "#2d3d58", "#a5b8d6", "#25344e", "#111c2e"),
}


def lighten(color, ratio):
    """Lift a content colour so it stays readable on the dark canvas."""
    channels = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(f"{round(value + (255 - value) * ratio):02x}" for value in channels)


class LearningMap(tk.Tk):
    def __init__(self, database=None):
        super().__init__()
        self.title("知路 · 学习地图")
        self.geometry("1440x900")
        self.minsize(1120, 780)
        self.configure(bg="#f5f7fb")
        if (BASE / "app.ico").exists():
            self.iconbitmap(str(BASE / "app.ico"))
        self.library = MapLibrary(database or prepare_data_dir() / "learning_map.db")
        self.map_id = self.library.active_id
        self.store = Store(self.library.path(self.map_id))
        self.kind_colors = self.library.kind_colors(self.map_id)
        self.border_width = self.library.border_width(self.map_id)
        self.selected = None
        self.loaded_form = None
        self.undo_stack = []
        self.scale_factor, self.offset_x, self.offset_y = 1.0, 30.0, 60.0
        self.drag = None
        self.positions = {}
        self.visible = set()
        self.guides = []
        self.menu_request = None
        self.popup = None
        self.graph_nodes, self.graph_edges = [], []
        self._draw_job = None
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
        style.layout("TNotebook.Tab", [("Notebook.padding", {"children": [("Notebook.label", {"sticky": "nswe"})], "sticky": "nswe"})])
        style.configure("TNotebook.Tab", padding=(10, 9), background="#eef0f7", borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")], foreground=[("selected", "#5865d8")])
        style.configure("Accent.TButton", background="#5865d8", foreground="white")
        style.map("Accent.TButton", background=[("active", "#4955c5")])
        style.configure("TEntry", padding=7, fieldbackground="white", bordercolor="#e1e5ee", lightcolor="white", darkcolor="white")
        style.map("TEntry", bordercolor=[("focus", "#5865d8")])
        style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})], "sticky": "ns"})])
        style.configure("Vertical.TScrollbar", width=9, arrowsize=0, background="#dce1ed", troughcolor="#f5f7fb", borderwidth=0, bordercolor="#f5f7fb", lightcolor="#dce1ed", darkcolor="#dce1ed")
        style.configure("TCombobox", padding=6, fieldbackground="white", background="white", bordercolor="#e1e5ee", arrowcolor="#808aa0")
        style.map("TCombobox", fieldbackground=[("readonly", "white")], selectbackground=[("readonly", "white")], selectforeground=[("readonly", "#334155")])
        style.configure("TCheckbutton", background="white", foreground="#7b849b", font=("Microsoft YaHei UI", 9))
        style.layout("Segment.TRadiobutton", [("Radiobutton.padding", {"children": [("Radiobutton.label", {"sticky": "nswe"})], "sticky": "nswe"})])
        style.configure("Segment.TRadiobutton", padding=(10, 10), background="#f0f2f8", foreground="#7b849b", anchor="center", font=("Microsoft YaHei UI", 10))
        style.map("Segment.TRadiobutton", background=[("selected", "#e5e8fc"), ("active", "#ebedf9")], foreground=[("selected", "#5865d8")])
        style.configure("Treeview", rowheight=40, background="white", fieldbackground="white", borderwidth=0)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9), background="#f0f2f8", foreground="#7b849b", relief="flat", padding=(8, 8))
        style.map("Treeview", background=[("selected", "#e9ecff")], foreground=[("selected", "#4e5aca")])

        header = tk.Frame(self, bg="#ffffff", height=76)
        header.pack(fill="x")
        tk.Label(header, text="知路", font=("Microsoft YaHei UI", 24, "bold"), fg="#26304c", bg="white").pack(side="left", padx=(26, 14), pady=16)
        tk.Label(header, text="把每一次理解，连成自己的知识地图。", font=("Microsoft YaHei UI", 10), fg="#8992a8", bg="white").pack(side="left")
        tk.Button(header, text=f"v{__version__}  ·  版本与更新", command=self.about,
                  fg="#7b849b", bg="white", activebackground="#eef0f8", activeforeground="#5865d8",
                  relief="flat", bd=0, cursor="hand2", padx=12, pady=8).pack(side="right", padx=16)

        maps_bar = ttk.Frame(self, padding=(16, 10, 16, 0))
        maps_bar.pack(fill="x")
        ttk.Label(maps_bar, text="学习空间", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left", padx=(0, 12))
        self.map_name = tk.StringVar()
        self.map_picker = ttk.Combobox(maps_bar, textvariable=self.map_name, state="readonly", width=24)
        self.map_picker.pack(side="left", padx=(0, 8))
        self.map_picker.bind("<<ComboboxSelected>>", self.switch_map)
        SoftButton(maps_bar, "＋ 新建地图", self.new_map, width=118).pack(side="left", padx=(0, 8))
        ttk.Button(maps_bar, text="地图设置", command=self.rename_map).pack(side="left")
        ttk.Button(maps_bar, text="外观设置", command=self.edit_appearance).pack(side="left", padx=(8, 0))
        self.theme = tk.StringVar(value=self.library.get(self.map_id)["theme"])
        theme_picker = ttk.Combobox(maps_bar, textvariable=self.theme, values=THEMES, state="readonly", width=11)
        theme_picker.pack(side="right")
        theme_picker.bind("<<ComboboxSelected>>", self.change_theme)
        ttk.Label(maps_bar, text="画布背景", foreground="#64748b").pack(side="right", padx=10)

        bar = ttk.Frame(self, padding=(16, 10))
        bar.pack(fill="x")
        for text, command, accent in (("＋ 添加内容", self.new_node, True), ("连接已有内容", self.relation_dialog, False), ("保存  Ctrl+S", self.save, False)):
            SoftButton(bar, text, command, primary=accent).pack(side="left", padx=(0, 8))
        operations = ttk.Menubutton(bar, text="地图操作  ▾")
        menu = tk.Menu(operations, tearoff=False, bg="white", fg="#334155", activebackground="#e9ecff", activeforeground="#5865d8", font=("Microsoft YaHei UI", 10))
        for text, command in (("导出当前地图", self.export_file), ("导入地图备份", self.import_file), ("撤销删除 / 导入", self.undo)):
            menu.add_command(label=text, command=command)
        operations.configure(menu=menu)
        operations.pack(side="right")
        self.progress_label = ttk.Label(bar, text="", foreground="#8992a8")
        self.progress_label.pack(side="right", padx=20)

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, padding=(18, 10), foreground="#64748b").pack(side="bottom", fill="x")
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=16)
        left, center, right = ttk.Frame(panes, width=235), ttk.Frame(panes), ttk.Frame(panes, width=330)
        panes.add(left, weight=0)
        panes.add(center, weight=1)
        panes.add(right, weight=0)

        ttk.Label(left, text="内容库", font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
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
        self.canvas.bind("<Configure>", lambda e: self.request_draw())
        self.canvas.bind("<ButtonPress-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_motion)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<Double-Button-1>", lambda e: self.edit_node() if any(t.startswith("node:") for t in self.canvas.gettags("current")) else None)
        self.canvas.bind("<ButtonPress-3>", self.canvas_press_right)
        self.canvas.bind("<B3-Motion>", self.canvas_motion)
        self.canvas.bind("<ButtonRelease-3>", self.canvas_release_right)
        self.canvas.bind("<MouseWheel>", self.zoom)
        self.canvas.bind("<Button-4>", lambda e: self.zoom(e, 1.1))
        self.canvas.bind("<Button-5>", lambda e: self.zoom(e, 1 / 1.1))
        ttk.Label(center, text="实线 → 前置依赖    紫虚线 → 进阶延伸    绿点线 — 相关内容", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(8, 2))
        ttk.Label(center, text="拖动模块调整位置 · 拖动空白平移 · 滚轮缩放 · 右键模块可删除", foreground="#94a3b8", font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(0, 10))

        detail_header = ttk.Frame(right)
        detail_header.pack(fill="x", pady=(0, 10))
        self.detail_title = ttk.Label(detail_header, text="内容详情", font=("Microsoft YaHei UI", 12, "bold"))
        self.detail_title.pack(side="left")
        ttk.Button(detail_header, text="完整编辑 ↗", command=self.edit_node).pack(side="right")
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
        bind_form_scroll(info, inspector)
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
        SoftButton(actions, "＋ 补充前置", lambda: self.new_node("before"), width=135).pack(side="left", expand=True, fill="x", padx=(0, 5))
        SoftButton(actions, "＋ 继续延伸", lambda: self.new_node("after"), width=135).pack(side="left", expand=True, fill="x")
        self.notebook.pack(fill="both", expand=True)

    def refresh_map_picker(self):
        self.map_choices = {m["title"]: m["id"] for m in self.library.maps()}
        self.map_picker.configure(values=list(self.map_choices))
        current = self.library.get(self.map_id)
        self.map_name.set(current["title"])
        self.theme.set(current["theme"])
        self.title(f"知路 v{__version__} · {current['title']}")

    def about(self):
        dialog = tk.Toplevel(self)
        dialog.title("关于知路")
        dialog.transient(self)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"知路  v{__version__}", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="把知识连成自己的学习路线", foreground="#64748b").pack(anchor="w", pady=(6, 18))
        ttk.Label(frame, text=f"学习数据保存在：\n{self.library.original.parent}", wraplength=420).pack(anchor="w")
        ttk.Label(frame, text="更新方式：关闭应用，下载新版本 EXE 并替换程序。\n打包版的地图与笔记保存在独立目录，不会被覆盖。\n从其他电脑迁移时，先导出地图备份。", wraplength=420).pack(anchor="w", pady=16)
        ttk.Button(frame, text="前往 GitHub 下载最新版本", command=lambda: webbrowser.open(RELEASE_URL)).pack(fill="x")

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
        self.kind_colors = self.library.kind_colors(map_id)
        self.border_width = self.library.border_width(map_id)
        self.selected = None
        self.loaded_form = None
        self.undo_stack = []
        self.drag = None
        self.guides = []
        self.menu_request = None
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
        def create(title, theme):
            map_id = self.library.create(title)
            self.library.set_theme(map_id, theme)
            self.open_map(map_id)
            self.status.set(f"已创建「{title.strip()}」，添加第一个内容开始学习。")
        return MapDialog(self, create)

    def rename_map(self):
        def update(title, theme):
            self.library.rename(self.map_id, title)
            self.library.set_theme(self.map_id, theme)
            self.refresh_map_picker()
            self.draw()
        return MapDialog(self, update, self.map_name.get(), self.theme.get(), rename=True)

    def change_theme(self, event=None):
        self.library.set_theme(self.map_id, self.theme.get())
        self.draw()

    def edit_appearance(self):
        def update(colors, border):
            self.library.set_kind_colors(self.map_id, colors)
            self.library.set_border_width(self.map_id, border)
            self.kind_colors = self.library.kind_colors(self.map_id)
            self.border_width = self.library.border_width(self.map_id)
            self.draw()
            self.status.set("已更新模块外观，只影响当前地图。")
        return AppearanceDialog(self, update, self.kind_colors, self.border_width, DEFAULT_COLORS, DEFAULT_BORDER)

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
        self.graph_nodes, self.graph_edges = nodes, self.store.edges()
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
            for edge in self.graph_edges:
                if self.selected in (edge["source"], edge["target"]):
                    neighbors.update((edge["source"], edge["target"]))
            self.visible &= neighbors
        self.positions = {n["id"]: (n["x"], n["y"]) for n in nodes}
        self.draw()
        completed = sum(n["state"] == "已完成" for n in nodes)
        self.progress_label.configure(text=f"{len(nodes)} 个内容   /   已完成 {completed}")
        self.status.set(f"{len(nodes)} 个模块 · {len(self.graph_edges)} 条关系 · 已完成 {completed} 个 · 当前显示 {len(self.visible)} 个")

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
        self.updated.configure(text=f"最近保存：{node['updated_at'].replace('T', ' ')}" if node else "点击「添加内容」，或载入示例地图。")
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
            self.status.set("先选择一个内容，再补充前置知识或继续延伸。")
            return
        if not self.ensure_saved():
            return
        anchor = self.store.node(self.selected) if relative else None

        def commit(data, existing, allow_duplicate):
            if existing is not None:
                if relative == "before":
                    self.store.add_edge(existing, anchor["id"], "前置依赖")
                else:
                    self.store.add_edge(anchor["id"], existing, "进阶延伸")
                nid = existing
            else:
                if not allow_duplicate and any(n["title"] == data["title"].strip() for n in self.store.nodes()):
                    raise ValueError("已有同名内容。可复用已有内容，或勾选允许同名后创建。")
                if anchor:
                    x, y = self.positions[anchor["id"]]
                    x += -270 if relative == "before" else 270
                else:
                    count = len(self.store.nodes())
                    x, y = 130 + (count % 3) * 270, 100 + (count // 3) * 140
                while any(abs(x-px) < 200 and abs(y-py) < 95 for px,py in self.positions.values()):
                    y += 140
                if anchor:
                    nid = self.store.create_connected_node(anchor["id"], relative, **data, x=x, y=y)
                else:
                    nid = self.store.create_node(**data, x=x, y=y)
            self.selected = nid
            self.clear_filters()
            self.load_detail()
            self.fit()
            self.status.set("已保存到地图：" + self.store.node(nid)["title"])

        candidates = [n for n in self.store.nodes() if not anchor or n["id"] != anchor["id"]]
        return ContentDialog(self, commit, relative=relative, anchor=anchor, candidates=candidates, colors=self.kind_colors)

    def edit_node(self, event=None):
        if not self.selected:
            self.status.set("先选择一个内容，再打开完整编辑器。")
            return
        if not self.ensure_saved():
            return
        node_id = self.selected
        def commit(data, existing, allow_duplicate):
            self.store.update_node(node_id, **data)
            self.refresh()
            self.status.set("内容与笔记已更新。")
        return ContentDialog(self, commit, node=self.store.node(node_id), colors=self.kind_colors)

    def relation_dialog(self):
        if not self.ensure_saved():
            return
        nodes = self.store.nodes()
        if len(nodes) < 2:
            self.status.set("先添加至少两个内容，就可以建立连接。")
            return
        def commit(source, target, kind):
            self.store.add_edge(source, target, kind)
            self.refresh()
        return RelationDialog(self, nodes, self.selected, commit)

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

    def request_draw(self):
        if self._draw_job is None:
            self._draw_job = self.after(16, self.draw)

    def destroy(self):
        # A pending redraw must not fire once the interpreter is torn down.
        if self._draw_job is not None:
            self.after_cancel(self._draw_job)
            self._draw_job = None
        super().destroy()

    def draw(self):
        if self._draw_job is not None:
            self.after_cancel(self._draw_job)
            self._draw_job = None
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
        edges = [e for e in self.graph_edges if e["source"] in self.visible and e["target"] in self.visible]
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
                color = (EDGE_COLORS_DARK if dark else EDGE_COLORS)[edge["kind"]]
                options = dict(fill=color, width=max(1, 1.8 * s), arrow="none" if edge["kind"] == "相关内容" else "last", arrowshape=(9, 11, 4), smooth=True)
                if edge["kind"] != "前置依赖":
                    options["dash"] = (7, 4) if edge["kind"] == "进阶延伸" else (2, 5)
                self.canvas.create_line(*start, *mid, *end, **options)
        for node in self.graph_nodes:
            nid = node["id"]
            if nid not in self.visible:
                continue
            x, y = self.transform(*self.positions[nid])
            w, h = NODE_HALF_WIDTH * s, NODE_HALF_HEIGHT * s
            tag = f"node:{nid}"
            kind_color = self.kind_colors.get(node["kind"], STATE_COLORS["未开始"])
            if dark:
                kind_color = lighten(kind_color, .35)
            state_color = (STATE_COLORS_DARK if dark else STATE_COLORS)[node["state"]]
            self.rounded_rect(x - w + 2, y - h + 5, x + w + 2, y + h + 5, 12 * s, fill=shadow, outline="", tags=tag)
            border = max(1.5, self.border_width * s)
            if nid == self.selected:
                # Selection is a ring outside the card, so the type colour stays readable.
                self.rounded_rect(x - w - 5 * s, y - h - 5 * s, x + w + 5 * s, y + h + 5 * s, 15 * s,
                                  fill="", outline="#6296ff", width=max(1.5, border * .8), tags=tag)
            self.rounded_rect(x - w, y - h, x + w, y + h, 12 * s, fill=card, outline=kind_color,
                              width=border, tags=tag)
            self.canvas.create_oval(x - w + 13*s, y + 23*s, x - w + 19*s, y + 29*s, fill=state_color, outline="", tags=tag)
            title = node["title"] if len(node["title"]) <= 24 else node["title"][:23] + "…"
            self.canvas.create_text(x, y - 11 * s, text=title, width=180 * s, font=("Microsoft YaHei UI", max(7, round(11 * s)), "bold"), fill="#edf3ff" if dark else "#1e293b", tags=tag)
            self.canvas.create_text(x, y + 26 * s, text=f"{node['kind']}  ·  {node['state']}", font=("Microsoft YaHei UI", max(6, round(9 * s))), fill=kind_color, tags=tag)
        for axis, value in self.guides:
            if axis == "v":
                position = value * s + self.offset_x
                self.canvas.create_line(position, 0, position, height, fill=GUIDE_COLOR, dash=(4, 4), tags="guide")
            else:
                position = value * s + self.offset_y
                self.canvas.create_line(0, position, width, position, fill=GUIDE_COLOR, dash=(4, 4), tags="guide")
        self.rounded_rect(10, 10, 132, 38, 8, fill=card, outline=grid)
        self.canvas.create_text(22, 24, anchor="w", text=f"{round(s * 100)}%  ·  {len(self.visible)} 个模块", fill=muted, font=("Microsoft YaHei UI", 9))

    def rounded_rect(self, x1, y1, x2, y2, radius, **options):
        r = min(radius, (x2-x1)/2, (y2-y1)/2)
        points = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2, x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return self.canvas.create_polygon(points, smooth=True, splinesteps=20, **options)

    def node_under(self, event):
        """Topmost module at a canvas position, found by geometry instead of hover state."""
        for item in reversed(self.canvas.find_overlapping(event.x - 1, event.y - 1, event.x + 1, event.y + 1)):
            tag = next((name for name in self.canvas.gettags(item) if name.startswith("node:")), None)
            if tag:
                return int(tag.split(":")[1])
        return None

    def canvas_press(self, event):
        current = self.canvas.find_withtag("current")
        tags = self.canvas.gettags(current[0]) if current else ()
        if "empty-action" in tags:
            self.clear_filters() if self.positions else self.new_node()
            return
        node_id = self.node_under(event)
        if node_id is None:
            self.pan_press(event)
        elif self.select(node_id):
            self.drag = ("node", node_id, event.x, event.y, *self.positions[node_id])

    def canvas_press_right(self, event):
        # Right-dragging empty canvas still pans; right-clicking a module opens its menu.
        node_id = self.node_under(event)
        if node_id is None:
            self.pan_press(event)
        else:
            self.menu_request = (node_id, event.x_root, event.y_root, event.x, event.y)

    def canvas_release_right(self, event):
        request, self.menu_request = self.menu_request, None
        self.drag = None
        self.canvas.configure(cursor="")
        if request and abs(event.x - request[3]) <= 4 and abs(event.y - request[4]) <= 4:
            self.open_node_menu(request[0], request[1], request[2])

    def node_menu(self):
        menu = tk.Menu(self, tearoff=False, bg="white", fg="#334155", activebackground="#e9ecff",
                       activeforeground="#5865d8", font=("Microsoft YaHei UI", 10))
        menu.add_command(label="完整编辑", command=self.edit_node)
        menu.add_command(label="＋ 补充前置", command=lambda: self.new_node("before"))
        menu.add_command(label="＋ 继续延伸", command=lambda: self.new_node("after"))
        menu.add_separator()
        menu.add_command(label="删除这个模块", command=self.delete_node)
        return menu

    def open_node_menu(self, node_id, x_root, y_root):
        if not self.select(node_id):
            return
        self.popup = self.node_menu()
        try:
            self.popup.tk_popup(x_root, y_root)
        finally:
            self.popup.grab_release()
            self.popup = None

    def pan_press(self, event):
        self.drag = ("pan", None, event.x, event.y, self.offset_x, self.offset_y)
        self.canvas.configure(cursor="fleur")

    def nearest_alignment(self, value, targets, offsets, tolerance):
        """Best guide for one axis. Centre alignment wins over an edge at equal distance."""
        best = None
        for target in targets:
            for offset in offsets:
                distance = abs(value + offset - target)
                rank = (round(distance, 6), abs(offset))
                if distance <= tolerance and (best is None or rank < best[0]):
                    best = (rank, target - offset, target)
        return best

    def snap_position(self, node_id, x, y):
        """Align a dragged module with its neighbours and report the guides to draw."""
        tolerance = GUIDE_TOLERANCE / self.scale_factor
        columns, rows = [], []
        for other, (ox, oy) in self.positions.items():
            if other == node_id or other not in self.visible:
                continue
            columns += [ox - NODE_HALF_WIDTH, ox, ox + NODE_HALF_WIDTH]
            rows += [oy - NODE_HALF_HEIGHT, oy, oy + NODE_HALF_HEIGHT]
        guides = []
        hit = self.nearest_alignment(x, columns, (-NODE_HALF_WIDTH, 0, NODE_HALF_WIDTH), tolerance)
        if hit:
            x, guides = hit[1], guides + [("v", hit[2])]
        hit = self.nearest_alignment(y, rows, (-NODE_HALF_HEIGHT, 0, NODE_HALF_HEIGHT), tolerance)
        if hit:
            y, guides = hit[1], guides + [("h", hit[2])]
        return (x, y), guides

    def canvas_motion(self, event):
        if not self.drag:
            return
        kind, nid, sx, sy, x, y = self.drag
        if kind == "node":
            moved = (x + (event.x - sx) / self.scale_factor, y + (event.y - sy) / self.scale_factor)
            self.positions[nid], self.guides = self.snap_position(nid, *moved)
        else:
            self.offset_x, self.offset_y = x + event.x - sx, y + event.y - sy
        self.request_draw()

    def canvas_release(self, event):
        if self.drag and self.drag[0] == "node":
            nid = self.drag[1]
            self.store.set_positions({nid: self.positions[nid]})
            self.guides = []
            self.request_draw()
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
        self.request_draw()

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
    parser.add_argument("--db", type=Path, help="指定 SQLite 数据文件")
    parser.add_argument("--smoke-test", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    if args.smoke_test and not args.db:
        parser.error("--smoke-test requires an isolated --db")
    database = args.db or prepare_data_dir() / "learning_map.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=database.parent / "app.log", encoding="utf-8", level=logging.ERROR)
    app = LearningMap(database)
    if args.smoke_test:
        import ctypes
        app.update()
        app.store.seed_demo()
        app.refresh()
        app.update()
        app.select(app.store.nodes()[0]["id"])
        editor = app.edit_node()
        editor.update()
        editor_visible = bool(editor.winfo_viewable())
        editor.texts["notes"].insert("end", "Packaged editor verification")
        editor.submit()
        result = {"version": __version__, "visible": bool(app.winfo_viewable()),
                  "console": ctypes.windll.kernel32.GetConsoleWindow(), "nodes": len(app.store.nodes()),
                  "editor": editor_visible and "Packaged editor verification" in app.store.node(app.selected)["notes"]}
        app.close()
        args.smoke_test.write_text(json.dumps(result), encoding="utf-8")
        return
    app.mainloop()


if __name__ == "__main__":
    main()
