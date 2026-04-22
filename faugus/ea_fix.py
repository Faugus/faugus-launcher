import json
import os
import re

from faugus.path_manager import *

games_json = PathManager.user_config('faugus-launcher/games.json')

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

        if changed:
            with open(games_json, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=4, ensure_ascii=False)

    return new_path
