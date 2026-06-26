"""Temporary migration from the legacy single-directory layout.

This module intentionally contains all compatibility migration behavior so it
can be removed together with the small startup hook in ``launcher.py`` once
support for pre-XDG-split installations is no longer needed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from faugus.path_manager import PathManager


_APP_DIR = "faugus-launcher"

# These paths used to live below XDG_CONFIG_HOME/faugus-launcher.
_CONFIG_TO_DATA = (
    "games.json",
    "banners",
    "icons",
    "icons-nolauncher",
    "games-backup",
    "presets.json",
    "categories.txt",
    "custom-order.json",
    "components",
    "logs",
)

_CONFIG_TO_STATE = (
    "latest-games.txt",
)

# These were already in XDG_DATA_HOME before being reclassified as state.
_DATA_TO_STATE = (
    "faugus_temp",
    "running_games.json",
    "latest-games.txt",
)

def _lexists(path: Path) -> bool:
    """Like Path.exists(), but also recognizes broken symlinks."""
    return os.path.lexists(path)


def _same_path(left: Path, right: Path) -> bool:
    return os.path.abspath(os.fspath(left)) == os.path.abspath(os.fspath(right))


def _move_without_overwriting(source: Path, destination: Path) -> int:
    """Move missing files recursively, preserving all destination entries.

    Returns the number of move operations performed. If a source and destination
    entry conflict, the destination wins and the source is left untouched.
    """
    if _same_path(source, destination) or not _lexists(source):
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)

    if not _lexists(destination):
        shutil.move(os.fspath(source), os.fspath(destination))
        return 1

    source_is_directory = source.is_dir() and not source.is_symlink()
    destination_is_directory = destination.is_dir() and not destination.is_symlink()
    if not (source_is_directory and destination_is_directory):
        return 0

    moved = 0
    for child in source.iterdir():
        moved += _move_without_overwriting(child, destination / child.name)

    # Remove a legacy directory only when every entry was migrated. Conflicting
    # entries remain in place, making the operation safe and retryable.
    try:
        source.rmdir()
    except OSError:
        pass

    return moved


def _migrate_items(source_root: Path, destination_root: Path,
                   items: Iterable[str]) -> int:
    if _same_path(source_root, destination_root):
        return 0

    moved = 0
    for item in items:
        try:
            moved += _move_without_overwriting(
                source_root / item,
                destination_root / item,
            )
        except OSError as error:
            print(
                f"Faugus XDG migration: could not migrate {source_root / item}: {error}",
                file=sys.stderr,
            )
    return moved


def _rewrite_managed_path(value: object, old_root: Path,
                          new_root: Path) -> object:
    if not isinstance(value, str) or not value:
        return value

    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        return value

    try:
        relative = path.relative_to(old_root)
    except ValueError:
        return value

    return os.fspath(new_root / relative)


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=os.fspath(path.parent),
        text=True,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=4)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _rewrite_games_file(path: Path, config_root: Path,
                        data_root: Path) -> bool:
    if not path.is_file():
        return False

    try:
        with path.open("r", encoding="utf-8") as file:
            games = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(
            f"Faugus XDG migration: could not read {path}: {error}",
            file=sys.stderr,
        )
        return False

    if not isinstance(games, list):
        return False

    path_mappings = {
        "icon": (
            config_root / "icons",
            data_root / "icons",
        ),
        "banner": (
            config_root / "banners",
            data_root / "banners",
        ),
    }

    changed = False
    for game in games:
        if not isinstance(game, dict):
            continue

        for field, (old_root, new_root) in path_mappings.items():
            old_value = game.get(field)
            new_value = _rewrite_managed_path(old_value, old_root, new_root)
            if new_value != old_value:
                game[field] = new_value
                changed = True

    if not changed:
        return False

    try:
        _write_json_atomic(path, games)
    except OSError as error:
        print(
            f"Faugus XDG migration: could not update {path}: {error}",
            file=sys.stderr,
        )
        return False

    return True


def _rewrite_stored_paths(config_root: Path, data_root: Path) -> int:
    rewritten = int(
        _rewrite_games_file(data_root / "games.json", config_root, data_root)
    )

    backup_root = data_root / "games-backup"
    if backup_root.is_dir():
        for backup_file in backup_root.glob("*.json"):
            rewritten += int(
                _rewrite_games_file(backup_file, config_root, data_root)
            )

    return rewritten


def migrate_legacy_xdg_layout() -> None:
    """Migrate legacy Faugus files without replacing newer destinations."""
    config_root = Path(PathManager.user_config(_APP_DIR))
    data_root = Path(PathManager.user_data(_APP_DIR))
    state_root = Path(PathManager.user_state(_APP_DIR))

    data_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)

    moved = 0
    moved += _migrate_items(config_root, data_root, _CONFIG_TO_DATA)
    moved += _migrate_items(config_root, state_root, _CONFIG_TO_STATE)
    moved += _migrate_items(data_root, state_root, _DATA_TO_STATE)

    rewritten = _rewrite_stored_paths(config_root, data_root)

    if moved or rewritten:
        print(
            "Faugus XDG migration: "
            f"moved {moved} path(s), updated {rewritten} game database file(s).",
            file=sys.stderr,
        )
