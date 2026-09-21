"""Consistent content editors, with inline validation and contextual previews."""
import tkinter as tk
from tkinter import ttk

from library import THEMES
from storage import KINDS, STATES, MASTERY, RELATIONS

INK = "#202943"
MUTED = "#7b849b"
ACCENT = "#5865d8"
PAPER = "#f5f6fb"


def label(parent, text, size=10, color=INK, bold=False, bg="white", **options):
    return tk.Label(parent, text=text, font=("Microsoft YaHei UI", size, "bold" if bold else "normal"),
                    fg=color, bg=bg, anchor="w", **options)


def rounded(canvas, x1, y1, x2, y2, r=12, **options):
    return canvas.create_polygon(x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,
                                 x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1, smooth=True, splinesteps=20, **options)


def bind_form_scroll(frame, canvas):
    def scroll(event):
        amount = (-1 if event.delta > 0 else 1) if getattr(event, "delta", 0) else (-1 if event.num == 4 else 1)
        canvas.yview_scroll(amount * 2, "units")
        return "break"
    for widget in (frame, *frame.winfo_children()):
        if isinstance(widget, (tk.Text, ttk.Combobox)):
            continue
        for event in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(event, scroll)
        if widget is not frame:
            bind_form_scroll(widget, canvas)


class SoftButton(tk.Canvas):
    def __init__(self, parent, text, command, primary=False, width=130):
        super().__init__(parent, width=width, height=40, highlightthickness=0,
                         bg=parent.cget("background") if isinstance(parent, tk.Frame) else PAPER,
                         takefocus=True, cursor="hand2")
        self.text, self.command, self.primary = text, command, primary
        self.hover = False
        self.bind("<Configure>", self.paint)
        self.bind("<Enter>", lambda e: self.set_hover(True))
        self.bind("<Leave>", lambda e: self.set_hover(False))
        self.bind("<ButtonRelease-1>", lambda e: self.invoke())
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<FocusIn>", self.paint)
        self.bind("<FocusOut>", self.paint)

    def set_hover(self, value):
        self.hover = value
        self.paint()

    def paint(self, event=None):
        self.delete("all")
        color = ("#4955c5" if self.hover else ACCENT) if self.primary else ("#e8eaf6" if self.hover else "#edf0f8")
        rounded(self, 1, 1, self.winfo_width()-1, 39, 10, fill=color,
                outline=ACCENT if self.focus_get() == self else "")
        self.create_text(self.winfo_width()/2, 20, text=self.text,
                         font=("Microsoft YaHei UI", 10, "bold"), fill="white" if self.primary else INK)

    def invoke(self):
        self.command()


class Modal(tk.Toplevel):
    def __init__(self, parent, title, subtitle, width=860, height=680):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.transient(parent)
        self.configure(bg=PAPER)
        self.resizable(True, True)
        self.minsize(min(width, 720), min(height, 540))
        self.parent = parent
        top = tk.Frame(self, bg="white", padx=28, pady=22)
        top.pack(fill="x")
        label(top, "Z H I L U   /   学习空间", 9, ACCENT, True).pack(anchor="w", pady=(0, 8))
        label(top, title, 21, bold=True).pack(anchor="w")
        label(top, subtitle, 10, MUTED, wraplength=760).pack(anchor="w", pady=(6, 0))
        self.footer = tk.Frame(self, bg="white", padx=24, pady=14)
        self.footer.pack(side="bottom", fill="x")
        self.error = tk.StringVar()
        self.error_label = tk.Label(self.footer, textvariable=self.error, fg="#c14b61", bg="white",
                                    font=("Microsoft YaHei UI", 9), anchor="w", wraplength=480)
        self.error.trace_add("write", self.update_error)
        self.body = tk.Frame(self, bg=PAPER, padx=24, pady=20)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<Control-Return>", lambda e: self.submit())
        self.bind("<Control-s>", lambda e: self.submit())
        self.geometry(f"{width}x{height}")

    def show(self, focus=None):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width()-w)//2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height()-h)//2
        self.geometry(f"+{max(0, min(x, self.winfo_screenwidth()-w))}+{max(0, min(y, self.winfo_screenheight()-h-50))}")
        self.deiconify()
        self.grab_set()
        (focus or self).focus_set()

    def actions(self, caption="保存内容"):
        self.submit_button = SoftButton(self.footer, caption, self.submit, primary=True, width=148)
        self.submit_button.pack(side="right")
        SoftButton(self.footer, "取消", self.cancel, width=80).pack(side="right", padx=(0, 10))

    def update_error(self, *args):
        if self.error.get():
            siblings = [w for w in self.footer.pack_slaves() if w != self.error_label]
            options = {"before": siblings[0]} if siblings else {}
            self.error_label.pack(side="top", fill="x", pady=(0, 8), **options)
        else:
            self.error_label.pack_forget()

    def cancel(self):
        if getattr(self, "initial", None) is not None and self.values() != self.initial:
            # Keep unfinished input visible and require an explicit discard click.
            if not getattr(self, "discard_armed", False):
                self.discard_armed = True
                self.error.set("内容尚未保存。再次点击取消或按 Esc 可放弃；也可继续编辑。")
                return
        self.destroy()

    def failure(self, error):
        self.error.set(str(error))
        self.error_label.configure(fg="#c14b61")


class MapDialog(Modal):
    def __init__(self, parent, callback, initial_name="", initial_theme=THEMES[0], rename=False):
        super().__init__(parent, "为学习开启一个新空间" if not rename else "给地图一个好名字",
                         "每张地图独立保存，已有的知识和笔记会一直保留。", width=720, height=540)
        self.callback, self.rename = callback, rename
        card = tk.Frame(self.body, bg="white", padx=22, pady=18)
        card.pack(fill="both", expand=True)
        label(card, "地图名称", 10, bold=True).pack(anchor="w", pady=(0, 8))
        self.name = tk.StringVar(value=initial_name)
        entry = ttk.Entry(card, textvariable=self.name, font=("Microsoft YaHei UI", 13))
        entry.pack(fill="x", ipady=5)
        label(card, "例如：深度学习入门 / 毕业论文 / 数学基础", 9, MUTED).pack(anchor="w", pady=(8, 20))
        self.theme = tk.StringVar(value=initial_theme)
        label(card, "选择一种学习氛围", 10, bold=True).pack(anchor="w", pady=(0, 10))
        row = tk.Frame(card, bg="white")
        row.pack(fill="x")
        for title in THEMES:
            ttk.Radiobutton(row, text=title, value=title, variable=self.theme, style="Segment.TRadiobutton").pack(side="left", expand=True, fill="x", padx=(0, 8))
        self.actions("保存设置" if rename else "创建空白地图")
        self.initial = self.values()
        self.show(entry)

    def values(self):
        return self.name.get(), self.theme.get()

    def submit(self):
        try:
            self.callback(*self.values())
        except (ValueError, OSError) as error:
            self.failure(error)
            return
        self.destroy()


class ContentDialog(Modal):
    def __init__(self, parent, callback, node=None, relative=None, anchor=None, candidates=()):
        title = "编辑与补充内容" if node else {"before": "补充前置知识", "after": "探索下一步"}.get(relative, "添加一个新的学习内容")
        subtitle = "把目标、笔记和资料放在一起，让每个知识点更完整。"
        if anchor:
            subtitle = f"围绕「{anchor['title'][:48]}」完善你的学习路线。"
        super().__init__(parent, title, subtitle, height=730)
        self.callback, self.editing, self.relative, self.anchor = callback, node is not None, relative, anchor
        self.mode = tk.StringVar(value="new")
        self.keep_adding = tk.BooleanVar(value=False)
        self.allow_duplicate = tk.BooleanVar(value=False)
        self.existing = {f"{n['title']}  ·  #{n['id']}": n["id"] for n in candidates}
        self.existing_choice = tk.StringVar(value=next(iter(self.existing), ""))
        defaults = dict(title="", kind=KINDS[0], state=STATES[0], mastery=MASTERY[0], tags="", summary="", notes="", resources="")
        defaults.update(node or {})
        self.fields = {k: tk.StringVar(value=defaults[k]) for k in ("title", "kind", "state", "mastery", "tags")}
        self.texts = {}
        self.preview = tk.Canvas(self.body, width=235, highlightthickness=0, bg=PAPER)
        self.preview.pack(side="right", fill="y", padx=(18, 0))
        left = tk.Frame(self.body, bg=PAPER)
        left.pack(fill="both", expand=True)
        if relative:
            modes = tk.Frame(left, bg=PAPER)
            modes.pack(fill="x", pady=(0, 12))
            for value, text in (("new", "创建新内容"), ("existing", "复用已有内容")):
                ttk.Radiobutton(modes, text=text, variable=self.mode, value=value, command=self.change_mode,
                                style="Segment.TRadiobutton").pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.editor = ttk.Notebook(left)
        basic_page = tk.Frame(self.editor, bg="white")
        form_canvas = tk.Canvas(basic_page, bg="white", highlightthickness=0, width=360)
        form_scroll = ttk.Scrollbar(basic_page, command=form_canvas.yview)
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_scroll.pack(side="right", fill="y")
        form_canvas.pack(side="left", fill="both", expand=True)
        basic = tk.Frame(form_canvas, bg="white", padx=20, pady=16)
        form_window = form_canvas.create_window(0, 0, window=basic, anchor="nw")
        basic.bind("<Configure>", lambda e: form_canvas.configure(scrollregion=form_canvas.bbox("all")))
        form_canvas.bind("<Configure>", lambda e: form_canvas.itemconfigure(form_window, width=e.width))
        self.editor.add(basic_page, text="01  内容信息")
        notes = tk.Frame(self.editor, bg="white", padx=20, pady=16)
        self.editor.add(notes, text="02  笔记与资料")
        self.editor.pack(fill="both", expand=True)
        label(basic, "你想学习什么？", 11, bold=True).pack(anchor="w", pady=(0, 8))
        self.title_entry = ttk.Entry(basic, textvariable=self.fields["title"], font=("Microsoft YaHei UI", 12))
        self.title_entry.pack(fill="x", ipady=3)
        label(basic, "内容类型", 9, MUTED).pack(anchor="w", pady=(16, 8))
        types = tk.Frame(basic, bg="white")
        types.pack(fill="x")
        for kind in KINDS:
            ttk.Radiobutton(types, text=kind, value=kind, variable=self.fields["kind"], style="Segment.TRadiobutton").pack(side="left", fill="x", expand=True, padx=(0, 4))
        row = tk.Frame(basic, bg="white")
        row.pack(fill="x", pady=(16, 12))
        for key, text, options in (("state", "学习状态", STATES), ("mastery", "掌握程度", MASTERY)):
            column = tk.Frame(row, bg="white")
            column.pack(side="left", fill="x", expand=True, padx=(0, 8))
            label(column, text, 9, MUTED).pack(anchor="w", pady=(0, 6))
            ttk.Combobox(column, textvariable=self.fields[key], values=options, state="readonly", width=13).pack(fill="x")
        label(basic, "学习目标 / 简介", 9, MUTED).pack(anchor="w", pady=(0, 6))
        self.texts["summary"] = self.text_field(basic, defaults["summary"], 3)
        label(basic, "标签  ·  用逗号分隔", 9, MUTED).pack(anchor="w", pady=(12, 6))
        ttk.Entry(basic, textvariable=self.fields["tags"]).pack(fill="x")
        if not self.editing:
            ttk.Checkbutton(basic, text="允许同名内容（作为独立模块）", variable=self.allow_duplicate).pack(anchor="w", pady=(10, 0))
        bind_form_scroll(basic, form_canvas)
        label(notes, "学习笔记", 11, bold=True).pack(anchor="w", pady=(0, 6))
        label(notes, "记录理解、疑问，或下一步要验证的想法。", 9, MUTED).pack(anchor="w", pady=(0, 8))
        self.texts["notes"] = self.text_field(notes, defaults["notes"], 7, expand=True)
        label(notes, "参考资料  ·  每行一个链接或文件路径", 9, MUTED).pack(anchor="w", pady=(14, 8))
        self.texts["resources"] = self.text_field(notes, defaults["resources"], 3)
        self.reuse = tk.Frame(left, bg="white", padx=20, pady=24)
        label(self.reuse, "连接已有知识", 13, bold=True).pack(anchor="w")
        label(self.reuse, "直接复用笔记和进度，不重复创建模块。", 9, MUTED, wraplength=350).pack(anchor="w", pady=(8, 20))
        ttk.Combobox(self.reuse, values=list(self.existing), textvariable=self.existing_choice, state="readonly").pack(fill="x")
        if not self.existing:
            label(self.reuse, "当前没有其他可连接的内容，请先创建。", 10, "#c14b61", wraplength=330).pack(pady=18)
        if not self.editing:
            ttk.Checkbutton(self.footer, text="保存后继续添加", variable=self.keep_adding).pack(side="left")
        self.actions("保存修改" if self.editing else "添加到地图")
        for var in (*self.fields.values(), self.existing_choice):
            var.trace_add("write", lambda *a: self.render_preview())
        self.preview.bind("<Configure>", lambda e: self.render_preview())
        self.initial = self.values()
        self.show(self.title_entry)
        self.render_preview()

    @staticmethod
    def text_field(parent, content, height, expand=False):
        frame = tk.Frame(parent, bg="white")
        frame.pack(fill="both" if expand else "x", expand=expand)
        text = tk.Text(frame, height=height, width=20, wrap="word", undo=True, relief="flat",
                       highlightthickness=1, highlightbackground="#e2e6f0", highlightcolor=ACCENT,
                       font=("Microsoft YaHei UI", 10), bg="#fafbfe", fg=INK, padx=10, pady=8)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.insert("1.0", content)
        return text

    def values(self):
        data = {k: v.get() for k, v in self.fields.items()}
        data.update({k: text.get("1.0", "end-1c") for k, text in self.texts.items()})
        return data, self.mode.get(), self.existing_choice.get()

    def change_mode(self):
        self.editor.pack_forget()
        self.reuse.pack_forget()
        (self.reuse if self.mode.get() == "existing" else self.editor).pack(fill="both", expand=True)
        self.error.set("")
        self.render_preview()

    def render_preview(self):
        c = self.preview
        c.delete("all")
        c.create_text(12, 16, anchor="w", text="地图预览", fill=MUTED, font=("Microsoft YaHei UI", 10))
        title = self.fields["title"].get().strip() or "新的学习内容"
        if self.mode.get() == "existing":
            title = self.existing_choice.get().rsplit("  ·  #", 1)[0] or "选择已有内容"
        def card(y, text, active=False):
            rounded(c, 10, y+3, 225, y+87, fill="#e3e6f2", outline="")
            rounded(c, 8, y, 223, y+84, fill="white", outline=ACCENT if active else "#dfe4ef", width=1.5)
            c.create_text(24, y+29, text=text[:36], anchor="w", width=185, fill=INK, font=("Microsoft YaHei UI", 10, "bold"))
            c.create_text(24, y+66, anchor="w", text=(self.fields["kind"].get()+"  /  "+self.fields["state"].get()) if active else "当前内容", fill=ACCENT if active else MUTED, font=("Microsoft YaHei UI", 8))
        card(48, title if self.relative != "after" else self.anchor["title"], self.relative != "after")
        if self.anchor:
            c.create_line(116, 142, 116, 184, arrow="last", fill=ACCENT, width=2, dash=(4,3) if self.relative=="after" else ())
            card(196, title if self.relative == "after" else self.anchor["title"], self.relative=="after")
            hint = "先掌握新内容\n再学习当前内容" if self.relative=="before" else "学完当前内容\n继续向下一步探索"
            c.create_text(116, 320, text=hint, fill=MUTED, width=205, justify="center", font=("Microsoft YaHei UI", 10))
        else:
            c.create_text(18, 164, anchor="nw", text="先记录一个想法，\n再逐步补全它的连接。\n\n笔记和资料可以现在填写，\n也可以在学习过程中继续补充。", fill=MUTED, width=210, font=("Microsoft YaHei UI", 10))
        if c.winfo_height() > 380:
            c.create_text(18, c.winfo_height()-18, anchor="w", text="Ctrl + Enter  快速保存", fill=MUTED, font=("Microsoft YaHei UI", 9))

    def submit(self):
        data, mode, choice = self.values()
        if mode == "existing" and choice not in self.existing:
            self.failure("请选择一个已有内容。")
            return
        if mode == "new" and not data["title"].strip():
            self.failure("给这个内容起一个名字后，就可以保存了。")
            self.editor.select(0)
            self.title_entry.focus_set()
            return
        try:
            self.callback(data, self.existing[choice] if mode == "existing" else None, self.allow_duplicate.get())
        except (ValueError, OSError) as error:
            self.failure(error)
            return
        if self.keep_adding.get() and not self.editing:
            for key in ("title", "tags"):
                self.fields[key].set("")
            for text in self.texts.values():
                text.delete("1.0", "end")
            self.allow_duplicate.set(False)
            self.initial = self.values()
            self.discard_armed = False
            self.error_label.configure(fg="#188c73")
            self.error.set("已保存到地图，可以继续添加下一个内容。")
            self.title_entry.focus_set()
        else:
            self.destroy()


class RelationDialog(Modal):
    def __init__(self, parent, nodes, selected, callback):
        super().__init__(parent, "让两个知识点产生连接", "选择内容与关系，下面会实时解释它们的学习顺序。", width=740, height=570)
        self.callback = callback
        self.choices = {f"{n['title']}  ·  #{n['id']}": n["id"] for n in nodes}
        values = list(self.choices)
        index = next((i for i, n in enumerate(nodes) if n['id'] == selected), 0)
        self.source = tk.StringVar(value=values[index])
        self.target = tk.StringVar(value=values[(index+1)%len(values)])
        self.kind = tk.StringVar(value=RELATIONS[0])
        card = tk.Frame(self.body, bg="white", padx=24, pady=20)
        card.pack(fill="both", expand=True)
        for text, var in (("从这个内容", self.source), ("连接到", self.target)):
            label(card, text, 10, bold=True).pack(anchor="w", pady=(0, 7))
            ttk.Combobox(card, textvariable=var, values=values, state="readonly").pack(fill="x", pady=(0, 16))
        row = tk.Frame(card, bg="white")
        row.pack(fill="x")
        for kind in RELATIONS:
            ttk.Radiobutton(row, text=kind, variable=self.kind, value=kind, style="Segment.TRadiobutton").pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.explanation = label(card, "", 10, ACCENT, wraplength=610, justify="left")
        self.explanation.pack(anchor="w", pady=18)
        for var in (self.source, self.target, self.kind):
            var.trace_add("write", lambda *a: self.describe())
        self.actions("建立连接")
        self.describe()
        self.show()

    def describe(self):
        a, b = self.source.get().rsplit("  ·  #", 1)[0], self.target.get().rsplit("  ·  #", 1)[0]
        text = {"前置依赖": f"先学习「{a}」，再学习「{b}」。", "进阶延伸": f"学完「{a}」后，可以继续探索「{b}」。", "相关内容": f"「{a}」与「{b}」相互关联，不限定学习顺序。"}
        self.explanation.configure(text=text[self.kind.get()])

    def submit(self):
        try:
            self.callback(self.choices[self.source.get()], self.choices[self.target.get()], self.kind.get())
        except ValueError as error:
            self.failure(error)
            return
        self.destroy()
