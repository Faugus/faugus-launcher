import calendar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from gi.repository import GLib, Gio

from faugus.language_config import *

_background_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="faugus-backup-worker")


def run_in_background(fn, *args, **kwargs):
    return _background_executor.submit(fn, *args, **kwargs)


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


def expand_path(value):
    if not value:
        return value
    return os.path.expandvars(os.path.expanduser(value))


def load_config():
    return load_json_file(CONFIG_FILE_DIR, default={})


def save_config(config):
    save_json_file(config, CONFIG_FILE_DIR)


def get_dir_inode_map(path):
    sizes = {}
    for dirpath, _dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            sizes[(st.st_dev, st.st_ino)] = st.st_size
    return sizes


def get_dir_size(path):
    return sum(get_dir_inode_map(path).values())


def get_settings_size_bytes():
    combined = {}
    temp_root = os.path.realpath(FAUGUS_TEMP)
    for root in (os.path.dirname(CONFIG_FILE_DIR), FAUGUS_LAUNCHER_SHARE_DIR, FAUGUS_LAUNCHER_STATE_DIR):
        root = os.path.realpath(root)
        if not os.path.isdir(root):
            continue
        for entry in os.scandir(root):
            if entry.path == temp_root:
                continue
            if entry.is_dir(follow_symlinks=False):
                combined.update(get_dir_inode_map(entry.path))
            else:
                try:
                    st = os.lstat(entry.path)
                    combined[(st.st_dev, st.st_ino)] = st.st_size
                except OSError:
                    continue
    return sum(combined.values())


def format_size(num_bytes):
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def get_free_space_bytes(path):
    while path and not os.path.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    if not path:
        return None
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return None


def estimate_backup_size_bytes(prefixes, shortcuts, protons):
    total = get_settings_size_bytes()
    for entry in prefixes:
        if os.path.isdir(entry.get("path", "")):
            total += get_dir_size(entry["path"])
    for entry in shortcuts:
        for file_path in entry.get("files") or []:
            try:
                total += os.path.getsize(file_path)
            except OSError:
                pass
    for entry in protons:
        if os.path.isdir(entry.get("path", "")):
            total += get_dir_size(entry["path"])
    return total


def list_game_prefixes():
    games = load_json_file(GAMES_JSON, default=[])
    result = []
    for game in games:
        if not isinstance(game, dict):
            continue
        if game.get('runner') == 'Steam':
            continue
        prefix = game.get('prefix', '')
        if not prefix:
            continue
        path = expand_path(prefix)
        if not path:
            continue
        gameid = game.get('gameid', '')
        title = game.get('title', '') or gameid
        if not gameid:
            continue
        result.append({"gameid": gameid, "title": title, "path": path, "has_prefix": os.path.isdir(path)})

    result.sort(key=lambda item: item["title"].lower())

    config = load_config()
    default_prefix_base = expand_path(config.get("default-prefix", "").strip('"'))
    if default_prefix_base:
        default_path = os.path.join(default_prefix_base, "default")
        if os.path.isdir(default_path):
            result.insert(0, {"gameid": "default", "title": _("Default Prefix"), "path": default_path, "has_prefix": True})

    return result


def list_installed_protons():
    result = []
    seen = set()
    for compat_dir in COMPATIBILITY_DIRS:
        compat_dir = str(compat_dir)
        if not os.path.isdir(compat_dir):
            continue
        for entry in os.listdir(compat_dir):
            if entry in seen:
                continue
            entry_path = os.path.join(compat_dir, entry)
            if not os.path.isdir(entry_path):
                continue
            seen.add(entry)
            result.append({"gameid": entry, "title": entry, "path": entry_path})

    result.sort(key=lambda item: item["title"].lower())
    return result


def list_faugus_shortcut_files():
    apps, desktop = [], []
    for target_list, base_dir in ((apps, APP_DIR), (desktop, DESKTOP_DIR)):
        base = Path(base_dir)
        if not base.is_dir():
            continue
        for entry in base.glob("*.desktop"):
            try:
                content = entry.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if LAUNCHER_PATH and LAUNCHER_PATH in content:
                target_list.append(entry)
    return apps, desktop


def list_game_prefixes_with_shortcuts():
    items = list_game_prefixes()
    known_gameids = {item["gameid"] for item in items if item["gameid"] != "default"}

    apps_files, desktop_files = list_faugus_shortcut_files()
    all_files = apps_files + desktop_files
    leftover_files = [f for f in all_files if f.stem not in known_gameids]

    for item in items:
        gameid = item["gameid"]
        if gameid == "default":
            item["shortcut_files"] = leftover_files
        else:
            item["shortcut_files"] = [f for f in all_files if f.stem == gameid]

    return items


def send_desktop_notification(title, body):
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            "Notify",
            GLib.Variant("(susssasa{sv}i)", (
                "Faugus", 0, str(FAUGUS_PNG_RASTER), title, body, [], {}, 5000
            )),
            GLib.VariantType.new("(u)"),
            Gio.DBusCallFlags.NONE,
            2000,
            None,
        )
    except GLib.Error:
        pass


def _link_or_copy(src, dst, *, follow_symlinks=True):
    try:
        os.link(src, dst, follow_symlinks=follow_symlinks)
    except OSError:
        shutil.copy2(src, dst, follow_symlinks=follow_symlinks)


def _copy_dir_including(src, dst, included_basenames):
    os.makedirs(dst, exist_ok=True)
    for entry in os.scandir(src):
        if entry.name not in included_basenames:
            continue
        target = os.path.join(dst, entry.name)
        if entry.is_dir():
            shutil.copytree(entry.path, target, dirs_exist_ok=True, copy_function=_link_or_copy)
        else:
            _link_or_copy(entry.path, target)


def perform_backup(dest_path, prefixes=None, shortcuts=None, protons=None, games=None):
    prefixes = prefixes or []
    shortcuts = shortcuts or []
    protons = protons or []
    games = games or []
    dest_path = expand_path(dest_path)
    temp_dir = os.path.join(FAUGUS_TEMP, "temp-backup")
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    manifest = {
        "version": 2,
        "games": [],
        "prefixes": [],
        "shortcuts": [],
        "protons": [],
    }

    settings_dir = os.path.join(temp_dir, "settings")
    temp_root = os.path.realpath(FAUGUS_TEMP)

    all_games = load_json_file(GAMES_JSON, default=[])
    included_image_basenames = set()
    for entry in all_games:
        if not isinstance(entry, dict) or entry.get("gameid") not in games:
            continue
        manifest["games"].append({"gameid": entry["gameid"], "title": entry.get("title", entry["gameid"])})
        included_image_basenames.add(f"{entry['gameid']}.png")
        for field in ("cover", "icon"):
            value = entry.get(field) or ""
            if value:
                included_image_basenames.add(os.path.basename(value))

    faugus_roots = {
        "config": os.path.realpath(os.path.dirname(CONFIG_FILE_DIR)),
        "data": os.path.realpath(FAUGUS_LAUNCHER_SHARE_DIR),
        "state": os.path.realpath(FAUGUS_LAUNCHER_STATE_DIR),
    }
    for root_name, root_path in faugus_roots.items():
        if not os.path.isdir(root_path):
            continue
        dst_root = os.path.join(settings_dir, root_name)
        for entry in os.scandir(root_path):
            if entry.path == temp_root:
                continue
            os.makedirs(dst_root, exist_ok=True)
            target = os.path.join(dst_root, entry.name)
            if entry.name == "games.json":
                filtered_games = [g for g in all_games if isinstance(g, dict) and g.get("gameid") in games]
                save_json_file(filtered_games, target)
            elif entry.name in ("covers", "banners", "icons"):
                _copy_dir_including(entry.path, target, included_image_basenames)
            elif entry.is_dir(follow_symlinks=False):
                shutil.copytree(entry.path, target, dirs_exist_ok=True, copy_function=_link_or_copy)
            else:
                _link_or_copy(entry.path, target)

    for prefix_info in prefixes:
        gameid = prefix_info["gameid"]
        src = prefix_info["path"]
        dst = os.path.join(temp_dir, "prefixes", gameid)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True, copy_function=_link_or_copy)
        manifest["prefixes"].append({
            "gameid": gameid,
            "title": prefix_info["title"],
            "original_path": src,
        })

    for shortcut_info in shortcuts:
        gameid = shortcut_info["gameid"]
        files = shortcut_info.get("files") or []
        dst_dir = os.path.join(temp_dir, "shortcuts", gameid)
        if files:
            os.makedirs(dst_dir, exist_ok=True)
            for f in files:
                shutil.copy2(f, os.path.join(dst_dir, os.path.basename(f)))
        if gameid == "default" and os.path.isdir(SHORTCUT_ICONS_DIR):
            shutil.copytree(SHORTCUT_ICONS_DIR, os.path.join(dst_dir, "icons"), dirs_exist_ok=True, copy_function=_link_or_copy)
        manifest["shortcuts"].append({
            "gameid": gameid,
            "title": shortcut_info["title"],
            "original_paths": [str(f) for f in files],
        })

    for proton_info in protons:
        gameid = proton_info["gameid"]
        src = proton_info["path"]
        dst = os.path.join(temp_dir, "protons", gameid)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True, copy_function=_link_or_copy)
        manifest["protons"].append({
            "gameid": gameid,
            "title": proton_info["title"],
            "original_path": src,
        })

    save_json_file(manifest, os.path.join(temp_dir, "manifest.json"))

    marker_path = os.path.join(temp_dir, ".faugus_marker")
    with open(marker_path, "w") as f:
        f.write("faugus-launcher-backup")

    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    zip_path = os.path.join(FAUGUS_TEMP, f"faugus-launcher-{current_date}")

    shutil.make_archive(zip_path, "tar", temp_dir)
    shutil.rmtree(temp_dir)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path):
        os.remove(dest_path)

    shutil.move(zip_path + ".tar", dest_path)

    return now.strftime("%Y-%m-%d %H:%M")


def resolve_excluded_ids(config, new_key, old_key, all_ids):
    if new_key in config:
        return set(config.get(new_key, []) or [])
    if old_key in config:
        return all_ids - set(config.get(old_key, []) or [])
    return set()


def backup_selection_from_config(config):
    entries = list_game_prefixes_with_shortcuts()
    game_ids = {entry["gameid"] for entry in entries}
    prefix_ids = {entry["gameid"] for entry in entries}
    shortcut_ids = {entry["gameid"] for entry in entries if entry["shortcut_files"]}

    excluded_game_ids = set(config.get('backup-excluded-game-ids', []) or [])
    excluded_prefix_ids = resolve_excluded_ids(config, 'backup-excluded-prefix-ids', 'backup-prefix-ids', prefix_ids)
    excluded_shortcut_ids = resolve_excluded_ids(config, 'backup-excluded-shortcut-ids', 'backup-shortcut-ids', shortcut_ids)
    proton_ids = set(config.get('backup-proton-ids', []) or [])

    games = [gameid for gameid in game_ids if gameid not in excluded_game_ids]
    prefixes = [entry for entry in entries if entry["gameid"] not in excluded_prefix_ids]
    shortcuts = [
        {"gameid": entry["gameid"], "title": entry["title"], "files": entry["shortcut_files"]}
        for entry in entries if entry["shortcut_files"] and entry["gameid"] not in excluded_shortcut_ids
    ]
    protons = [entry for entry in list_installed_protons() if entry["gameid"] in proton_ids]
    return prefixes, shortcuts, protons, games


def run_backup_with_notification(dest_path, prefixes, shortcuts=None, protons=None, games=None):
    send_desktop_notification("Faugus", _("Backup started"))
    new_date = perform_backup(
        dest_path,
        prefixes=prefixes,
        shortcuts=shortcuts,
        protons=protons,
        games=games,
    )
    send_desktop_notification("Faugus", _("Backup completed"))
    return new_date


_MODULE_DAEMON_ARGS = [sys.executable, "-m", "faugus.backup_daemon", "--daemon"]


def _daemon_autostart_exec_args():
    if IS_FLATPAK:
        return ["flatpak", "run", f"--command={LAUNCHER_PATH}", "io.github.Faugus.faugus-launcher", "--daemon"]
    if LAUNCHER_MODULE_ARGS:
        return _MODULE_DAEMON_ARGS
    return [LAUNCHER_PATH, "--daemon"]


def _daemon_spawn_args():
    if LAUNCHER_MODULE_ARGS or IS_FLATPAK:
        return _MODULE_DAEMON_ARGS
    return [LAUNCHER_PATH, "--daemon"]


def _daemon_token_path():
    return os.path.join(FAUGUS_LAUNCHER_STATE_DIR, "daemon.token")


def _perform_scheduled_backup(config):
    dest_dir = config.get('backup-dest-dir', '') or os.path.expanduser("~")
    dest_path = os.path.join(dest_dir, backup_filename())
    prefixes, shortcuts, protons, games = backup_selection_from_config(config)

    needed_bytes = estimate_backup_size_bytes(prefixes, shortcuts, protons)
    free_bytes = get_free_space_bytes(expand_path(dest_dir))
    if free_bytes is not None and needed_bytes > free_bytes:
        send_desktop_notification(
            "Faugus",
            _("Backup failed: not enough disk space ({} needed, {} available).").format(
                format_size(needed_bytes), format_size(free_bytes)),
        )
        suppress_immediate_auto_backup(config)
        return

    new_date = run_backup_with_notification(dest_path, prefixes, shortcuts, protons, games)
    config['backup-last-date'] = new_date
    config['backup-last-auto-date'] = new_date
    save_config(config)


def _run_scheduled_backup_if_due(config):
    if not should_run_backup(config):
        return

    def worker():
        try:
            _perform_scheduled_backup(config)
        except Exception:
            send_desktop_notification("Faugus", _("Automatic backup failed."))
            suppress_immediate_auto_backup(config)

    run_in_background(worker)


_daemon_timer_id = None


def _daemon_timer_tick():
    try:
        _run_scheduled_backup_if_due(load_config())
    except Exception:
        pass
    return True


def _daemon_process_running():
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                with open(f"/proc/{entry.name}/cmdline", "rb") as f:
                    cmdline = f.read().decode(errors="ignore")
            except OSError:
                continue
            if "faugus.backup_daemon" in cmdline and "--daemon" in cmdline:
                return True
    except OSError:
        pass
    return False


def start_daemon_now():
    global _daemon_timer_id
    if _daemon_timer_id is None:
        _daemon_timer_id = GLib.timeout_add_seconds(60, _daemon_timer_tick)
        _daemon_timer_tick()

    if _daemon_process_running():
        return

    try:
        proc = subprocess.Popen(
            _daemon_spawn_args(),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        GLib.child_watch_add(proc.pid, lambda pid, status: None)
    except OSError:
        pass


def stop_daemon():
    global _daemon_timer_id
    if _daemon_timer_id is not None:
        GLib.source_remove(_daemon_timer_id)
        _daemon_timer_id = None

    try:
        os.makedirs(FAUGUS_LAUNCHER_STATE_DIR, exist_ok=True)
        with open(_daemon_token_path(), "w") as f:
            f.write("__stopped__")
    except OSError:
        pass


def setup_autostart(enable):
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, "faugus-backup.desktop")

    if enable:
        os.makedirs(autostart_dir, exist_ok=True)
        exec_line = "Exec=" + " ".join(_daemon_autostart_exec_args()) + "\n"
        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            f.write("Type=Application\n")
            f.write("Name=Faugus Backup Service\n")
            f.write(exec_line)
            f.write("Hidden=false\n")
            f.write("NoDisplay=false\n")
            f.write("X-GNOME-Autostart-enabled=true\n")
        start_daemon_now()
    else:
        if os.path.exists(desktop_file):
            os.remove(desktop_file)
        stop_daemon()


def backup_filename():
    return f"faugus-launcher-{datetime.now().strftime('%Y-%m-%d_%H-%M')}.tar"


def suppress_immediate_auto_backup(config):
    if 'backup-last-auto-date' in config or config.get('backup-auto-enabled') == 'True':
        config['backup-last-auto-date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_config(config)


def get_last_monthly_target(today, target_day):
    def safe_replace(date_obj, day):
        try:
            return date_obj.replace(day=day)
        except ValueError:
            last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
            return date_obj.replace(day=last_day)

    current_month_target = safe_replace(today, target_day)
    if today >= current_month_target:
        return current_month_target

    first_day_current_month = today.replace(day=1)
    last_day_prev_month = first_day_current_month - timedelta(days=1)
    return safe_replace(last_day_prev_month, target_day)


def should_run_backup(config):
    if config.get('backup-auto-enabled', 'False') != 'True':
        return False

    last_backup_str = config.get('backup-last-auto-date', '')

    last_backup = datetime(2000, 1, 1)
    if last_backup_str and last_backup_str.strip():
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                last_backup = datetime.strptime(last_backup_str.strip(), fmt)
                break
            except ValueError:
                continue

    now = datetime.now()
    today = now.date()

    try:
        target_time = datetime.strptime(config.get('backup-target-time', '00:00'), "%H:%M").time()
    except ValueError:
        target_time = datetime.strptime('00:00', "%H:%M").time()

    freq = config.get('backup-frequency', 'daily')
    target_day = int(config.get('backup-target-day', '0'))

    if freq == 'weekly':
        days_ago = (today.weekday() - target_day) % 7
        target_date = today - timedelta(days=days_ago)
    elif freq == 'monthly':
        target_date = get_last_monthly_target(today, target_day)
    else:
        target_date = today

    target_datetime = datetime.combine(target_date, target_time)

    return now >= target_datetime and last_backup < target_datetime


def daemon_mode():
    os.makedirs(FAUGUS_LAUNCHER_STATE_DIR, exist_ok=True)
    token_path = _daemon_token_path()
    my_token = f"{os.getpid()}-{time.time()}"
    with open(token_path, "w") as f:
        f.write(my_token)

    last_check = 0
    while True:
        try:
            with open(token_path) as f:
                current_token = f.read().strip()
        except OSError:
            current_token = my_token
        if current_token != my_token:
            break

        now = time.monotonic()
        if now - last_check >= 60:
            last_check = now
            config = load_config()
            try:
                if should_run_backup(config):
                    _perform_scheduled_backup(config)
            except Exception:
                send_desktop_notification("Faugus", _("Automatic backup failed."))
                suppress_immediate_auto_backup(config)
        time.sleep(5)


_ = setup_gettext('faugus-launcher')


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        daemon_mode()
