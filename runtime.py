"""Stable packaged data paths and non-destructive migration from source builds."""
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

PROJECT = Path(__file__).resolve().parent
RELEASE_URL = "https://github.com/Lee7777777777/learn_dominate/releases/latest"


def user_data_dir():
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ZhiLu" / "data"
    return PROJECT / "data"


def migrate_legacy(source, target):
    """Copy a complete library only to a new destination. Never remove the original."""
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.exists() or not (source / "learning_map.db").is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / (".migration-" + uuid4().hex)
    staging.mkdir()
    try:
        databases = [source / "learning_map.db"]
        catalog = source / "learning_map.library.db"
        if catalog.exists():
            databases.append(catalog)
        maps = source / "learning_map_maps"
        if maps.exists():
            databases.extend(maps.glob("*.db"))
        for path in databases:
            destination = staging / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            origin = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
            copy = sqlite3.connect(destination)
            try:
                origin.backup(copy)
            finally:
                copy.close()
                origin.close()
        backups = source / "backups"
        if backups.exists():
            shutil.copytree(backups, staging / "backups")
        staging.rename(target)
        return True
    finally:
        if staging.exists():
            # Only the unique staging directory allocated above can be removed.
            if staging.resolve().parent != target.parent or not staging.name.startswith(".migration-"):
                raise ValueError("Invalid migration staging path")
            shutil.rmtree(staging)


def prepare_data_dir():
    target = user_data_dir()
    if getattr(sys, "frozen", False) and not target.exists():
        executable_folder = Path(sys.executable).resolve().parent
        # Supports a downloaded app beside old data and local dist/ builds.
        candidates = [executable_folder / "data", executable_folder.parent / "data"]
        development_root = executable_folder.parent.parent
        if executable_folder.parent.name == "dist" and (development_root / "app.py").is_file():
            candidates.append(development_root / "data")
        for candidate in candidates:
            if migrate_legacy(candidate, target):
                break
    target.mkdir(parents=True, exist_ok=True)
    return target
