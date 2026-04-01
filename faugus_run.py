#!/usr/bin/python3

import os
import subprocess
import sys
import vdf

from faugus.path_manager import *
from faugus.steam_setup import *

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')

if IS_FLATPAK:
    app_dir = str(Path.home() / '.local/share/applications')
else:
    app_dir = PathManager.user_data('applications')

def get_desktop_dir():
    try:
        desktop_dir = subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip()
        return desktop_dir
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("xdg-user-dir not found or failed; falling back to ~/Desktop")
        return str(Path.home() / 'Desktop')

desktop_dir = get_desktop_dir()

def fix_desktop_exec():
    replacements = [
        (
            "Exec=flatpak run --command=/app/bin/faugus-run io.github.Faugus.faugus-launcher --game",
            "Exec=flatpak run --command=/app/bin/faugus-launcher io.github.Faugus.faugus-launcher --game"
        ),
        (
            "Exec=flatpak run --command=/app/bin/faugus-run io.github.Faugus.faugus-launcher",
            "Exec=flatpak run --command=/app/bin/faugus-launcher io.github.Faugus.faugus-launcher --run"
        ),
        (
            "Exec=/usr/bin/faugus-run --game",
            "Exec=/usr/bin/faugus-launcher --game"
        ),
        (
            "Exec=/usr/bin/faugus-run",
            "Exec=/usr/bin/faugus-launcher --run"
        ),
    ]

    for d in [desktop_dir, app_dir]:
        if not d or not os.path.isdir(d):
            continue

        for file in os.listdir(d):
            if not file.endswith(".desktop"):
                continue

            file_path = os.path.join(d, file)

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                new_content = content
                for old, new in replacements:
                    new_content = new_content.replace(old, new)

                if new_content == content:
                    continue

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

            except Exception as e:
                print(f"Error processing {file_path}: {e}")

def fix_steam_shortcuts():
    if not os.path.exists(steam_shortcuts_path):
        return

    try:
        with open(steam_shortcuts_path, 'rb') as f:
            shortcuts = vdf.binary_load(f)
    except Exception as e:
        print(f"Error reading shortcuts.vdf: {e}")
        return

    changed = False

    for app_id, game in shortcuts.get("shortcuts", {}).items():
        if not isinstance(game, dict):
            continue

        launch = game.get("LaunchOptions", "")
        exe = game.get("Exe", "")

        if "--game" not in launch:
            continue

        new_launch = launch
        new_exe = exe

        new_launch = new_launch.replace(
            "/app/bin/faugus-run",
            "/app/bin/faugus-launcher"
        )

        new_launch = new_launch.replace(
            "/usr/bin/faugus-run",
            "/usr/bin/faugus-launcher"
        )

        new_exe = new_exe.replace(
            "/usr/bin/faugus-run",
            "/usr/bin/faugus-launcher"
        )

        if new_launch != launch or new_exe != exe:
            game["LaunchOptions"] = new_launch
            game["Exe"] = new_exe
            changed = True

    if not changed:
        return

    try:
        with open(steam_shortcuts_path, 'wb') as f:
            vdf.binary_dump(shortcuts, f)
    except Exception as e:
        print(f"Error saving shortcuts.vdf: {e}")

if __name__ == "__main__":
    fix_desktop_exec()
    fix_steam_shortcuts()
    os.execv(sys.executable, [sys.executable, "-m", "faugus.runner", *sys.argv[1:]])
