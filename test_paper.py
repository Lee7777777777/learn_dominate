"""Paper integration tests use generated PDFs and fake processes, never user papers."""
import copy
import json
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from app import LearningMap
from library import MapLibrary
from paper_agent import (Cancelled, RESULT_SCHEMA, extract_pdf, load_task, parse_result,
                         prepare_task, read_json, result_snapshot, run_codex, validate_result, write_json)
from storage import Store
from test_support import TestDirectory


def make_pdf(path, blank=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if not blank:
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 40 700 Td (Attention combines values using weights derived from queries and keys.) Tj 0 -20 Td (This synthetic paper describes a small learning experiment and its limitations.) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def fixture(root):
    pdf = Path(root) / "paper source.pdf"
    make_pdf(pdf)
    task, _ = prepare_task(pdf, root, "深入理解", "Python basics", 20)
    manifest, pages = load_task(task)
    result = dict(format_version=1, task_id=manifest["task_id"], paper_sha256=manifest["paper_sha256"], title="注意力学习路线", nodes=[
        dict(id="math", title="矩阵基础", kind="知识点", origin="AI建议", summary="理解矩阵乘法", objective="解释输入输出维度", task="计算一个小矩阵乘积", sources=[]),
        dict(id="attention", title="注意力机制", kind="论文", origin="论文内容", summary="加权组合数值", objective="理解查询与键的作用", task="实现一个加权和", sources=[dict(page=1, quote="Attention combines values using weights")])],
        edges=[dict(source="math", target="attention", kind="前置依赖", reason="计算注意力需要矩阵乘法")])
    return task, manifest, pages, result


class PaperTests(unittest.TestCase):
    def test_pdf_exchange_and_atomic_new_map(self):
        with TestDirectory() as root:
            task, manifest, pages, data = fixture(root)
            self.assertIn("PDF 第 1 页", (task / "paper.txt").read_text(encoding="utf-8"))
            self.assertEqual(validate_result(data, manifest, pages), [])
            self.assertEqual(parse_result("```json\n" + json.dumps(data) + "\n```"), data)
            snapshot, warnings = result_snapshot(data, manifest, pages)
            library = MapLibrary(Path(root) / "original.db")
            original = Store(library.original)
            original.create_node("保留我的笔记", notes="不能丢失")
            try:
                new_id = library.create(data["title"], snapshot)
                new = Store(library.path(new_id))
                try:
                    self.assertEqual(len(new.nodes()), 2)
                    self.assertIn("摘录已匹配", new.nodes()[1]["resources"])
                    self.assertIn("计算注意力", new.nodes()[0]["notes"])
                    self.assertLess(new.nodes()[0]["x"], new.nodes()[1]["x"])
                finally:
                    new.close()
                self.assertEqual(original.nodes()[0]["notes"], "不能丢失")
                count = len(library.maps())
                with patch.object(Store, "restore", side_effect=OSError("disk failure")):
                    with self.assertRaises(OSError):
                        library.create("保存失败", snapshot)
                self.assertEqual(len(library.maps()), count)
                self.assertEqual(len(list((Path(root) / "original_maps").glob("*.db"))), 1)
            finally:
                original.close()
                library.close()

    def test_bad_graph_and_wrong_paper_are_rejected(self):
        with TestDirectory() as root:
            _, manifest, pages, valid = fixture(root)
            changes = [lambda d: d.update(task_id="another"), lambda d: d.update(paper_sha256="wrong"),
                       lambda d: d["nodes"][1]["sources"][0].update(page=2),
                       lambda d: d["nodes"][1].update(sources=[]),
                       lambda d: d["nodes"][0].update(id=" math"),
                       lambda d: d["edges"][0].update(source=" math"),
                       lambda d: d["edges"][0].update(source="missing"),
                       lambda d: d["edges"].append(dict(source="attention", target="math", kind="前置依赖", reason="循环")),
                       lambda d: d["edges"].append(copy.deepcopy(d["edges"][0])),
                       lambda d: d["nodes"].append(copy.deepcopy(d["nodes"][0]))]
            for change in changes:
                data = copy.deepcopy(valid)
                change(data)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    validate_result(data, manifest, pages)

    def test_unmatched_quote_marked_and_modified_task_rejected(self):
        with TestDirectory() as root:
            task, manifest, pages, data = fixture(root)
            data["nodes"][1]["sources"][0]["quote"] = "This sentence does not appear in the document"
            snapshot, warnings = result_snapshot(data, manifest, pages)
            self.assertEqual(len(warnings), 1)
            self.assertIn("摘录待核对", snapshot["nodes"][1]["resources"])
            (task / "pages.json").write_text('["altered"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_task(task)

    def test_scan_cancel_and_invalid_json(self):
        with TestDirectory() as root:
            pdf = Path(root) / "scan.pdf"
            make_pdf(pdf, blank=True)
            with self.assertRaisesRegex(ValueError, "OCR"):
                extract_pdf(pdf, threading.Event(), lambda s: None)
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(Cancelled):
                extract_pdf(pdf, cancel, lambda s: None)
            with self.assertRaises(ValueError):
                parse_result("This is not JSON")

    def test_codex_contract_success_failure_and_cancellation(self):
        with TestDirectory() as root:
            task, _, _, data = fixture(root)
            class Process:
                pid = 12345
                returncode = 0
                def poll(self): return self.returncode
                def wait(self, timeout=None): return self.returncode
            commands = []
            def launch(command, **kwargs):
                commands.append((command, kwargs))
                write_json(Path(command[command.index("-o") + 1]), data)
                return Process()
            with patch("paper_agent.subprocess.Popen", side_effect=launch):
                result = run_codex(task, "codex.exe", threading.Event(), lambda s: None)
            self.assertEqual(result, data)
            command, options = commands[0]
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertEqual(options["stdin"], subprocess.DEVNULL)
            self.assertNotIn("shell", options)
            self.assertEqual(read_json(task / "result.json"), data)
            Process.returncode = 1
            with patch("paper_agent.subprocess.Popen", return_value=Process()), self.assertRaisesRegex(ValueError, "登录"):
                run_codex(task, "codex.exe", threading.Event(), lambda s: None)
            # Failure must not destroy an earlier valid result.
            self.assertEqual(read_json(task / "result.json"), data)
            cancel = threading.Event()
            cancel.set()
            with patch("paper_agent.subprocess.Popen") as popen, self.assertRaises(Cancelled):
                run_codex(task, "codex.exe", cancel, lambda s: None)
            popen.assert_not_called()
            class Running(Process):
                returncode = None
                def poll(self):
                    cancel.set()
                    return self.returncode
                def wait(self, timeout=None):
                    self.returncode = -1
                    return -1
                def terminate(self): self.returncode = -1
            cancel.clear()
            with patch("paper_agent.subprocess.Popen", return_value=Running()), patch("paper_agent.subprocess.run") as kill, self.assertRaises(Cancelled):
                run_codex(task, "codex.exe", cancel, lambda s: None)
            if __import__('os').name == "nt":
                self.assertIn("/T", kill.call_args.args[0])

    def test_dialog_import_edit_save_and_resume(self):
        with TestDirectory() as root:
            task, _, _, data = fixture(root)
            app = LearningMap(Path(root) / "ui.db")
            try:
                app.store.create_node("原有内容")
                app.refresh()
                old_id = app.map_id
                dialog = app.paper_dialog()
                app.update()
                dialog.start_codex()
                self.assertIn("勾选", dialog.error.get())
                dialog.set_task(task)
                dialog.raw.insert("1.0", json.dumps(data))
                self.assertTrue(dialog.apply_raw())
                app.update()
                self.assertEqual(len(dialog.canvas.find_withtag("paper-node:0")), 2)
                for size in ("1040x800", "900x700"):
                    dialog.geometry(size)
                    app.update()
                    self.assertLess(dialog.footer.winfo_y() + dialog.footer.winfo_height(), dialog.winfo_height() + 2)
                    self.assertTrue(dialog.validate_button.winfo_viewable())
                    self.assertLess(dialog.validate_button.winfo_rooty() + dialog.validate_button.winfo_height(), dialog.footer.winfo_rooty())
                dialog.title_var.set("我的 AI 地图")
                dialog.submit()
                self.assertFalse(dialog.winfo_exists())
                self.assertEqual(app.map_name.get(), "我的 AI 地图")
                self.assertEqual(len(app.store.nodes()), 2)
                app.open_map(old_id)
                self.assertEqual(app.store.nodes()[0]["title"], "原有内容")
                dialog = app.paper_dialog()
                dialog.set_task(task)
                dialog.accept_result(data)
                dialog.raw.delete("1.0", "end")
                dialog.raw.insert("1.0", "invalid")
                self.assertFalse(dialog.apply_raw())
                dialog.submit()
                self.assertTrue(dialog.winfo_exists())
                dialog.destroy()
            finally:
                app.store.close()
                app.library.close()
                app.destroy()

    def test_worker_does_not_block_tk_and_can_stop(self):
        with TestDirectory() as root:
            app = LearningMap(Path(root) / "async.db")
            try:
                dialog = app.paper_dialog()
                def work(cancel, report):
                    report("正在分析")
                    cancel.wait(5)
                    if cancel.is_set():
                        raise Cancelled("已取消")
                dialog.launch(work)
                app.update()
                self.assertTrue(dialog.busy)
                dialog.cancel()
                self.assertTrue(dialog.winfo_exists())
                deadline = time.monotonic() + 3
                while dialog.busy and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.02)
                self.assertFalse(dialog.busy)
                self.assertIn("已取消", dialog.error.get())
                dialog.cancel()
                self.assertFalse(dialog.winfo_exists())
            finally:
                app.store.close()
                app.library.close()
                app.destroy()


if __name__ == "__main__":
    unittest.main()
