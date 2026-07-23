import os
import subprocess
import zlib

import vdf
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
USERDATA = steam_folder / "userdata" if steam_folder else None
LIBRARY = steam_folder / "config/libraryfolders.vdf" if steam_folder else None
LIBRARYCACHE = steam_folder / "appcache/librarycache" if steam_folder else None

LOSSLESS_DLL = (
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


def list_steam_account_ids():
    if not USERDATA:
        return []
    try:
        return [f for f in os.listdir(USERDATA)
                if os.path.isdir(os.path.join(USERDATA, f)) and f.isdigit() and f != "0"]
    except (FileNotFoundError, PermissionError):
        return []


def get_all_shortcut_paths(account_id=None):
    if not USERDATA:
        return []
    if account_id and account_id != "all":
        return [USERDATA / account_id / "config/shortcuts.vdf"]
    return [USERDATA / sid / "config/shortcuts.vdf" for sid in list_steam_account_ids()]


def read_steam_users():
    account_ids = list_steam_account_ids()
    if not account_ids:
        return []

    names = {}
    login_users_path = steam_folder / "config/loginusers.vdf" if steam_folder else None
    if login_users_path and login_users_path.exists():
        try:
            with open(login_users_path, "r", errors="ignore") as f:
                data = vdf.load(f)
            for steamid64_str, info in data.get("users", {}).items():
                try:
                    account_id = str(int(steamid64_str) - 76561197960265728)
                except ValueError:
                    continue
                names[account_id] = info.get("PersonaName") or account_id
        except Exception:
            pass

    users = [(aid, names.get(aid, aid)) for aid in account_ids]
    return sorted(users, key=lambda u: u[1].lower())


def read_library_folders():
    libraries = []

    if not LIBRARY or not LIBRARY.exists():
        return libraries

    with open(LIBRARY, "r", errors="ignore") as f:
        for line in f:
            if '"path"' in line:
                path = line.split('"')[-2]
                libraries.append(Path(path))

    return libraries


def read_installed_games(account_id=None):
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
            last_owner = None

            with open(manifest, "r", errors="ignore") as f:
                for line in f:
                    if '"name"' in line and name is None:
                        name = line.split('"')[-2]
                    if '"LastOwner"' in line:
                        last_owner = line.split('"')[-2]

            if account_id and account_id != "all":
                owner_account_id = None
                if last_owner:
                    try:
                        owner_account_id = str(int(last_owner) - 76561197960265728)
                    except ValueError:
                        owner_account_id = None
                if owner_account_id != account_id:
                    continue

            if name:
                games.append((appid, name))

    return sorted(games, key=lambda x: x[1].lower())


def get_steam_icon_path(appid):
    if not LIBRARYCACHE or not LIBRARYCACHE.exists():
        return None

    cache = LIBRARYCACHE / str(appid)
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
