"""SQLite persistence and graph rules, independent from the UI."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

KINDS = ("知识点", "论文", "课程", "实践")
STATES = ("未开始", "学习中", "已完成")
MASTERY = ("待评估", "不熟悉", "基本理解", "熟练")
RELATIONS = ("前置依赖", "进阶延伸", "相关内容")
NODE_FIELDS = ("title", "kind", "state", "mastery", "summary", "notes", "resources", "tags", "x", "y")


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT '知识点', state TEXT NOT NULL DEFAULT '未开始',
                mastery TEXT NOT NULL DEFAULT '待评估', summary TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '', resources TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '', x REAL NOT NULL DEFAULT 100,
                y REAL NOT NULL DEFAULT 100, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                target INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                kind TEXT NOT NULL, UNIQUE(source, target, kind), CHECK(source <> target)
            );
        """)

    def nodes(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM nodes ORDER BY id")]

    def edges(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM edges ORDER BY id")]

    def node(self, node_id):
        row = self.db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def validate_node(data):
        if not isinstance(data.get("title"), str) or not data["title"].strip():
            raise ValueError("模块名称不能为空。")
        for key, values in (("kind", KINDS), ("state", STATES), ("mastery", MASTERY)):
            if data.get(key) not in values:
                raise ValueError(f"无效的模块字段：{key}")
        for key in ("summary", "notes", "resources", "tags"):
            if not isinstance(data.get(key), str):
                raise ValueError(f"字段 {key} 必须是文本。")
        for key in ("x", "y"):
            value = data.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e7:
                raise ValueError("节点位置无效或超出范围。")

    def _insert_node(self, title, **values):
        data = dict(title=title, kind=KINDS[0], state=STATES[0], mastery=MASTERY[0],
                    summary="", notes="", resources="", tags="", x=100, y=100)
        data.update(values)
        self.validate_node(data)
        data["title"] = data["title"].strip()
        cur = self.db.execute(
            f"INSERT INTO nodes ({','.join(NODE_FIELDS)},updated_at) VALUES ({','.join('?' for _ in range(11))})",
            [data[k] for k in NODE_FIELDS] + [datetime.now().isoformat(timespec="seconds")])
        return cur.lastrowid

    def create_node(self, title, **values):
        with self.db:
            return self._insert_node(title, **values)

    def create_connected_node(self, anchor, relative, title, **values):
        if not self.node(anchor) or relative not in ("before", "after"):
            raise ValueError("要补充的内容已不存在，请重新选择。")
        with self.db:
            nid = self._insert_node(title, **values)
            source, target, kind = (nid, anchor, "前置依赖") if relative == "before" else (anchor, nid, "进阶延伸")
            self.db.execute("INSERT INTO edges(source,target,kind) VALUES (?,?,?)", (source, target, kind))
        return nid

    def update_node(self, node_id, **values):
        data = self.node(node_id)
        if data is None:
            raise ValueError("模块不存在。")
        data.update({k: v for k, v in values.items() if k in NODE_FIELDS})
        self.validate_node(data)
        data["title"] = data["title"].strip()
        with self.db:
            self.db.execute(f"UPDATE nodes SET {','.join(k + '=?' for k in NODE_FIELDS)},updated_at=? WHERE id=?",
                            [data[k] for k in NODE_FIELDS] + [datetime.now().isoformat(timespec="seconds"), node_id])

    @staticmethod
    def would_cycle(edges, source, target):
        adjacency = {}
        for edge in edges:
            if edge["kind"] == "前置依赖":
                adjacency.setdefault(edge["source"], []).append(edge["target"])
        pending, seen = [target], set()
        while pending:
            current = pending.pop()
            if current == source:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(adjacency.get(current, []))
        return False

    def add_edge(self, source, target, kind):
        if kind not in RELATIONS:
            raise ValueError("未知的关系类型。")
        if source == target:
            raise ValueError("不能将模块连接到自身。")
        if not self.node(source) or not self.node(target):
            raise ValueError("连接的模块不存在。")
        if kind == "相关内容" and source > target:
            source, target = target, source
        if kind == "前置依赖" and self.would_cycle(self.edges(), source, target):
            raise ValueError("这条前置依赖会形成循环，无法确定学习顺序。")
        try:
            with self.db:
                self.db.execute("INSERT INTO edges(source,target,kind) VALUES (?,?,?)", (source, target, kind))
        except sqlite3.IntegrityError as error:
            raise ValueError("这条关系已经存在。") from error

    def delete_node(self, node_id):
        with self.db:
            self.db.execute("DELETE FROM nodes WHERE id=?", (node_id,))

    def delete_edge(self, edge_id):
        with self.db:
            self.db.execute("DELETE FROM edges WHERE id=?", (edge_id,))

    def set_positions(self, positions):
        with self.db:
            self.db.executemany("UPDATE nodes SET x=?,y=? WHERE id=?", [(x, y, i) for i, (x, y) in positions.items()])

    def snapshot(self):
        return dict(version=1, nodes=self.nodes(), edges=self.edges())

    @classmethod
    def validate_snapshot(cls, data):
        if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("不是受支持的学习地图文件（version 应为 1）。")
        if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
            raise ValueError("缺少模块或关系列表。")
        ids, edge_ids, unique, accepted = set(), set(), set(), []
        for node in data["nodes"]:
            if not isinstance(node, dict):
                raise ValueError("模块格式无效。")
            cls.validate_node(node)
            nid = node.get("id")
            if type(nid) is not int or nid <= 0 or nid > 2**63 - 1 or nid in ids:
                raise ValueError("模块 ID 无效或重复。")
            if not isinstance(node.get("updated_at"), str):
                raise ValueError("模块缺少更新时间。")
            ids.add(nid)
        for edge in data["edges"]:
            if not isinstance(edge, dict):
                raise ValueError("关系格式无效。")
            eid, source, target, kind = (edge.get(k) for k in ("id", "source", "target", "kind"))
            if type(eid) is not int or eid <= 0 or eid > 2**63 - 1 or eid in edge_ids:
                raise ValueError("关系 ID 无效或重复。")
            if type(source) is not int or type(target) is not int or source not in ids or target not in ids or source == target or kind not in RELATIONS:
                raise ValueError("存在无效的模块关系。")
            key = (min(source, target), max(source, target), kind) if kind == "相关内容" else (source, target, kind)
            if key in unique:
                raise ValueError("存在重复关系。")
            if kind == "前置依赖" and cls.would_cycle(accepted, source, target):
                raise ValueError("导入文件包含循环前置依赖。")
            unique.add(key)
            edge_ids.add(eid)
            accepted.append(edge)

    def restore(self, data):
        self.validate_snapshot(data)
        with self.db:
            self.db.execute("DELETE FROM edges")
            self.db.execute("DELETE FROM nodes")
            for node in data["nodes"]:
                fields = ("id",) + NODE_FIELDS + ("updated_at",)
                self.db.execute(f"INSERT INTO nodes({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", [node[k] for k in fields])
            for edge in data["edges"]:
                source, target = edge["source"], edge["target"]
                if edge["kind"] == "相关内容" and source > target:
                    source, target = target, source
                self.db.execute("INSERT INTO edges(id,source,target,kind) VALUES(?,?,?,?)", (edge["id"], source, target, edge["kind"]))

    def export(self, path):
        target = Path(path)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)

    def layout(self):
        nodes, edges = self.nodes(), self.edges()
        degree = {n["id"]: 0 for n in nodes}
        children = {i: [] for i in degree}
        levels = {i: 0 for i in degree}
        for edge in edges:
            if edge["kind"] == "前置依赖":
                degree[edge["target"]] += 1
                children[edge["source"]].append(edge["target"])
        queue = [i for i in degree if degree[i] == 0]
        for current in queue:
            for child in children[current]:
                levels[child] = max(levels[child], levels[current] + 1)
                degree[child] -= 1
                if degree[child] == 0:
                    queue.append(child)
        rows, positions = {}, {}
        for nid, level in levels.items():
            row = rows.get(level, 0)
            positions[nid] = (130 + level * 270, 100 + row * 140)
            rows[level] = row + 1
        self.set_positions(positions)

    def seed_demo(self):
        a = self.create_node("线性代数", state="已完成", mastery="基本理解", tags="数学", summary="矩阵、向量与线性变换。")
        b = self.create_node("概率基础", state="学习中", tags="数学", summary="理解概率分布与条件概率。")
        c = self.create_node("注意力机制", summary="理解 Query、Key、Value 的作用。", notes="待解决：为什么点积需要缩放？", tags="深度学习")
        d = self.create_node("Transformer 论文", kind="论文", summary="阅读论文，整理结构与关键创新。", resources="https://arxiv.org/abs/1706.03762")
        e = self.create_node("实现一个注意力层", kind="实践", summary="通过代码验证对注意力机制的理解。")
        f = self.create_node("后续改进论文", kind="论文")
        for source, target in ((a, c), (b, c), (c, d), (d, e)):
            self.add_edge(source, target, "前置依赖")
        self.add_edge(d, f, "进阶延伸")
        self.add_edge(a, b, "相关内容")
        self.layout()

    def close(self):
        self.db.close()
