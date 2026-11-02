import functools
import json
import os
import re
import shlex
import signal
import subprocess
import tempfile
import zlib
from concurrent.futures import ThreadPoolExecutor

from faugus.path_manager import COMPATIBILITY_DIRS, COVERS_DIR, FAUGUS_LAUNCHER_STATE_DIR, GAMES_JSON, ICONS_DIR, PROTON_CACHYOS


def umu_game_id(gameid):
    return f"umu-faugus{zlib.crc32(gameid.encode()):08x}"


def stop_request_path(gameid):
    return os.path.join(FAUGUS_LAUNCHER_STATE_DIR, f"stop-{gameid}")


def kill_by_faugusid(gameid):
    if not gameid:
        return

    marker = f"FAUGUSID={gameid}".encode()
    own_pid = os.getpid()

    for entry in os.scandir("/proc"):
        if not entry.name.isdigit() or int(entry.name) == own_pid:
            continue
        try:
            with open(f"/proc/{entry.name}/environ", "rb") as f:
                environ = f.read()
        except OSError:
            continue
        if marker in environ.split(b"\0"):
            try:
                os.kill(int(entry.name), signal.SIGKILL)
            except OSError:
                pass


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def atomic_write(filepath, write_func):
    ensure_parent_dir(filepath)
    dir_name = os.path.dirname(filepath) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            write_func(f)
        os.replace(tmp_path, filepath)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def load_json_file(filepath, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def save_json_file(data, filepath, indent=4):
    atomic_write(filepath, lambda f: json.dump(data, f, indent=indent, ensure_ascii=False))


def build_lossless_env(lossless_enabled, lossless_multiplier, lossless_flow,
                       lossless_performance, lossless_hdr, lossless_present):
    parts = []
    if not lossless_enabled:
        return parts
    parts.append("LSFG_LEGACY=1")
    parts.append("LSFGVK_ENV=1")
    if lossless_multiplier:
        parts.append(f"LSFG_MULTIPLIER={lossless_multiplier}")
        parts.append(f"LSFGVK_MULTIPLIER={lossless_multiplier}")
    if lossless_flow:
        parts.append(f"LSFG_FLOW_SCALE={lossless_flow/100}")
        parts.append(f"LSFGVK_FLOW_SCALE={lossless_flow/100}")
    parts.append(f"LSFG_PERFORMANCE_MODE={1 if lossless_performance else 0}")
    parts.append(f"LSFGVK_PERFORMANCE_MODE={1 if lossless_performance else 0}")
    parts.append(f"LSFG_HDR_MODE={1 if lossless_hdr else 0}")
    if lossless_present:
        parts.append(f"LSFG_EXPERIMENTAL_PRESENT_MODE={lossless_present}")
    return parts


def expand_path(value):
    if not value:
        return value
    return os.path.expandvars(os.path.expanduser(value))


def resolve_protonpath(runner):
    return PROTON_CACHYOS if runner == "Proton-CachyOS (System)" else runner


def resolve_game_runner(runner):
    if runner != "Default":
        return runner
    from faugus.config_manager import ConfigManager
    return ConfigManager().config.get('default-runner', '').strip('"')


_gpus_cache = None


def get_gpus():
    global _gpus_cache
    if _gpus_cache is None:
        _gpus_cache = scan_gpus()
    return [dict(gpu) for gpu in _gpus_cache]


def scan_gpus():
    gpus = []
    drm = "/sys/class/drm"
    try:
        cards = sorted(c for c in os.listdir(drm) if re.fullmatch(r"card\d+", c))
    except OSError:
        return gpus

    for card in cards:
        device = os.path.join(drm, card, "device")
        try:
            with open(os.path.join(device, "uevent")) as f:
                slot = next(l.split("=", 1)[1].strip() for l in f if l.startswith("PCI_SLOT_NAME="))
            with open(os.path.join(device, "vendor")) as f:
                vendor = f.read().strip()[2:]
            with open(os.path.join(device, "device")) as f:
                device_id = f.read().strip()[2:]
        except (OSError, StopIteration):
            continue

        name = slot
        try:
            out = subprocess.check_output(["lspci", "-s", slot, "-mm"], text=True, timeout=5)
            parts = shlex.split(out.strip())
            vendor_name = {"10de": "NVIDIA", "1002": "AMD", "8086": "Intel"}.get(vendor, parts[2])
            model = re.search(r"\[(.+)\]", parts[3])
            name = "{} {}".format(vendor_name, model.group(1) if model else parts[3])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass

        gpus.append({"slot": slot, "vendor": vendor, "device": device_id, "name": name})
    return gpus


@functools.cache
def get_steamgriddb_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=16)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_steamgriddb_candidates(api_key, game_name, limit=12, game_id=None, steam_appid=None):
    import requests
    from urllib.parse import quote

    session = get_steamgriddb_session()
    headers = {"Authorization": f"Bearer {api_key}"}
    result = {"game_id": None, "grids": [], "heroes": [], "icons": []}

    try:
        if steam_appid is not None:
            id_type, lookup_id = "steam", steam_appid
        else:
            if game_id is None:
                search = session.get(
                    f"https://www.steamgriddb.com/api/v2/search/autocomplete/{quote(game_name)}",
                    headers=headers, timeout=10,
                )
                search.raise_for_status()
                results = search.json().get("data") or []
                if not results:
                    return result
                game_id = results[0]["id"]
            id_type, lookup_id = "game", game_id
            result["game_id"] = game_id

        endpoints = {
            "grids": (f"https://www.steamgriddb.com/api/v2/grids/{id_type}/{lookup_id}", {"dimensions": "600x900"}),
            "heroes": (f"https://www.steamgriddb.com/api/v2/heroes/{id_type}/{lookup_id}", {}),
            "icons": (f"https://www.steamgriddb.com/api/v2/icons/{id_type}/{lookup_id}", {}),
        }

        def fetch_one(key):
            url, params = endpoints[key]
            try:
                response = session.get(url, headers=headers, params=params, timeout=10)
                if response.ok:
                    data = response.json().get("data") or []
                    return key, [
                        {"url": item["url"], "thumb": item.get("thumb") or item["url"]}
                        for item in data[:limit] if item.get("url")
                    ]
            except requests.RequestException:
                pass
            return key, []

        with ThreadPoolExecutor(max_workers=3) as pool:
            for key, items in pool.map(fetch_one, endpoints.keys()):
                result[key] = items

        return result
    except requests.RequestException:
        return result


def load_json_file_or_none(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"Faugus Launcher: refusing to touch {filepath}, failed to read it ({e})")
        return None


def latest_installed_umu_proton():
    names = set()
    for compat_dir in COMPATIBILITY_DIRS:
        if not os.path.isdir(compat_dir):
            continue
        for entry in os.listdir(compat_dir):
            if entry.startswith("UMU-Proton-") and os.path.isdir(os.path.join(compat_dir, entry)):
                names.add(entry)
    return max(names, key=version_key) if names else None


def update_games_json():
    games = load_json_file_or_none(GAMES_JSON)
    if not games:
        return

    changed = False

    for game in games:
        if game.get("runner") == "Proton-CachyOS":
            game["runner"] = "Proton-CachyOS (System)"
            changed = True

        if game.get("runner") == "":
            game["runner"] = latest_installed_umu_proton() or "Default"
            changed = True

        if game.get("disable_umu") and game.get("runtime") != "disable-runtime":
            game["runtime"] = "disable-runtime"
            changed = True

        if "favorite" in game:
            if game["favorite"] == True:
                game["category"] = False

            game.pop("favorite")
            changed = True

        game_id = game.get("gameid")

        if game_id:
            ico_path = os.path.join(ICONS_DIR, f"{game_id}.ico")
            png_path = os.path.join(ICONS_DIR, f"{game_id}.png")

            if os.path.exists(png_path):
                new_icon_path = png_path
            elif os.path.exists(ico_path):
                new_icon_path = ico_path
            else:
                new_icon_path = png_path

            if game.get("icon") != new_icon_path:
                game["icon"] = new_icon_path
                changed = True

            if game.get("cover"):
                new_cover_path = os.path.join(COVERS_DIR, f"{game_id}.png")
                if game.get("cover") != new_cover_path:
                    game["cover"] = new_cover_path
                    changed = True

    if changed:
        save_json_file(games, GAMES_JSON)


def version_key(v):
    cleaned = re.sub(r'^[^\d]+', '', v)
    parts = re.split(r'(\d+)', cleaned)
    return [int(p) if p.isdigit() else p for p in parts]
