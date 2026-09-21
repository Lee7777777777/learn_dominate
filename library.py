"""Map catalog. Each map has its own database; existing v1 data stays in place."""
import sqlite3
from pathlib import Path
from uuid import uuid4

from storage import Store

THEMES = ("晴空点阵", "暖纸网格", "午夜星空")


class MapLibrary:
    def __init__(self, original_database):
        self.original = Path(original_database).resolve()
        self.original.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.original.with_suffix(".library.db"))
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute("CREATE TABLE IF NOT EXISTS maps (id TEXT PRIMARY KEY, title TEXT NOT NULL UNIQUE, theme TEXT NOT NULL)")
            self.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self.db.execute("INSERT OR IGNORE INTO maps VALUES ('default', '我的第一张地图', ?)", (THEMES[0],))
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

    def create(self, title):
        title = self.validate_title(title)
        map_id = uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO maps VALUES (?,?,?)", (map_id, title, THEMES[0]))
            Store(self.path(map_id)).close()
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

    def close(self):
        self.db.close()
