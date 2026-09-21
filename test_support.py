"""Isolated test folders inside the workspace (also works in restricted shells)."""
import shutil
from pathlib import Path
from uuid import uuid4


class TestDirectory:
    def __init__(self):
        self.root = (Path(__file__).resolve().parent / "test-artifacts").resolve()
        self.path = self.root / uuid4().hex
        self.path.mkdir(parents=True)
        self.name = str(self.path)

    def cleanup(self):
        target = self.path.resolve()
        if target.parent != self.root or target == self.root:
            raise ValueError("Refusing to clean a folder outside test-artifacts")
        shutil.rmtree(target)

    def __enter__(self):
        return self.name

    def __exit__(self, *args):
        self.cleanup()
