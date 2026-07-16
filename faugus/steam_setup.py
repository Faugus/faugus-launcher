import os
import subprocess
import zlib

from pathlib import Path
import gi
gi.require_version('GdkPixbuf', '2.0')
from faugus.path_manager import PathManager, IS_FLATPAK
from gi.repository import GdkPixbuf


def _check_command(cmd):
    try:
        if IS_FLATPAK:
            cmd = ["flatpak-spawn", "--host"] + cmd
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def has_steam_flatpak():
    return _check_command(["flatpak", "info", "com.valvesoftware.Steam"])


def has_steam_native():
    return _check_command(["which", "steam"])


def detect_steam_version():
    if has_steam_native():
        return "native"
    elif has_steam_flatpak():
        return "flatpak"
    else:
        return None


def detect_steam_folder():
    steam_version = detect_steam_version()
    if steam_version == "flatpak":
        return (Path(PathManager.user_home(".var/app/com.valvesoftware.Steam/.steam/steam")), True)
    if steam_version == "native":
        return (Path(PathManager.user_home(".steam/steam")), False)
    return (None, False)


steam_folder, IS_STEAM_FLATPAK = detect_steam_folder()
userdata = steam_folder / "userdata" if steam_folder else None
library = steam_folder / "config/libraryfolders.vdf" if steam_folder else None
librarycache = steam_folder / "appcache/librarycache" if steam_folder else None

lossless_dll = (
    (steam_folder / "steamapps/common/Lossless Scaling/Lossless.dll")
    if steam_folder and (steam_folder / "steamapps/common/Lossless Scaling/Lossless.dll").is_file()
    else ""
)


def generate_steam_shortcut_id(exe, appname):
    return zlib.crc32((exe + appname).encode('utf-8')) | 0x80000000


def to_signed_int32(value):
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def get_all_shortcut_paths():
    paths = []
    if userdata:
        try:
            steam_ids = [f for f in os.listdir(userdata)
                         if os.path.isdir(os.path.join(userdata, f)) and f.isdigit()]
            for sid in steam_ids:
                paths.append(userdata / sid / "config/shortcuts.vdf")
        except (FileNotFoundError, PermissionError):
            pass
    return paths


def read_library_folders():
    libraries = []

    if not library or not library.exists():
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

            with open(manifest, "r", errors="ignore") as f:
                for line in f:
                    if '"name"' in line:
                        name = line.split('"')[-2]

            if name:
                games.append((appid, name))

    return sorted(games, key=lambda x: x[1].lower())


def get_steam_icon_path(appid):
    if not librarycache or not librarycache.exists():
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
