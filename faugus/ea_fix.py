import os
import re
import shutil
import vdf

from faugus.path_manager import *
from faugus.steam_setup import get_all_shortcut_paths
from faugus.utils import load_json_file, save_json_file, expand_path


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
    for shortcut_path in get_all_shortcut_paths():
        if not os.path.exists(shortcut_path):
            continue

        try:
            with open(shortcut_path, 'rb') as f:
                shortcuts = vdf.binary_load(f)
        except SyntaxError:
            continue

        changed = False
        if "shortcuts" in shortcuts:
            for app_id, game_info in shortcuts["shortcuts"].items():
                if isinstance(game_info, dict) and game_info.get("AppName") == game_title:
                    game_info["StartDir"] = new_start_dir

                    if "EALauncher.exe" in game_info.get("Exe", ""):
                        game_info["Exe"] = f'"{new_exe}"'

                    changed = True

        if changed:
            with open(shortcut_path, 'wb') as f:
                vdf.binary_dump(shortcuts, f)
            print(f"Steam shortcut updated for: {game_title}")


def update_ea_path(prefix):
    prefix = expand_path(prefix)
    ea_base_dir = f"{prefix}/drive_c/Program Files/Electronic Arts/EA Desktop"
    target_ea_desktop = f"{ea_base_dir}/EA Desktop"
    new_path = f"{target_ea_desktop}/EALauncher.exe"

    if os.path.exists(ea_base_dir):
        try:
            folders = [f for f in os.listdir(ea_base_dir) if os.path.isdir(os.path.join(ea_base_dir, f))]

            versions = []
            for folder in folders:
                if folder == "EA Desktop":
                    continue

                numbers = [int(n) for n in re.findall(r'\d+', folder)]
                if numbers and folder[0].isdigit():
                    versions.append((numbers, folder))

            if versions:
                versions.sort(key=lambda x: x[0], reverse=True)
                folder_version = versions[0][1]
                print(f"Latest version found: {folder_version}")

                highest_version_path = os.path.join(ea_base_dir, folder_version)
                inner_ea_desktop = os.path.join(highest_version_path, "EA Desktop")

                if os.path.exists(inner_ea_desktop):
                    print(f"Copying files to base EA Desktop directory: {target_ea_desktop}")
                    shutil.copytree(inner_ea_desktop, target_ea_desktop, dirs_exist_ok=True)

                    for _, v_folder in versions:
                        version_dir_to_remove = os.path.join(ea_base_dir, v_folder)
                        try:
                            print(f"Removing version directory: {version_dir_to_remove}")
                            shutil.rmtree(version_dir_to_remove)
                        except Exception as e:
                            print(f"Error removing directory {version_dir_to_remove}: {e}")

        except Exception as e:
            print(f"Error processing EA directories: {e}")

    new_executable_dir = os.path.dirname(new_path)

    games = load_json_file(GAMES_JSON, [])

    changed = False

    for game in games:
        if "EALauncher.exe" in game.get("path", ""):
            game["path"] = new_path
            changed = True

            gameid = game.get("gameid") or game.get("id")
            game_title = game.get("title") or game.get("name") or "EA App"

            if gameid:
                applications_shortcut_path = f"{APP_DIR}/{gameid}.desktop"
                desktop_shortcut_path = f"{DESKTOP_DIR}/{gameid}.desktop"

                if os.path.exists(applications_shortcut_path):
                    update_desktop_path(applications_shortcut_path, new_executable_dir)

                if os.path.exists(desktop_shortcut_path):
                    update_desktop_path(desktop_shortcut_path, new_executable_dir)

            if game_title:
                update_steam_shortcut(game_title, new_executable_dir, new_path)

    if changed:
        save_json_file(games, GAMES_JSON)

    return new_path
