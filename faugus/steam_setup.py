import os
import subprocess
import shutil

from pathlib import Path
from gi.repository import GdkPixbuf

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')
IS_STEAM_FLATPAK = None

def has_steam_flatpak():
    try:
        cmd = ["flatpak", "info", "com.valvesoftware.Steam"]

        if IS_FLATPAK:
            cmd = ["flatpak-spawn", "--host"] + cmd

        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False

def has_steam_native():
    return shutil.which("steam") is not None

def detect_steam_version():
    if IS_FLATPAK:
        if has_steam_flatpak():
            return "flatpak"
    else:
        if has_steam_native():
            return "native"
        elif has_steam_flatpak():
            return "flatpak"
        else:
            return None

def detect_steam_folder():
    steam_version = detect_steam_version()
    if steam_version == "flatpak":
        IS_STEAM_FLATPAK = True
        return Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / ".steam" / "steam"
    if steam_version == "native":
        return Path.home() / ".steam" / "steam"

steam_folder = detect_steam_folder()
userdata = steam_folder / "userdata" if steam_folder else None
library = steam_folder / "config/libraryfolders.vdf" if steam_folder else None
steamapps = steam_folder / "steamapps" if steam_folder else None
librarycache = steam_folder / "appcache/librarycache" if steam_folder else None

lossless_dll = (
    (steam_folder / "steamapps/common/Lossless Scaling/Lossless.dll")
    if steam_folder and (steam_folder / "steamapps/common/Lossless Scaling/Lossless.dll").is_file()
    else ""
)

def detect_steam_id():
    if userdata:
        try:
            steam_ids = [f for f in os.listdir(userdata)
                         if os.path.isdir(os.path.join(userdata, f)) and f.isdigit()]
            return steam_ids[0] if steam_ids else None
        except (FileNotFoundError, PermissionError):
            return None
    return None

steam_id = detect_steam_id()
steam_shortcuts_path = userdata / steam_id / "config/shortcuts.vdf" if userdata and steam_id else ""

def read_library_folders():
    libraries = []

    if not library.exists():
        return libraries

    with open(library, "r", errors="ignore") as f:
        for line in f:
            if '"path"' in line:
                path = line.split('"')[-2]
                libraries.append(Path(path))

    return libraries

def read_installed_games():
    if not steam_folder:
        return []

    games = []
    libraries = read_library_folders()

    for lib in libraries:
        steamapps_dir = lib / "steamapps"

        if not steamapps_dir.exists():
            continue

        for manifest in steamapps_dir.glob("appmanifest_*.acf"):
            appid = manifest.stem.split("_")[-1]
            name = None
            state = None

            with open(manifest, "r", errors="ignore") as f:
                for line in f:
                    if '"name"' in line:
                        name = line.split('"')[-2]
                    elif '"StateFlags"' in line:
                        state = line.split('"')[-2]

            if name and state == "4":
                games.append((appid, name))

    return sorted(games, key=lambda x: x[1].lower())

def get_steam_icon_path(appid):
    if not librarycache.exists():
        return None

    cache = librarycache / str(appid)
    if not cache.exists():
        return None

    images = []

    for img in cache.rglob("*.jpg"):
        if img.name in (
            "header.jpg",
            "library_600x900.jpg",
            "library_capsule.jpg",
        ):
            continue

        try:
            pix = GdkPixbuf.Pixbuf.new_from_file(str(img))
            area = pix.get_width() * pix.get_height()
            images.append((area, img))
        except Exception:
            pass

    if not images:
        return None

    images.sort(key=lambda x: x[0])
    return str(images[0][1])
