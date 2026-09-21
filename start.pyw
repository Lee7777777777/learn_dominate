"""Windowed entry point: pythonw does not create a console window."""
import logging
from pathlib import Path

if __name__ == "__main__":
    log = Path(__file__).resolve().parent / "data" / "app.log"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=log, encoding="utf-8", level=logging.ERROR)
        from app import main
        main()
    except Exception:
        logging.exception("Application startup failed")
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f"启动失败，请查看日志：\n{log}", "知路 · 启动失败", 16)
