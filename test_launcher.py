"""Verify the actual Windows launcher opens a GUI without a console."""
import ctypes
import json
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from test_support import TestDirectory


@unittest.skipUnless(sys.platform == "win32", "Windows launcher")
class LauncherTests(unittest.TestCase):
    def test_windowed_launcher(self):
        with TestDirectory() as directory:
            target = Path(directory)
            shutil.copyfile(Path(__file__).with_name("start.vbs"), target / "start.vbs")
            (target / "start.pyw").write_text(
                'import ctypes, json, os, tkinter as tk\nfrom pathlib import Path\n'
                'root=tk.Tk()\nroot.update()\n'
                'result={"pid":os.getpid(),"console":ctypes.windll.kernel32.GetConsoleWindow(),"visible":bool(root.winfo_viewable())}\n'
                'root.destroy()\nPath(__file__).with_suffix(".json").write_text(json.dumps(result))\n', encoding="utf-8")
            subprocess.run(["wscript.exe", str(target / "start.vbs")], check=True, timeout=10)
            marker = target / "start.json"
            deadline = time.monotonic() + 10
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(marker.exists(), "Windowed Python failed to start")
            result = json.loads(marker.read_text())
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(0x100000, False, result["pid"])
            if handle:
                try:
                    self.assertEqual(kernel.WaitForSingleObject(handle, 10000), 0)
                finally:
                    kernel.CloseHandle(handle)
            self.assertEqual(result["console"], 0)
            self.assertTrue(result["visible"])
