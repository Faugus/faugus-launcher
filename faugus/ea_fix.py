import json
import os

from faugus.path_manager import *

games_json = PathManager.user_config('faugus-launcher/games.json')

def update_ea_path(prefix):
    new_path = f"{prefix}/drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe"

    try:
        with open(os.path.join(prefix, "drive_c", "ProgramData", "EA Desktop", "machine.ini"), "r") as machine_ini:
            for l in machine_ini.readlines():
                if "machine.telemetry.updatestats" in l:
                    launcher_version = json.loads(l.split("=")[1])["version"]
                    new_path = f"{prefix}/drive_c/Program Files/Electronic Arts/EA Desktop/{launcher_version}/EA Desktop/EALauncher.exe"
                    break
    except FileNotFoundError:
        print("machine.ini not found")
    except KeyError:
        print("version not found in updatestats")

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
