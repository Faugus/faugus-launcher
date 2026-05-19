import json
import os
import re
import vdf
from pathlib import Path

from faugus.path_manager import *
from faugus.steam_setup import steam_shortcuts_path

games_json = PathManager.user_config('faugus-launcher/games.json')
app_dir = Path(PathManager.get_applications())
desktop_dir = PathManager.user_desktop()

def update_desktop_path(shortcut_path, new_dir_path):
    try:
        with open(shortcut_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        with open(shortcut_path, 'w', encoding='utf-8') as f:
            for line in lines:
                if line.startswith("Path="):
                    f.write(f"Path={new_dir_path}\n")
                else:
                    f.write(line)
        print(f"Shortcut successfully updated: {shortcut_path}")
    except Exception as e:
        print(f"Error updating shortcut {shortcut_path}: {e}")

def update_steam_shortcut(game_title, new_start_dir, new_exe):
    if not os.path.exists(steam_shortcuts_path):
        return

    try:
        with open(steam_shortcuts_path, 'rb') as f:
            shortcuts = vdf.binary_load(f)
    except SyntaxError:
        return

    changed = False
    if "shortcuts" in shortcuts:
        for app_id, game_info in shortcuts["shortcuts"].items():
            if isinstance(game_info, dict) and game_info.get("AppName") == game_title:
                game_info["StartDir"] = new_start_dir

                if "EALauncher.exe" in game_info.get("Exe", ""):
                    game_info["Exe"] = f'"{new_exe}"'

                changed = True

    if changed:
        with open(steam_shortcuts_path, 'wb') as f:
            vdf.binary_dump(shortcuts, f)
        print(f"Steam shortcut updated for: {game_title}")

def update_ea_path(prefix):
    ea_base_dir = f"{prefix}/drive_c/Program Files/Electronic Arts/EA Desktop"
    new_path = f"{ea_base_dir}/EA Desktop/EALauncher.exe"

    if os.path.exists(ea_base_dir):
        try:
            folders = [f for f in os.listdir(ea_base_dir) if os.path.isdir(os.path.join(ea_base_dir, f))]

            versions = []
            for folder in folders:
                numbers = [int(n) for n in re.findall(r'\d+', folder)]
                if numbers and folder[0].isdigit():
                    versions.append((numbers, folder))

            if versions:
                versions.sort(key=lambda x: x[0], reverse=True)
                folder_version = versions[0][1]
                new_path = f"{ea_base_dir}/{folder_version}/EA Desktop/EALauncher.exe"
                print(f"Latest version found: {folder_version}")

        except Exception as e:
            print(f"Error fetching version in folder: {e}")

    new_executable_dir = os.path.dirname(new_path)

    if os.path.exists(games_json):
        try:
            with open(games_json, "r", encoding="utf-8") as f:
                games = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            games = []

        changed = False

        for game in games:
            if "EALauncher.exe" in game.get("path", ""):
                game["path"] = new_path
                changed = True

                gameid = game.get("gameid") or game.get("id")
                game_title = game.get("title") or game.get("name") or "EA App"

                if gameid:
                    applications_shortcut_path = f"{app_dir}/{gameid}.desktop"
                    desktop_shortcut_path = f"{desktop_dir}/{gameid}.desktop"

                    if os.path.exists(applications_shortcut_path):
                        update_desktop_path(applications_shortcut_path, new_executable_dir)

                    if os.path.exists(desktop_shortcut_path):
                        update_desktop_path(desktop_shortcut_path, new_executable_dir)

                if game_title:
                    update_steam_shortcut(game_title, new_executable_dir, new_path)

        if changed:
            with open(games_json, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=4, ensure_ascii=False)

    return new_path
