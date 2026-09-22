"""Nonblocking paper workflow: task preparation, external exchange, preview, import."""
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dialogs import ACCENT, INK, MUTED, PAPER, Modal, SoftButton, bind_form_scroll, label, rounded
from paper_agent import (GOALS, SIZES, Cancelled, find_codex, load_task, parse_result,
                         prepare_task, read_json, result_snapshot, run_codex, write_json)
from storage import Store


class PaperDialog(Modal):
    def __init__(self, parent):
        super().__init__(parent, "从论文，走向理解", "连接 Codex 或外部 Agent，把论文转为可以继续编辑的学习地图。", 1040, 800)
        self.minsize(900, 700)
        self.task = None
        self.data = None
        self.busy = False
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self.poll_id = None
        self.imported = False
        self.pdf = tk.StringVar()
        self.goal = tk.StringVar(value=GOALS[1])
        self.background = tk.StringVar()
        self.size = tk.StringVar(value=list(SIZES)[1])
        self.codex = tk.StringVar()
        self.consent = tk.BooleanVar()
        self.title_var = tk.StringVar()
        self.progress = tk.StringVar(value="先选择论文和学习目标，也可以打开之前导出的任务包。")
        self.notebook = ttk.Notebook(self.body)
        self.notebook.pack(fill="both", expand=True)
        self.setup_tab = tk.Frame(self.notebook, bg="white")
        setup_scroll = ttk.Scrollbar(self.setup_tab, orient="vertical")
        setup_scroll.pack(side="right", fill="y")
        self.setup_canvas = tk.Canvas(self.setup_tab, bg="white", highlightthickness=0, yscrollcommand=setup_scroll.set)
        self.setup_canvas.pack(fill="both", expand=True)
        setup_scroll.configure(command=self.setup_canvas.yview)
        self.setup = tk.Frame(self.setup_canvas, bg="white", padx=20, pady=12)
        setup_id = self.setup_canvas.create_window(0, 0, window=self.setup, anchor="nw")
        self.setup.bind("<Configure>", lambda e: self.setup_canvas.configure(scrollregion=self.setup_canvas.bbox("all")))
        self.setup_canvas.bind("<Configure>", lambda e: self.setup_canvas.itemconfigure(setup_id, width=e.width))
        self.preview = tk.Frame(self.notebook, bg="white", padx=16, pady=12)
        self.notebook.add(self.setup_tab, text="  01  论文与 Agent  ")
        self.notebook.add(self.preview, text="  02  地图草稿  ")
        self.build_setup()
        bind_form_scroll(self.setup, self.setup_canvas)
        self.build_preview()
        self.progress_label = label(self.footer, "", 9, MUTED, wraplength=930)
        self.progress_label.configure(textvariable=self.progress)
        self.progress_label.pack(fill="x", pady=(0, 8))
        ttk.Style(self).configure("Paper.Horizontal.TProgressbar", troughcolor="#eef0f8", background=ACCENT, borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT)
        self.spinner = ttk.Progressbar(self.footer, mode="indeterminate", style="Paper.Horizontal.TProgressbar", maximum=100)
        self.spinner.pack(fill="x", pady=(0, 8))
        actions = tk.Frame(self.footer, bg="white")
        actions.pack(fill="x")
        SoftButton(actions, "保存为新地图", self.submit, True, 150).pack(side="right")
        SoftButton(actions, "关闭", self.cancel, width=70).pack(side="right", padx=8)
        ttk.Button(actions, text="停止分析", command=self.stop).pack(side="left")
        ttk.Button(actions, text="打开任务文件夹", command=self.open_folder).pack(side="left", padx=8)
        self.show()
        self.poll_id = self.after(150, self.poll)

    def build_setup(self):
        label(self.setup, "论文文件", bold=True).pack(anchor="w")
        row = tk.Frame(self.setup, bg="white")
        row.pack(fill="x", pady=(5, 10))
        ttk.Entry(row, textvariable=self.pdf).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="选择 PDF", command=self.choose_pdf).pack(side="left", padx=(8, 0))
        row = tk.Frame(self.setup, bg="white")
        row.pack(fill="x")
        for title, var, values in (("学习目标", self.goal, GOALS), ("地图规模", self.size, tuple(SIZES))):
            box = tk.Frame(row, bg="white")
            box.pack(side="left", expand=True, fill="x", padx=(0, 14))
            label(box, title, bold=True).pack(anchor="w")
            ttk.Combobox(box, textvariable=var, values=values, state="readonly").pack(fill="x", pady=5)
        label(self.setup, "我的基础", bold=True).pack(anchor="w", pady=(5, 4))
        ttk.Entry(self.setup, textvariable=self.background).pack(fill="x")
        label(self.setup, "例如：会 Python 和线性代数，希望理解方法并实现最小实验。", 9, MUTED).pack(anchor="w", pady=(4, 10))
        label(self.setup, "Codex 自动分析", bold=True).pack(anchor="w")
        row = tk.Frame(self.setup, bg="white")
        row.pack(fill="x", pady=5)
        ttk.Entry(row, textvariable=self.codex).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="选择 codex.exe", command=self.choose_codex).pack(side="left", padx=(8, 0))
        label(self.setup, "路径留空自动查找；需要安装并登录 Codex CLI。不会弹出 PowerShell。", 9, MUTED).pack(anchor="w")
        ttk.Checkbutton(self.setup, text="允许本次分析将论文内容交给 Codex（可能发送云端，并消耗账号额度）",
                        variable=self.consent).pack(anchor="w", pady=(8, 5))
        row = tk.Frame(self.setup, bg="white")
        row.pack(fill="x", pady=6)
        SoftButton(row, "用 Codex 分析", self.start_codex, True, 148).pack(side="left")
        ttk.Button(row, text="导出外部 Agent 任务包", command=self.export_task).pack(side="left", padx=10)
        ttk.Button(row, text="打开已有任务包", command=self.choose_task).pack(side="left")
        label(self.setup, "外部模式：把任务包交给豆包工作等 Agent，再到「地图草稿」导入结果。\n"
              "本版分析文字层，暂不含 OCR 和图表识别；支持 ≤50 MB、≤300 页、≤16 万字符。",
              9, MUTED, wraplength=850, justify="left").pack(anchor="w", pady=(5, 0))

    def build_preview(self):
        top = tk.Frame(self.preview, bg="white")
        top.pack(fill="x", pady=(0, 8))
        label(top, "新地图名称", bold=True).pack(side="left", padx=(0, 10))
        ttk.Entry(top, textvariable=self.title_var).pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="导入结果文件", command=self.import_result).pack(side="left", padx=8)
        self.tabs = ttk.Notebook(self.preview)
        self.tabs.pack(fill="both", expand=True)
        visual = tk.Frame(self.tabs, bg=PAPER)
        self.tabs.add(visual, text="地图预览")
        graph = tk.Frame(visual, bg=PAPER)
        graph.pack(fill="both", expand=True)
        vertical = ttk.Scrollbar(graph, orient="vertical")
        vertical.pack(side="right", fill="y")
        horizontal = ttk.Scrollbar(graph, orient="horizontal")
        horizontal.pack(side="bottom", fill="x")
        self.canvas = tk.Canvas(graph, bg="#f3f7fc", highlightthickness=0, height=200,
                                xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        vertical.configure(command=self.canvas.yview)
        horizontal.configure(command=self.canvas.xview)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.canvas.bind("<Configure>", lambda e: self.draw_preview())
        self.canvas.bind("<Button-1>", self.node_detail)
        self.detail = tk.Text(visual, height=6, wrap="word", font=("Microsoft YaHei UI", 10),
                              relief="flat", bg="white", fg=INK, padx=12, pady=8, state="disabled")
        self.detail.pack(side="bottom", fill="x", before=graph)
        raw = tk.Frame(self.tabs, bg="white")
        self.tabs.add(raw, text="粘贴结果 / 高级编辑")
        label(raw, "可粘贴 Agent 返回内容，或修改节点与连线，然后点击校验。", 9, MUTED).pack(anchor="w", pady=8)
        self.raw = tk.Text(raw, wrap="none", font=("Consolas", 10), undo=True)
        scrollbar = ttk.Scrollbar(raw, command=self.raw.yview)
        scrollbar.pack(side="right", fill="y")
        self.raw.configure(yscrollcommand=scrollbar.set)
        self.raw.pack(fill="both", expand=True)
        bottom = tk.Frame(self.preview, bg="white")
        bottom.pack(side="bottom", fill="x", pady=(8, 0), before=self.tabs)
        self.validate_button = ttk.Button(bottom, text="校验并刷新预览", command=self.apply_raw)
        self.validate_button.pack(side="left")
        ttk.Button(bottom, text="导出当前草稿", command=self.export_result).pack(side="left", padx=8)
        label(bottom, "滚动查看地图，点击节点阅读说明。", 9, MUTED).pack(side="right")

    def guard(self):
        if self.busy:
            self.failure("正在处理任务，请等待完成或先停止分析。")
            return False
        return True

    def choose_pdf(self):
        if not self.guard():
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("PDF 论文", "*.pdf")])
        if path:
            self.pdf.set(path)

    def choose_codex(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Codex", "codex.exe"), ("所有文件", "*")])
        if path:
            self.codex.set(path)

    def launch(self, work):
        if not self.guard():
            return
        self.busy = True
        self.error.set("")
        self.cancel_event = threading.Event()
        self.started = time.monotonic()
        self.stage = "准备任务…"
        self.spinner.start(12)
        self.progress.set(self.stage)
        def run():
            try:
                work(self.cancel_event, lambda s: self.events.put(("progress", s)))
            except Exception as error:
                self.events.put(("error", str(error) or type(error).__name__))
            finally:
                self.events.put(("done", None))
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def export_task(self):
        if not self.guard():
            return
        root = filedialog.askdirectory(parent=self, title="选择任务包保存位置（自动创建独立子目录）")
        if not root:
            return
        self.prepare(root, False)

    def start_codex(self):
        if not self.guard():
            return
        if not self.consent.get():
            self.failure("请先勾选允许将本次论文内容交给 Codex。")
            return
        try:
            executable = find_codex(self.codex.get())
        except ValueError as error:
            self.failure(error)
            return
        # Reuse a prepared task only if the visible settings still describe it.
        if self.task:
            try:
                manifest, _ = load_task(self.task)
                same = (self.pdf.get() == str(self.task / "paper.pdf") and self.goal.get() == manifest.get("goal")
                        and self.background.get() == manifest.get("background") and SIZES[self.size.get()] == manifest.get("target_nodes"))
            except (OSError, ValueError):
                same = False
            if same:
                task = self.task
                self.launch(lambda cancel, report: self.events.put(("result", run_codex(task, executable, cancel, report))))
                return
        self.prepare(self.parent.library.original.parent / "paper_tasks", True, executable)

    def prepare(self, root, automatic, executable=None):
        pdf, goal, background, count = self.pdf.get(), self.goal.get(), self.background.get(), SIZES[self.size.get()]
        def work(cancel, report):
            task, notice = prepare_task(pdf, root, goal, background, count, cancel, report)
            self.events.put(("task", (task, notice)))
            if automatic:
                result = run_codex(task, executable, cancel, report)
                self.events.put(("result", result))
        self.launch(work)

    def set_task(self, task, notice="任务已打开，可导入结果或用 Codex 分析。"):
        manifest, pages = load_task(task)
        self.task, self.manifest, self.pages = Path(task), manifest, pages
        self.pdf.set(str(self.task / "paper.pdf"))
        self.goal.set(manifest.get("goal", GOALS[1]))
        self.background.set(manifest.get("background", ""))
        self.size.set(next((k for k, v in SIZES.items() if v == manifest.get("target_nodes")), list(SIZES)[1]))
        self.data = None
        self.imported = False
        self.raw.delete("1.0", "end")
        self.title_var.set("")
        self.set_detail("等待分析结果。来源页码是 PDF 物理页码，可能与印刷页码不同。")
        self.draw_preview()
        self.stage = notice
        self.progress.set(notice)

    def choose_task(self):
        if not self.guard():
            return
        path = filedialog.askdirectory(parent=self, title="选择包含 manifest.json 的任务目录")
        if path:
            try:
                self.set_task(path)
                if (Path(path) / "result.json").exists():
                    self.accept_result(read_json(Path(path) / "result.json"))
            except (ValueError, OSError) as error:
                self.failure(error)

    def import_result(self):
        if not self.guard():
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("Agent 分析结果", "*.json")])
        if not path:
            return
        try:
            if not self.task:
                self.set_task(Path(path).parent)
            self.accept_result(read_json(path))
        except (OSError, ValueError) as error:
            self.failure(f"{error}\n请先打开这份结果对应的任务包。")

    def accept_result(self, data):
        if not self.task:
            raise ValueError("请先准备或打开对应的论文任务包。")
        snapshot, warnings = result_snapshot(data, self.manifest, self.pages)
        self.data, self.snapshot, self.warnings = data, snapshot, warnings
        self.raw.delete("1.0", "end")
        self.raw.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self.title_var.set(data["title"][:50])
        self.error.set("")
        self.imported = False
        self.stage = f"草稿：{len(data['nodes'])} 个模块 · {len(data['edges'])} 条关系 · {len(warnings)} 处摘录待核对。请检查内容后保存。"
        self.progress.set(self.stage)
        self.set_detail("\n".join(warnings) if warnings else "摘录已与论文文字核对；匹配不代表结论正确。点击节点查看学习任务和来源。")
        self.notebook.select(self.preview)
        self.tabs.select(0)
        self.draw_preview()

    def apply_raw(self):
        if not self.guard():
            return False
        try:
            title = self.title_var.get()
            self.accept_result(parse_result(self.raw.get("1.0", "end")))
            if title.strip():
                self.title_var.set(title)
            return True
        except (ValueError, OSError) as error:
            self.failure(error)
            return False

    def export_result(self):
        if not self.apply_raw():
            return
        path = filedialog.asksaveasfilename(parent=self, initialfile="result.json", defaultextension=".json", filetypes=[("分析草稿", "*.json")])
        if path:
            try:
                if Path(path).suffix.lower() != ".json":
                    raise ValueError("草稿请保存为 .json 文件，避免覆盖其他类型文件。")
                if self.task and Path(path).resolve() in {(self.task / n).resolve() for n in ("manifest.json", "pages.json", "result.schema.json")}:
                    raise ValueError("不能覆盖任务包元数据，请另选结果文件名。")
                write_json(path, self.data)
                self.progress.set("草稿已导出，下次打开任务包后可继续导入。")
            except (OSError, ValueError) as error:
                self.failure(error)

    def set_detail(self, text):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def draw_preview(self):
        self.canvas.delete("all")
        if not self.data:
            self.canvas.create_text(30, 35, text="论文分析结果将在这里呈现", fill=MUTED, anchor="w", font=("Microsoft YaHei UI", 12))
            return
        # DAG levels keep the preview consistent with the map's automatic layout.
        nodes = self.data["nodes"]
        levels = {n["id"]: 0 for n in nodes}
        for _ in nodes:
            for edge in self.data["edges"]:
                if edge["kind"] == "前置依赖":
                    levels[edge["target"]] = max(levels[edge["target"]], levels[edge["source"]] + 1)
        rows, positions = {}, {}
        for n in nodes:
            level = levels[n["id"]]
            row = rows.get(level, 0)
            rows[level] = row + 1
            positions[n["id"]] = (100 + level * 210, 45 + row * 90)
        width, height = max(x for x, y in positions.values()) + 100, max(y for x, y in positions.values()) + 45
        scale = 1
        self.canvas.configure(scrollregion=(0, 0, width + 20, height + 20))
        for edge in self.data["edges"]:
            a, b = positions[edge["source"]], positions[edge["target"]]
            dx, dy = b[0] - a[0], b[1] - a[1]
            fraction = min(90 / abs(dx) if dx else float("inf"), 30 / abs(dy) if dy else float("inf"))
            self.canvas.create_line((a[0]+dx*fraction)*scale+10, (a[1]+dy*fraction)*scale+10,
                                    (b[0]-dx*fraction)*scale+10, (b[1]-dy*fraction)*scale+10,
                                    fill="#acb8d0", arrow="none" if edge["kind"] == "相关内容" else "last")
        for index, node in enumerate(nodes):
            x, y = positions[node["id"]]
            x, y = x*scale+10, y*scale+10
            tag = f"paper-node:{index}"
            color = ACCENT if node["origin"] == "论文内容" else "#0d9488"
            rounded(self.canvas, x-90*scale, y-30*scale, x+90*scale, y+30*scale, max(3, 8*scale), fill="white", outline=color, width=1.5, tags=tag)
            self.canvas.create_text(x, y, text=node["title"][:22], width=170*scale, fill=INK,
                                    font=("Microsoft YaHei UI", max(6, round(10*scale))), tags=tag)

    def node_detail(self, event):
        for tag in self.canvas.gettags("current"):
            if tag.startswith("paper-node:") and self.data:
                node = self.data["nodes"][int(tag.split(":")[1])]
                refs = "\n".join(f"PDF 第 {s['page']} 页：{s['quote']}" for s in node["sources"])
                self.set_detail(f"{node['title']} · {node['origin']}\n{node['summary']}\n学习目标：{node['objective']}\n学习任务（AI 建议）：{node['task']}\n{refs}")

    def submit(self):
        if self.imported or not self.apply_raw():
            return
        if self.warnings and not messagebox.askyesno("仍有摘录待核对", "部分摘录无法在指定页匹配，节点会保留“待核对”标记。仍保存为新地图？", parent=self):
            return
        try:
            if not self.parent.ensure_saved():
                return
            map_id = self.parent.library.create(self.title_var.get(), snapshot=self.snapshot)
            self.parent.open_map(map_id)
            self.parent.status.set("论文草稿已保存为新地图。可编辑模块、调整关系并记录学习进度。")
            self.imported = True
            self.destroy()
        except (OSError, ValueError) as error:
            self.failure(error)

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                try:
                    if kind == "progress":
                        self.stage = value
                    elif kind == "task":
                        self.set_task(*value)
                    elif kind == "result":
                        self.accept_result(value)
                    elif kind == "error":
                        self.failure(value)
                        self.stage = value
                    elif kind == "done":
                        self.busy = False
                        self.spinner.stop()
                except (ValueError, OSError) as error:
                    self.failure(error)
                    self.stage = str(error)
        except queue.Empty:
            pass
        if hasattr(self, "stage"):
            suffix = f"  ·  已用 {int(time.monotonic() - self.started)} 秒" if self.busy else ""
            self.progress.set(self.stage + suffix)
        self.poll_id = self.after(150, self.poll)

    def stop(self):
        if self.busy:
            self.cancel_event.set()
            self.stage = "正在停止，请稍候…"

    def open_folder(self):
        if self.task and os.name == "nt":
            os.startfile(self.task)
        elif not self.task:
            self.failure("请先准备或打开任务包。")

    def cancel(self):
        if self.busy:
            self.stop()
            self.failure("正在停止分析，停止后可关闭。")
            return
        if self.raw.get("1.0", "end").strip() and not self.imported:
            if not messagebox.askyesno("关闭草稿", "尚未保存为地图。关闭会放弃窗口内的编辑；已导出的任务文件仍保留。继续关闭？", parent=self):
                return
        self.destroy()

    def destroy(self):
        self.cancel_event.set()
        if self.poll_id:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()
