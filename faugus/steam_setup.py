import os

from pathlib import Path
from gi.repository import GdkPixbuf

possible_steam_locations = [
    Path.home() / '.local' / 'share' / 'Steam' / 'userdata',
    Path.home() / '.steam' / 'steam' / 'userdata',
    Path.home() / '.steam' / 'root' / 'userdata',
    os.path.expanduser('~/.var/app/com.valvesoftware.Steam/.steam/steam/userdata/')
]

steam_userdata_path = None
IS_STEAM_FLATPAK = False

for location in possible_steam_locations:
    if Path(location).exists():
        steam_userdata_path = location
        if str(location).startswith(str(Path.home() / '.var' / 'app' / 'com.valvesoftware.Steam')):
            IS_STEAM_FLATPAK = True
        break

def detect_steam_id():
    if steam_userdata_path:
        try:
            steam_ids = [f for f in os.listdir(steam_userdata_path)
                         if os.path.isdir(os.path.join(steam_userdata_path, f)) and f.isdigit()]
            return steam_ids[0] if steam_ids else None
        except (FileNotFoundError, PermissionError):
            return None
    return None

steam_id = detect_steam_id()

steam_shortcuts_path = f'{steam_userdata_path}/{steam_id}/config/shortcuts.vdf' if steam_id else ""

def find_lossless_dll():
    possible_common_locations = [
        Path.home() / '.local' / 'share' / 'Steam' / 'steamapps' / 'common',
        Path.home() / '.steam' / 'steam' / 'steamapps' / 'common',
        Path.home() / '.steam' / 'root' / 'steamapps' / 'common',
        Path.home() / 'SteamLibrary' / 'steamapps' / 'common',
        Path(os.path.expanduser('~/.var/app/com.valvesoftware.Steam/.steam/steamapps/common/'))
    ]

    for location in possible_common_locations:
        dll_candidate = location / 'Lossless Scaling' / 'Lossless.dll'
        if dll_candidate.exists():
            return str(dll_candidate)

    return ""

STEAM_BASE_DIRS = [
    Path.home() / ".steam/steam",
    Path.home() / ".local/share/Steam",
]

def find_steam_root():
    for base in STEAM_BASE_DIRS:
        if base.exists():
            return base
    return None


def read_library_folders(steam_root: Path):
    libraries = [steam_root]
    vdf = steam_root / "config/libraryfolders.vdf"

    if not vdf.exists():
        return libraries

    with open(vdf, "r", errors="ignore") as f:
        for line in f:
            if '"path"' in line:
                path = line.split('"')[-2]
                libraries.append(Path(path))

    return libraries


def read_installed_games():
    steam_root = find_steam_root()
    if not steam_root:
        return []

    games = []
    libraries = read_library_folders(steam_root)

    for lib in libraries:
        steamapps = lib / "steamapps"
        if not steamapps.exists():
            continue

        for manifest in steamapps.glob("appmanifest_*.acf"):
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
    steam_root = find_steam_root()
    if not steam_root:
        return None

    cache = steam_root / "appcache/librarycache" / appid
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
