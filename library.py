"""Map catalog. Each map has its own database; existing v1 data stays in place."""
import json
import math
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from storage import KINDS, Store

THEMES = ("晴空点阵", "暖纸网格", "午夜星空")
DEFAULT_COLORS = dict(zip(KINDS, ("#3b82f6", "#8b5cf6", "#0d9488", "#ea580c")))
COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}")
DEFAULT_BORDER, BORDER_RANGE = 2.5, (1.0, 6.0)


class MapLibrary:
    def __init__(self, original_database):
        self.original = Path(original_database).resolve()
        self.original.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.original.with_suffix(".library.db"))
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS maps (id TEXT PRIMARY KEY, title TEXT NOT NULL UNIQUE, theme TEXT NOT NULL, colors TEXT NOT NULL DEFAULT '{}', border REAL NOT NULL DEFAULT 2.5)")
            self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            # Maps created before appearance settings existed keep working; both columns are additive.
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(maps)")}
            if "colors" not in columns:
                self.db.execute("ALTER TABLE maps ADD COLUMN colors TEXT NOT NULL DEFAULT '{}'")
            if "border" not in columns:
                self.db.execute("ALTER TABLE maps ADD COLUMN border REAL NOT NULL DEFAULT 2.5")
            self.db.execute("INSERT OR IGNORE INTO maps (id,title,theme) VALUES ('default', '我的第一张地图', ?)", (THEMES[0],))
            self.db.execute("INSERT OR IGNORE INTO settings VALUES ('active', 'default')")

    def maps(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM maps ORDER BY rowid")]

    def get(self, map_id):
        row = self.db.execute("SELECT * FROM maps WHERE id=?", (map_id,)).fetchone()
        if row is None:
            raise ValueError("地图不存在。")
        return dict(row)

    @property
    def active_id(self):
        return self.db.execute("SELECT value FROM settings WHERE key='active'").fetchone()[0]

    def activate(self, map_id):
        self.get(map_id)
        with self.db:
            self.db.execute("UPDATE settings SET value=? WHERE key='active'", (map_id,))

    def path(self, map_id):
        self.get(map_id)
        if map_id == "default":
            return self.original
        # IDs are generated internally, never interpreted as user supplied paths.
        if len(map_id) != 32 or any(c not in "0123456789abcdef" for c in map_id):
            raise ValueError("地图标识无效。")
        return self.original.parent / (self.original.stem + "_maps") / (map_id + ".db")

    def validate_title(self, title, except_id=None):
        if not isinstance(title, str) or not title.strip():
            raise ValueError("地图名称不能为空。")
        title = title.strip()
        if len(title) > 50:
            raise ValueError("地图名称最多 50 个字符。")
        if any(m["id"] != except_id and m["title"].casefold() == title.casefold() for m in self.maps()):
            raise ValueError("已有同名地图，请换一个名称。")
        return title

    def create(self, title, snapshot=None):
        title = self.validate_title(title)
        if snapshot is not None:
            Store.validate_snapshot(snapshot)
        map_id = uuid4().hex
        path = None
        try:
            with self.db:
                self.db.execute("INSERT INTO maps (id,title,theme) VALUES (?,?,?)", (map_id, title, THEMES[0]))
                path = self.path(map_id)
                store = Store(path)
                try:
                    if snapshot is not None:
                        store.restore(snapshot)
                        store.layout()
                finally:
                    store.close()
        except Exception:
            if path is not None:
                path.unlink(missing_ok=True)
            raise
        return map_id

    def rename(self, map_id, title):
        self.get(map_id)
        title = self.validate_title(title, map_id)
        with self.db:
            self.db.execute("UPDATE maps SET title=? WHERE id=?", (title, map_id))

    def set_theme(self, map_id, theme):
        self.get(map_id)
        if theme not in THEMES:
            raise ValueError("未知的地图背景。")
        with self.db:
            self.db.execute("UPDATE maps SET theme=? WHERE id=?", (theme, map_id))

    def kind_colors(self, map_id):
        """Content-type colours for one map, always complete and safe to draw with."""
        try:
            stored = json.loads(self.get(map_id)["colors"] or "{}")
        except (ValueError, TypeError):
            stored = {}
        colors = dict(DEFAULT_COLORS)
        if isinstance(stored, dict):
            for kind, value in stored.items():
                if kind in KINDS and isinstance(value, str) and COLOR_PATTERN.fullmatch(value):
                    colors[kind] = value.lower()
        return colors

    def set_kind_colors(self, map_id, colors):
        self.get(map_id)
        clean = {}
        for kind, value in colors.items():
            if kind not in KINDS:
                raise ValueError("未知的内容类型。")
            if not isinstance(value, str) or not COLOR_PATTERN.fullmatch(value):
                raise ValueError("颜色必须是 #RRGGBB 格式。")
            clean[kind] = value.lower()
        with self.db:
            self.db.execute("UPDATE maps SET colors=? WHERE id=?", (json.dumps(clean, sort_keys=True), map_id))

    def border_width(self, map_id):
        """Module border thickness for one map, always a value that is safe to draw with."""
        value = self.get(map_id)["border"]
        low, high = BORDER_RANGE
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            return DEFAULT_BORDER
        return round(float(value), 2)

    def set_border_width(self, map_id, value):
        self.get(map_id)
        low, high = BORDER_RANGE
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"边框粗细需要是 {low:g} 到 {high:g} 之间的数字。")
        with self.db:
            self.db.execute("UPDATE maps SET border=? WHERE id=?", (float(value), map_id))

    def close(self):
        self.db.close()
