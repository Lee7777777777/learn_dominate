"""Windowed entry point: pythonw does not create a console window."""
import logging

if __name__ == "__main__":
    try:
        from app import main
        main()
    except Exception:
        logging.exception("Application startup failed")
        import ctypes
        import traceback
        ctypes.windll.user32.MessageBoxW(None, "启动失败：\n" + traceback.format_exc()[-1800:], "知路 · 启动失败", 16)
