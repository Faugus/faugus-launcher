import os
import shutil
import sys
import time
import calendar
import warnings
from pathlib import Path
from datetime import datetime, timedelta
import gi

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, Gio, Gdk
from faugus.language_config import *
from faugus.utils import on_entry_changed, on_entry_query_tooltip, load_red_entry_css, load_frame_css, load_compact_time_spin_css, hide_dialog_action_area, new_file_chooser, destroy_and_release, set_file_chooser_start_folder, load_json_file, save_json_file, build_bottom_button_box, expand_path, run_in_background, add_css_once, show_message_dialog


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
        if not path or not os.path.isdir(path):
            continue
        gameid = game.get('gameid', '')
        title = game.get('title', '') or gameid
        if not gameid:
            continue
        result.append({"gameid": gameid, "title": title, "path": path})

    result.sort(key=lambda item: item["title"].lower())

    config = load_config()
    default_prefix_base = expand_path(config.get("default-prefix", "").strip('"'))
    if default_prefix_base:
        default_path = os.path.join(default_prefix_base, "default")
        if os.path.isdir(default_path):
            result.insert(0, {"gameid": "default", "title": _("Default Prefix"), "path": default_path})

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
    send_desktop_notification(_("Faugus Backup"), _("Backup started"))
    new_date = perform_backup(
        dest_path,
        prefixes=prefixes,
        shortcuts=shortcuts,
        protons=protons,
        games=games,
    )
    send_desktop_notification(_("Faugus Backup"), _("Backup completed"))
    return new_date


def _daemon_exec_args():
    if IS_FLATPAK:
        return ["flatpak", "run", f"--command={LAUNCHER_PATH}", "io.github.Faugus.faugus-launcher", "--daemon"]
    if LAUNCHER_MODULE_ARGS:
        return [sys.executable, "-m", "faugus.backup", "--daemon"]
    return [LAUNCHER_PATH, "--daemon"]


def _daemon_token_path():
    return os.path.join(FAUGUS_LAUNCHER_STATE_DIR, "daemon.token")


def _run_scheduled_backup_if_due(config):
    if not should_run_backup(config):
        return
    dest_dir = config.get('backup-dest-dir', '')
    if not dest_dir:
        dest_dir = os.path.expanduser("~")
    dest_path = os.path.join(dest_dir, backup_filename())
    prefixes, shortcuts, protons, games = backup_selection_from_config(config)

    def worker():
        try:
            new_date = run_backup_with_notification(dest_path, prefixes, shortcuts, protons, games)
            config['backup-last-date'] = new_date
            config['backup-last-auto-date'] = new_date
            save_config(config)
        except Exception:
            pass

    run_in_background(worker)


_daemon_timer_id = None


def _daemon_timer_tick():
    try:
        _run_scheduled_backup_if_due(load_config())
    except Exception:
        pass
    return True


def start_daemon_now():
    global _daemon_timer_id
    if _daemon_timer_id is not None:
        return
    _daemon_timer_id = GLib.timeout_add_seconds(60, _daemon_timer_tick)
    _daemon_timer_tick()


def setup_autostart(enable):
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, "faugus-backup.desktop")

    if enable:
        os.makedirs(autostart_dir, exist_ok=True)
        exec_line = "Exec=" + " ".join(_daemon_exec_args()) + "\n"
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


def backup_filename():
    return f"faugus-launcher-{datetime.now().strftime('%Y-%m-%d_%H-%M')}.tar"


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

    while True:
        try:
            with open(token_path) as f:
                current_token = f.read().strip()
        except OSError:
            current_token = my_token
        if current_token != my_token:
            break

        try:
            config = load_config()
            if should_run_backup(config):
                dest_dir = config.get('backup-dest-dir', '')
                if not dest_dir:
                    dest_dir = os.path.expanduser("~")

                dest_path = os.path.join(dest_dir, backup_filename())

                prefixes, shortcuts, protons, games = backup_selection_from_config(config)
                new_date = run_backup_with_notification(dest_path, prefixes, shortcuts, protons, games)
                config['backup-last-date'] = new_date
                config['backup-last-auto-date'] = new_date
                save_config(config)
        except Exception:
            pass
        time.sleep(60)


_ = setup_gettext('faugus-launcher')


def enable_cursor_cell_highlight(treeview):
    def get_highlight_rgba():
        found, rgba = treeview.get_style_context().lookup_color("theme_selected_bg_color")
        if not found:
            rgba = Gdk.RGBA()
            rgba.parse("#3584e4")
        return rgba

    toggle_entries = [
        (column, renderer)
        for column in treeview.get_columns()
        for renderer in column.get_cells()
        if isinstance(renderer, Gtk.CellRendererToggle)
    ]

    def make_data_func(target_column):
        def data_func(col, cell, model, it, _data=None):
            cursor_path, cursor_column = treeview.get_cursor()
            row_path = model.get_path(it)
            is_cursor = (
                treeview.has_focus()
                and cursor_path is not None
                and cursor_path.to_string() == row_path.to_string()
                and cursor_column is target_column
            )
            cell.set_property("cell-background-set", is_cursor)
            if is_cursor:
                cell.set_property("cell-background-rgba", get_highlight_rgba())
        return data_func

    for column, renderer in toggle_entries:
        column.set_cell_data_func(renderer, make_data_func(column))

    treeview.connect("cursor-changed", lambda tv: tv.queue_draw())

    focus_controller = Gtk.EventControllerFocus()
    focus_controller.connect("enter", lambda c: treeview.queue_draw())
    focus_controller.connect("leave", lambda c: treeview.queue_draw())
    treeview.add_controller(focus_controller)


def load_header_focus_css():
    add_css_once(
        "header_focus_highlight",
        """
        button.header-focus-highlight {
            background-color: @theme_selected_bg_color;
            color: @theme_selected_fg_color;
        }
        """,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


def enable_header_focus_highlight(button):
    load_header_focus_css()
    focus_controller = Gtk.EventControllerFocus()
    focus_controller.connect("enter", lambda c: button.add_css_class("header-focus-highlight"))
    focus_controller.connect("leave", lambda c: button.remove_css_class("header-focus-highlight"))
    button.add_controller(focus_controller)


class _RowCapMixin:
    def _max_height_for_rows(self, max_rows):
        _min, natural, _min_baseline, _natural_baseline = self.treeview.measure(Gtk.Orientation.VERTICAL, -1)
        row_count = max(1, len(self.items))
        visible_rows = min(max_rows, row_count)
        return max(1, int(natural * visible_rows / row_count))

    def _on_treeview_mapped(self, widget):
        GLib.idle_add(self._apply_row_cap)
        return False

    def _apply_row_cap(self):
        self.scrolled_window.set_max_content_height(self._max_height_for_rows(10))
        return False


class PrefixSelectionList(_RowCapMixin):
    def __init__(self, items, size_lookup=None, title_column_label=None, path_column_label=None):
        self.items = items
        self.sizes = {}
        self.inode_maps = {}
        self.total_size_bytes = 0
        self.on_total_changed = None
        self._suppress_select_all = False

        self.liststore = Gtk.ListStore(bool, str, str, str, str)
        for item in items:
            self.liststore.append([False, item["title"], item["path"], _("Calculating..."), item["gameid"]])

        self.treeview = Gtk.TreeView(model=self.liststore)
        self.treeview.set_headers_visible(True)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.NONE)

        self.checkbox_select_all = Gtk.CheckButton()
        self.checkbox_select_all.set_can_target(False)
        self.checkbox_select_all.connect("toggled", self.on_select_all_toggled)

        toggle_renderer = Gtk.CellRendererToggle()
        toggle_renderer.set_property("xalign", 0.0)
        toggle_renderer.set_property("xpad", 4)
        toggle_renderer.connect("toggled", self.on_toggled)
        column_toggle = Gtk.TreeViewColumn("", toggle_renderer, active=0)
        column_toggle.set_widget(self.checkbox_select_all)
        column_toggle.set_clickable(True)
        column_toggle.connect("clicked", self._on_select_all_header_clicked)
        self.treeview.append_column(column_toggle)
        enable_header_focus_highlight(column_toggle.get_button())

        title_renderer = Gtk.CellRendererText()
        column_title = Gtk.TreeViewColumn(title_column_label or _("Game"), title_renderer, text=1)
        column_title.set_expand(True)
        self.treeview.append_column(column_title)

        path_renderer = Gtk.CellRendererText()
        column_path = Gtk.TreeViewColumn(path_column_label or _("Prefix"), path_renderer, text=2)
        column_path.set_expand(True)
        self.treeview.append_column(column_path)

        size_renderer = Gtk.CellRendererText()
        column_size = Gtk.TreeViewColumn(_("Size"), size_renderer, text=3)
        self.treeview.append_column(column_size)

        enable_cursor_cell_highlight(self.treeview)

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_propagate_natural_height(True)
        self.scrolled_window.set_child(self.treeview)
        self.treeview.connect("map", self._on_treeview_mapped)

        self.label_total_size = Gtk.Label(label=_("Total: {}").format(format_size(0)))
        self.label_total_size.set_halign(Gtk.Align.END)
        self.label_total_size.set_hexpand(True)

        self.box_footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_footer.append(self.label_total_size)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.append(self.scrolled_window)
        self.box.append(self.box_footer)

        if size_lookup is None:
            for item in items:
                gameid = item["gameid"]
                self.sizes[gameid] = item.get("size_bytes", 0)
                self.inode_maps[gameid] = {("no-inode-info", gameid): self.sizes[gameid]}
            self.refresh_size_column()
        else:
            run_in_background(self._compute_sizes, size_lookup)

    def _compute_sizes(self, size_lookup):
        for item in self.items:
            gameid = item["gameid"]
            inode_map = size_lookup(item["path"])
            self.inode_maps[gameid] = inode_map
            size_bytes = sum(inode_map.values())
            self.sizes[gameid] = size_bytes
            GLib.idle_add(self._apply_size, gameid, size_bytes)

    def _apply_size(self, gameid, size_bytes):
        for row in self.liststore:
            if row[4] == gameid:
                row[3] = format_size(size_bytes)
                break
        self.update_total_size()
        return False

    def refresh_size_column(self):
        for row in self.liststore:
            row[3] = format_size(self.sizes.get(row[4], 0))
        self.update_total_size()

    def on_toggled(self, renderer, path):
        it = self.liststore.get_iter(path)
        current = self.liststore.get_value(it, 0)
        self.liststore.set_value(it, 0, not current)
        self.sync_select_all_checkbox()
        self.update_total_size()

    def _on_select_all_header_clicked(self, column):
        self.checkbox_select_all.set_active(not self.checkbox_select_all.get_active())

    def on_select_all_toggled(self, widget):
        if self._suppress_select_all:
            return
        value = widget.get_active()
        for row in self.liststore:
            row[0] = value
        self.update_total_size()

    def sync_select_all_checkbox(self):
        all_selected = len(self.liststore) > 0 and all(row[0] for row in self.liststore)
        self._suppress_select_all = True
        self.checkbox_select_all.set_active(all_selected)
        self._suppress_select_all = False

    def update_total_size(self):
        combined = {}
        for row in self.liststore:
            if row[0]:
                combined.update(self.inode_maps.get(row[4], {}))
        total = sum(combined.values())
        self.total_size_bytes = total
        self.label_total_size.set_text(_("Total: {}").format(format_size(total)))
        if self.on_total_changed:
            self.on_total_changed()

    def get_selected(self):
        selected_ids = {row[4] for row in self.liststore if row[0]}
        return [item for item in self.items if item["gameid"] in selected_ids]

    def set_sensitive(self, sensitive):
        self.scrolled_window.set_sensitive(sensitive)
        self.checkbox_select_all.set_sensitive(sensitive)
        self.label_total_size.set_sensitive(sensitive)


class PrefixShortcutList(_RowCapMixin):
    def __init__(self, items, size_lookup=None):
        self.items = items
        self.sizes = {}
        self.inode_maps = {}
        self.shortcut_files = {item["gameid"]: item.get("shortcut_files", []) for item in items}
        self.total_size_bytes = 0
        self.on_total_changed = None
        self._suppress_game_all = False
        self._suppress_prefix_all = False
        self._suppress_shortcut_all = False

        self.liststore = Gtk.ListStore(bool, bool, bool, bool, str, str, str, str)
        for item in items:
            has_shortcut = bool(item.get("shortcut_files"))
            self.liststore.append([False, False, False, has_shortcut, item["title"], item["path"], _("Calculating..."), item["gameid"]])

        self.treeview = Gtk.TreeView(model=self.liststore)
        self.treeview.set_headers_visible(True)
        self.treeview.get_selection().set_mode(Gtk.SelectionMode.NONE)

        self.checkbox_game_all = Gtk.CheckButton()
        self.checkbox_game_all.set_can_target(False)
        self.checkbox_game_all.connect("toggled", self.on_game_all_toggled)
        game_renderer = Gtk.CellRendererToggle()
        game_renderer.set_property("xalign", 0.0)
        game_renderer.set_property("xpad", 4)
        game_renderer.connect("toggled", self.on_game_toggled)
        column_game_toggle = Gtk.TreeViewColumn("", game_renderer, active=0)
        column_game_toggle.set_widget(self.checkbox_game_all)
        column_game_toggle.set_clickable(True)
        column_game_toggle.connect("clicked", self._on_game_header_clicked)
        self.treeview.append_column(column_game_toggle)
        enable_header_focus_highlight(column_game_toggle.get_button())

        title_renderer = Gtk.CellRendererText()
        column_title = Gtk.TreeViewColumn(_("Game/App"), title_renderer, text=4)
        column_title.set_expand(True)
        self.treeview.append_column(column_title)

        self.checkbox_prefix_all = Gtk.CheckButton()
        self.checkbox_prefix_all.set_can_target(False)
        self.checkbox_prefix_all.connect("toggled", self.on_prefix_all_toggled)
        prefix_renderer = Gtk.CellRendererToggle()
        prefix_renderer.set_property("xalign", 0.0)
        prefix_renderer.set_property("xpad", 4)
        prefix_renderer.connect("toggled", self.on_prefix_toggled)
        column_prefix_toggle = Gtk.TreeViewColumn("", prefix_renderer, active=1)
        column_prefix_toggle.set_widget(self.checkbox_prefix_all)
        column_prefix_toggle.set_clickable(True)
        column_prefix_toggle.connect("clicked", self._on_prefix_header_clicked)
        self.treeview.append_column(column_prefix_toggle)
        enable_header_focus_highlight(column_prefix_toggle.get_button())

        path_renderer = Gtk.CellRendererText()
        column_path = Gtk.TreeViewColumn(_("Prefix"), path_renderer, text=5)
        column_path.set_expand(True)
        self.treeview.append_column(column_path)

        self.checkbox_shortcut_all = Gtk.CheckButton()
        self.checkbox_shortcut_all.set_can_target(False)
        self.checkbox_shortcut_all.connect("toggled", self.on_shortcut_all_toggled)
        self.checkbox_shortcut_all.set_sensitive(any(item.get("shortcut_files") for item in items))

        box_shortcut_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box_shortcut_header.append(self.checkbox_shortcut_all)
        box_shortcut_header.append(Gtk.Label(label=_("Shortcuts")))

        shortcut_renderer = Gtk.CellRendererToggle()
        shortcut_renderer.set_property("xalign", 0.0)
        shortcut_renderer.set_property("xpad", 4)
        shortcut_renderer.connect("toggled", self.on_shortcut_toggled)
        column_shortcut_toggle = Gtk.TreeViewColumn("", shortcut_renderer, active=2, visible=3, activatable=3)
        column_shortcut_toggle.set_widget(box_shortcut_header)
        column_shortcut_toggle.set_clickable(True)
        column_shortcut_toggle.connect("clicked", self._on_shortcut_header_clicked)
        self.treeview.append_column(column_shortcut_toggle)
        enable_header_focus_highlight(column_shortcut_toggle.get_button())

        size_renderer = Gtk.CellRendererText()
        column_size = Gtk.TreeViewColumn(_("Size"), size_renderer, text=6)
        self.treeview.append_column(column_size)

        enable_cursor_cell_highlight(self.treeview)

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_window.set_propagate_natural_height(True)
        self.scrolled_window.set_child(self.treeview)
        self.treeview.connect("map", self._on_treeview_mapped)

        self.label_total_size = Gtk.Label(label=_("Total: {}").format(format_size(0)))
        self.label_total_size.set_halign(Gtk.Align.END)
        self.label_total_size.set_hexpand(True)

        self.box_footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_footer.append(self.label_total_size)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.append(self.scrolled_window)
        self.box.append(self.box_footer)

        if size_lookup is None:
            for item in items:
                gameid = item["gameid"]
                self.sizes[gameid] = item.get("size_bytes", 0)
                self.inode_maps[gameid] = {("no-inode-info", gameid): self.sizes[gameid]}
            self.refresh_size_column()
        else:
            run_in_background(self._compute_sizes, size_lookup)

    def _compute_sizes(self, size_lookup):
        for item in self.items:
            gameid = item["gameid"]
            inode_map = size_lookup(item["path"])
            self.inode_maps[gameid] = inode_map
            size_bytes = sum(inode_map.values())
            self.sizes[gameid] = size_bytes
            GLib.idle_add(self._apply_size, gameid, size_bytes)

    def _apply_size(self, gameid, size_bytes):
        for row in self.liststore:
            if row[7] == gameid:
                row[6] = format_size(size_bytes)
                break
        self.update_total_size()
        return False

    def refresh_size_column(self):
        for row in self.liststore:
            row[6] = format_size(self.sizes.get(row[7], 0))
        self.update_total_size()

    def _on_game_header_clicked(self, column):
        self.checkbox_game_all.set_active(not self.checkbox_game_all.get_active())

    def _on_prefix_header_clicked(self, column):
        self.checkbox_prefix_all.set_active(not self.checkbox_prefix_all.get_active())

    def _on_shortcut_header_clicked(self, column):
        if not self.checkbox_shortcut_all.get_sensitive():
            return
        self.checkbox_shortcut_all.set_active(not self.checkbox_shortcut_all.get_active())

    def on_game_toggled(self, renderer, path):
        it = self.liststore.get_iter(path)
        value = not self.liststore.get_value(it, 0)
        has_shortcut = self.liststore.get_value(it, 3)
        self.liststore.set_value(it, 0, value)
        self.liststore.set_value(it, 1, value)
        self.liststore.set_value(it, 2, value and has_shortcut)
        self.sync_game_all_checkbox()
        self.sync_prefix_all_checkbox()
        self.sync_shortcut_all_checkbox()
        self.update_total_size()

    def on_prefix_toggled(self, renderer, path):
        it = self.liststore.get_iter(path)
        current = self.liststore.get_value(it, 1)
        self.liststore.set_value(it, 1, not current)
        self.sync_prefix_all_checkbox()
        self.update_total_size()

    def on_shortcut_toggled(self, renderer, path):
        it = self.liststore.get_iter(path)
        if not self.liststore.get_value(it, 3):
            return
        current = self.liststore.get_value(it, 2)
        self.liststore.set_value(it, 2, not current)
        self.sync_shortcut_all_checkbox()

    def on_game_all_toggled(self, widget):
        if self._suppress_game_all:
            return
        value = widget.get_active()
        it = self.liststore.get_iter_first()
        while it is not None:
            has_shortcut = self.liststore.get_value(it, 3)
            self.liststore.set_value(it, 0, value)
            self.liststore.set_value(it, 1, value)
            self.liststore.set_value(it, 2, value and has_shortcut)
            it = self.liststore.iter_next(it)
        self.sync_prefix_all_checkbox()
        self.sync_shortcut_all_checkbox()
        self.update_total_size()

    def on_prefix_all_toggled(self, widget):
        if self._suppress_prefix_all:
            return
        value = widget.get_active()
        for row in self.liststore:
            row[1] = value
        self.update_total_size()

    def on_shortcut_all_toggled(self, widget):
        if self._suppress_shortcut_all:
            return
        value = widget.get_active()
        for row in self.liststore:
            if row[3]:
                row[2] = value

    def sync_game_all_checkbox(self):
        all_selected = len(self.liststore) > 0 and all(row[0] for row in self.liststore)
        self._suppress_game_all = True
        self.checkbox_game_all.set_active(all_selected)
        self._suppress_game_all = False

    def sync_prefix_all_checkbox(self):
        all_selected = len(self.liststore) > 0 and all(row[1] for row in self.liststore)
        self._suppress_prefix_all = True
        self.checkbox_prefix_all.set_active(all_selected)
        self._suppress_prefix_all = False

    def sync_shortcut_all_checkbox(self):
        eligible = [row for row in self.liststore if row[3]]
        all_selected = len(eligible) > 0 and all(row[2] for row in eligible)
        self._suppress_shortcut_all = True
        self.checkbox_shortcut_all.set_active(all_selected)
        self._suppress_shortcut_all = False

    def update_total_size(self):
        combined = {}
        for row in self.liststore:
            if row[1]:
                combined.update(self.inode_maps.get(row[7], {}))
        total = sum(combined.values())
        self.total_size_bytes = total
        self.label_total_size.set_text(_("Total: {}").format(format_size(total)))
        if self.on_total_changed:
            self.on_total_changed()

    def get_selected_games(self):
        return [row[7] for row in self.liststore if row[0]]

    def get_selected_prefixes(self):
        selected_ids = {row[7] for row in self.liststore if row[1]}
        return [item for item in self.items if item["gameid"] in selected_ids]

    def get_selected_shortcuts(self):
        selected_ids = {row[7] for row in self.liststore if row[2] and row[3]}
        result = []
        for item in self.items:
            if item["gameid"] in selected_ids:
                result.append({
                    "gameid": item["gameid"],
                    "title": item["title"],
                    "files": self.shortcut_files.get(item["gameid"], []),
                })
        return result


class BackupWindow(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title=_("Backup Settings"), transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)
        self.connect("response", lambda d, r: destroy_and_release(d))

        self.config = load_config()

        load_red_entry_css()
        load_frame_css()

        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.get_content_area().append(self.root_box)

        self.frame = Gtk.Frame()
        self.frame.set_margin_start(10)
        self.frame.set_margin_end(10)
        self.frame.set_margin_top(10)
        self.frame.set_margin_bottom(10)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.frame.set_child(self.main_box)
        self.root_box.append(self.frame)

        self.box_columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20, homogeneous=True)
        self.main_box.append(self.box_columns)

        self.box_column_auto = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box_columns.append(self.box_column_auto)

        self.box_column_dest = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box_columns.append(self.box_column_dest)

        self.box_column_action = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box_columns.append(self.box_column_action)

        self.prefix_items = list_game_prefixes_with_shortcuts()
        self.prefix_list = PrefixShortcutList(self.prefix_items, size_lookup=get_dir_inode_map)
        self.main_box.append(self.prefix_list.box)

        self.proton_items = list_installed_protons()
        self.proton_list = PrefixSelectionList(
            self.proton_items, size_lookup=get_dir_inode_map,
            title_column_label=_("Proton"), path_column_label=_("Path"))
        self.main_box.append(self.proton_list.box)

        prefix_gameids = {item["gameid"] for item in self.prefix_items}
        shortcut_gameids = {item["gameid"] for item in self.prefix_items if item.get("shortcut_files")}
        excluded_game_ids = set(self.config.get('backup-excluded-game-ids', []) or [])
        excluded_prefix_ids = resolve_excluded_ids(
            self.config, 'backup-excluded-prefix-ids', 'backup-prefix-ids', prefix_gameids)
        excluded_shortcut_ids = resolve_excluded_ids(
            self.config, 'backup-excluded-shortcut-ids', 'backup-shortcut-ids', shortcut_gameids)

        it = self.prefix_list.liststore.get_iter_first()
        while it is not None:
            gameid = self.prefix_list.liststore.get_value(it, 7)
            has_shortcut = self.prefix_list.liststore.get_value(it, 3)
            self.prefix_list.liststore.set_value(it, 0, gameid not in excluded_game_ids)
            self.prefix_list.liststore.set_value(it, 1, gameid not in excluded_prefix_ids)
            self.prefix_list.liststore.set_value(it, 2, has_shortcut and gameid not in excluded_shortcut_ids)
            it = self.prefix_list.liststore.iter_next(it)
        self.prefix_list.sync_game_all_checkbox()
        self.prefix_list.sync_prefix_all_checkbox()
        self.prefix_list.sync_shortcut_all_checkbox()
        self.prefix_list.update_total_size()

        saved_proton_ids = set(self.config.get('backup-proton-ids', []) or [])
        if saved_proton_ids:
            for row in self.proton_list.liststore:
                if row[4] in saved_proton_ids:
                    row[0] = True
            self.proton_list.sync_select_all_checkbox()
            self.proton_list.update_total_size()

        self.label_backup_destination = Gtk.Label(label=_("Backup Destination"))
        self.label_backup_destination.set_halign(Gtk.Align.START)
        self.box_column_dest.append(self.label_backup_destination)

        dest_dir = self.config.get('backup-dest-dir', '')
        if not dest_dir:
            dest_dir = os.path.expanduser(PathManager.user_home('Faugus Backup'))

        self.box_dest = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry_dest = Gtk.Entry()
        self.entry_dest.connect("changed", on_entry_changed)
        self.entry_dest.set_text(dest_dir)
        self.entry_dest.set_hexpand(True)
        self.entry_dest.set_tooltip_text(_("Backup destination path"))
        self.entry_dest.set_has_tooltip(True)
        self.entry_dest.connect("query-tooltip", on_entry_query_tooltip)
        self.button_browse = Gtk.Button()
        self.button_browse.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_browse.connect("clicked", self.on_browse_clicked)
        self.button_browse.set_size_request(50, -1)
        self.box_dest.append(self.entry_dest)
        self.box_dest.append(self.button_browse)
        self.box_column_dest.append(self.box_dest)

        last_date = self.config.get('backup-last-date')
        if not last_date or not last_date.strip():
            last_date = _("No backup yet")
        self.label_last_backup = Gtk.Label(label="{} {}".format(_("Last backup:"), last_date))
        self.label_last_backup.set_halign(Gtk.Align.START)
        self.box_column_action.append(self.label_last_backup)

        self.button_backup_now = Gtk.Button(label=_("Backup now"))
        self.button_backup_now.connect("clicked", self.on_backup_now_clicked)
        self.box_column_action.append(self.button_backup_now)

        self.settings_size_bytes = 0
        self.prefix_list.on_total_changed = self.update_backup_button_label
        self.proton_list.on_total_changed = self.update_backup_button_label
        self.update_backup_button_label()
        run_in_background(self._compute_settings_size)

        self.box_switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.label_automatic_backup = Gtk.Label(label=_("Automatic Backup"))
        self.label_automatic_backup.set_halign(Gtk.Align.START)
        self.box_switch.append(self.label_automatic_backup)
        self.box_column_auto.append(self.box_switch)

        self.backup_weekday_choices = [
            ("Monday", _("Monday")),
            ("Tuesday", _("Tuesday")),
            ("Wednesday", _("Wednesday")),
            ("Thursday", _("Thursday")),
            ("Friday", _("Friday")),
            ("Saturday", _("Saturday")),
            ("Sunday", _("Sunday")),
        ]
        self.backup_frequency = 'daily'
        self.backup_target_day = 0

        self.backupfreq_actions = Gio.SimpleActionGroup()

        self.action_backup_frequency = Gio.SimpleAction.new_stateful(
            "frequency", GLib.VariantType.new("s"), GLib.Variant.new_string(self.backup_frequency))
        self.action_backup_frequency.connect("activate", self.on_backup_frequency_action)
        self.backupfreq_actions.add_action(self.action_backup_frequency)

        self.action_backup_weekday = Gio.SimpleAction.new_stateful(
            "weekday", GLib.VariantType.new("s"), GLib.Variant.new_string(self.backup_weekday_choices[0][0]))
        self.action_backup_weekday.connect("activate", self.on_backup_weekday_action)
        self.backupfreq_actions.add_action(self.action_backup_weekday)

        self.insert_action_group("backupfreq", self.backupfreq_actions)

        self.box_time = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        def format_two_digits(spin):
            spin.set_text(f"{int(spin.get_value()):02d}")
            return True

        def hide_spin_arrows(spin):
            child = spin.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                if isinstance(child, Gtk.Button):
                    child.set_visible(False)
                child = nxt

        load_compact_time_spin_css()

        adj_hour = Gtk.Adjustment(value=0, lower=0, upper=23, step_increment=1, page_increment=1, page_size=0)
        self.spin_hour = Gtk.SpinButton(adjustment=adj_hour, numeric=True)
        self.spin_hour.set_wrap(True)
        self.spin_hour.set_width_chars(2)
        self.spin_hour.set_max_width_chars(2)
        self.spin_hour.add_css_class("compact-time-spin")
        self.spin_hour.set_alignment(0.5)
        hide_spin_arrows(self.spin_hour)
        self.spin_hour.connect("output", format_two_digits)

        adj_minute = Gtk.Adjustment(value=0, lower=0, upper=59, step_increment=1, page_increment=5, page_size=0)
        self.spin_minute = Gtk.SpinButton(adjustment=adj_minute, numeric=True)
        self.spin_minute.set_wrap(True)
        self.spin_minute.set_width_chars(2)
        self.spin_minute.set_max_width_chars(2)
        self.spin_minute.add_css_class("compact-time-spin")
        self.spin_minute.set_alignment(0.5)
        hide_spin_arrows(self.spin_minute)
        self.spin_minute.connect("output", format_two_digits)

        self.box_time.append(self.spin_hour)
        self.box_time.append(Gtk.Label(label=":"))
        self.box_time.append(self.spin_minute)

        self.button_backup_frequency = Gtk.MenuButton()
        self.button_backup_frequency.set_hexpand(True)
        self.label_backup_frequency = Gtk.Label()
        self.button_backup_frequency.set_child(self.label_backup_frequency)

        self.box_freq_time = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_freq_time.append(self.button_backup_frequency)
        self.box_freq_time.append(self.box_time)
        self.box_column_auto.append(self.box_freq_time)

        self.monthday_grid = Gtk.Grid()
        self.monthday_grid.set_row_spacing(2)
        self.monthday_grid.set_column_spacing(2)
        self.monthday_grid.set_column_homogeneous(True)
        self.monthday_grid.set_margin_start(6)
        self.monthday_grid.set_margin_end(6)
        self.monthday_grid.set_margin_top(6)
        self.monthday_grid.set_margin_bottom(6)
        self.monthday_buttons = {}
        for day in range(1, 32):
            button = Gtk.Button(label=str(day))
            button.set_hexpand(True)
            button.connect("clicked", self.on_monthday_button_clicked, day)
            self.monthday_buttons[day] = button
            row, col = divmod(day - 1, 7)
            self.monthday_grid.attach(button, col, row, 1, 1)

        target_time = self.config.get('backup-target-time', '00:00')
        try:
            hour_val, minute_val = target_time.split(":")
            self.spin_hour.set_value(int(hour_val))
            self.spin_minute.set_value(int(minute_val))
        except ValueError:
            pass

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.set_hexpand(True)
        self.button_cancel.connect("clicked", self.on_cancel_clicked)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.set_hexpand(True)
        self.button_ok.connect("clicked", self.on_ok_clicked)

        self.bottom_box = build_bottom_button_box(self.button_cancel, self.button_ok)

        self.root_box.append(self.bottom_box)

        auto_enabled = self.config.get('backup-auto-enabled', 'False') == 'True'
        freq_val = self.config.get('backup-frequency', 'daily')
        target_day = int(self.config.get('backup-target-day', '0'))
        if not auto_enabled:
            self.backup_frequency = 'disabled'
            self.backup_target_day = 0
        elif freq_val == 'weekly' and 0 <= target_day < 7:
            self.backup_frequency = 'weekly'
            self.backup_target_day = target_day
        elif freq_val == 'monthly' and 1 <= target_day <= 31:
            self.backup_frequency = 'monthly'
            self.backup_target_day = target_day
        else:
            self.backup_frequency = 'daily'
            self.backup_target_day = 0

        self.action_backup_frequency.set_state(GLib.Variant.new_string(self.backup_frequency))
        if self.backup_frequency == 'weekly':
            self.action_backup_weekday.set_state(
                GLib.Variant.new_string(self.backup_weekday_choices[self.backup_target_day][0]))

        self.button_backup_frequency.set_menu_model(self.build_backup_frequency_menu())
        self.button_backup_frequency.get_popover().add_child(self.monthday_grid, "monthdays")

        self.update_monthday_grid_selection()
        self.update_backup_frequency_label()

        self.update_ui_state()

    def build_backup_frequency_menu(self):
        menu = Gio.Menu()

        disabled_item = Gio.MenuItem.new(_("Disabled"), None)
        disabled_item.set_action_and_target_value("backupfreq.frequency", GLib.Variant.new_string("disabled"))
        menu.append_item(disabled_item)

        daily_item = Gio.MenuItem.new(_("Daily"), None)
        daily_item.set_action_and_target_value("backupfreq.frequency", GLib.Variant.new_string("daily"))
        menu.append_item(daily_item)

        weekly_menu = Gio.Menu()
        for day_id, day_name in self.backup_weekday_choices:
            item = Gio.MenuItem.new(day_name, None)
            item.set_action_and_target_value("backupfreq.weekday", GLib.Variant.new_string(day_id))
            weekly_menu.append_item(item)
        menu.append_submenu(_("Weekly"), weekly_menu)

        monthly_menu = Gio.Menu()
        monthday_item = Gio.MenuItem.new()
        monthday_item.set_attribute_value("custom", GLib.Variant.new_string("monthdays"))
        monthly_menu.append_item(monthday_item)
        menu.append_submenu(_("Monthly"), monthly_menu)

        return menu

    def update_monthday_grid_selection(self):
        for day, button in self.monthday_buttons.items():
            is_current = self.backup_frequency == 'monthly' and self.backup_target_day == day
            if is_current:
                button.add_css_class("suggested-action")
            else:
                button.remove_css_class("suggested-action")

    def update_backup_frequency_label(self):
        if self.backup_frequency == 'weekly':
            day_name = self.backup_weekday_choices[self.backup_target_day][1]
            label = "{} ({})".format(_("Weekly"), day_name)
        elif self.backup_frequency == 'monthly':
            label = "{} ({})".format(_("Monthly"), _("Day {}").format(self.backup_target_day))
        elif self.backup_frequency == 'disabled':
            label = _("Disabled")
        else:
            label = _("Daily")
        self.label_backup_frequency.set_text(label)

    def on_backup_frequency_action(self, action, param):
        action.set_state(param)
        self.backup_frequency = param.get_string()
        if self.backup_frequency != 'weekly':
            self.backup_target_day = 0
        self.update_backup_frequency_label()
        self.update_monthday_grid_selection()
        self.update_ui_state()

    def on_backup_weekday_action(self, action, param):
        action.set_state(param)
        day_id = param.get_string()
        day_ids = [entry[0] for entry in self.backup_weekday_choices]
        self.backup_frequency = 'weekly'
        self.backup_target_day = day_ids.index(day_id)
        self.action_backup_frequency.set_state(GLib.Variant.new_string('weekly'))
        self.update_backup_frequency_label()
        self.update_monthday_grid_selection()
        self.update_ui_state()

    def on_monthday_button_clicked(self, button, day):
        self.backup_frequency = 'monthly'
        self.backup_target_day = day
        self.action_backup_frequency.set_state(GLib.Variant.new_string('monthly'))
        self.update_backup_frequency_label()
        self.update_monthday_grid_selection()
        self.update_ui_state()
        popover = self.button_backup_frequency.get_popover()
        if popover:
            popover.popdown()

    def update_ui_state(self):
        is_active = self.backup_frequency != 'disabled'

        self.spin_hour.set_sensitive(is_active)
        self.spin_minute.set_sensitive(is_active)

    def on_browse_clicked(self, widget):
        filechooser = new_file_chooser(
            self,
            _("Select the backup destination"),
            Gtk.FileChooserAction.SELECT_FOLDER,
        )
        entry_value = self.entry_dest.get_text()
        set_file_chooser_start_folder(filechooser, "backup_destination", expand_path(entry_value) or None)

        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                self.entry_dest.set_text(dialog.get_file().get_path())
            destroy_and_release(dialog)

        filechooser.connect("response", on_response)
        filechooser.present()

    def current_selection(self):
        prefixes = self.prefix_list.get_selected_prefixes()
        shortcuts = self.prefix_list.get_selected_shortcuts()
        protons = self.proton_list.get_selected()
        games = self.prefix_list.get_selected_games()
        return prefixes, shortcuts, protons, games

    def _compute_settings_size(self):
        size = get_settings_size_bytes()
        GLib.idle_add(self._apply_settings_size, size)

    def _apply_settings_size(self, size):
        self.settings_size_bytes = size
        self.update_backup_button_label()
        return False

    def update_backup_button_label(self):
        total = self.settings_size_bytes + self.prefix_list.total_size_bytes + self.proton_list.total_size_bytes
        self.button_backup_now.set_label(_("Backup now ({})").format(format_size(total)))

    def on_backup_now_clicked(self, widget):
        if not self.entry_dest.get_text():
            self.entry_dest.add_css_class("entry")
            return
        dest_dir = self.entry_dest.get_text()
        if not dest_dir:
            dest_dir = os.path.expanduser("~")

        dest_path = os.path.join(dest_dir, backup_filename())

        prefixes, shortcuts, protons, games = self.current_selection()

        self.button_backup_now.set_sensitive(False)
        self.button_backup_now.set_label(_("Backing up..."))

        def do_backup():
            try:
                new_date = run_backup_with_notification(dest_path, prefixes, shortcuts, protons, games)
                self.config['backup-last-date'] = new_date
                save_config(self.config)
                GLib.idle_add(self.on_backup_finished, new_date)
            except Exception:
                GLib.idle_add(self.on_backup_finished, None)

        run_in_background(do_backup)

    def on_backup_finished(self, new_date):
        self.button_backup_now.set_sensitive(True)
        self.update_backup_button_label()
        if new_date:
            self.label_last_backup.set_text("{} {}".format(_("Last backup:"), new_date))
        return False

    def on_cancel_clicked(self, widget):
        destroy_and_release(self)

    def on_ok_clicked(self, widget):
        is_enabled = self.backup_frequency != 'disabled'
        self.config['backup-auto-enabled'] = str(is_enabled)

        self.config['backup-frequency'] = self.backup_frequency
        self.config['backup-target-day'] = str(self.backup_target_day)

        self.config['backup-target-time'] = f"{int(self.spin_hour.get_value()):02d}:{int(self.spin_minute.get_value()):02d}"

        self.config['backup-dest-dir'] = self.entry_dest.get_text()

        prefixes, shortcuts, protons, games = self.current_selection()
        self.config['backup-excluded-game-ids'] = [row[7] for row in self.prefix_list.liststore if not row[0]]
        self.config['backup-excluded-prefix-ids'] = [row[7] for row in self.prefix_list.liststore if not row[1]]
        self.config['backup-excluded-shortcut-ids'] = [row[7] for row in self.prefix_list.liststore if row[3] and not row[2]]
        self.config.pop('backup-prefix-ids', None)
        self.config.pop('backup-shortcut-ids', None)
        self.config['backup-proton-ids'] = [item["gameid"] for item in protons]

        save_config(self.config)

        setup_autostart(is_enabled)

        if is_enabled and should_run_backup(self.config):
            try:
                dest_dir = self.config.get('backup-dest-dir', '')
                if not dest_dir:
                    dest_dir = os.path.expanduser("~")
                dest_path = os.path.join(dest_dir, backup_filename())

                new_date = run_backup_with_notification(dest_path, prefixes, shortcuts, protons, games)
                self.config['backup-last-date'] = new_date
                self.config['backup-last-auto-date'] = new_date
                save_config(self.config)
            except Exception:
                pass

        destroy_and_release(self)


class RestoreWindow(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title=_("Restore Backup"), transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        self.temp_dir = None
        self.is_closed = False

        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.get_content_area().append(self.root_box)

        self.frame = Gtk.Frame()
        self.frame.set_margin_start(10)
        self.frame.set_margin_end(10)
        self.frame.set_margin_top(10)
        self.frame.set_margin_bottom(10)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.frame.set_child(self.main_box)
        self.root_box.append(self.frame)

        self.progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.progress_box.set_margin_top(40)
        self.progress_box.set_margin_bottom(40)

        self.progress_label = Gtk.Label(label=_("Extracting backup..."))
        self.progress_box.append(self.progress_label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(280, -1)
        self.progress_box.append(self.progress_bar)

        self.main_box.append(self.progress_box)
        self.progress_timer_id = GLib.timeout_add(100, self._pulse_progress)

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.set_hexpand(True)
        self.button_cancel.connect("clicked", self.on_cancel_clicked)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.set_hexpand(True)
        self.button_ok.connect("clicked", self.on_ok_clicked)
        self.button_ok.set_sensitive(False)

        self.bottom_box = build_bottom_button_box(self.button_cancel, self.button_ok)
        self.root_box.append(self.bottom_box)

    def _pulse_progress(self):
        self.progress_bar.pulse()
        return True

    def load_content(self, temp_dir, manifest):
        self.temp_dir = temp_dir

        manifest_shortcuts = manifest.get("shortcuts", [])
        manifest_prefixes = manifest.get("prefixes", [])
        manifest_protons = manifest.get("protons", [])

        shortcuts_by_gameid = {group["gameid"]: group for group in manifest_shortcuts}

        items = []
        seen_gameids = set()
        for entry in manifest_prefixes:
            gameid = entry["gameid"]
            seen_gameids.add(gameid)
            src = os.path.join(temp_dir, "prefixes", gameid)
            size_bytes = get_dir_size(src) if os.path.isdir(src) else 0
            shortcut_group = shortcuts_by_gameid.get(gameid)
            items.append({
                "gameid": gameid,
                "title": entry.get("title", gameid),
                "path": entry.get("original_path", ""),
                "size_bytes": size_bytes,
                "shortcut_files": shortcut_group.get("original_paths", []) if shortcut_group else [],
            })

        for gameid, group in shortcuts_by_gameid.items():
            if gameid in seen_gameids:
                continue
            items.append({
                "gameid": gameid,
                "title": group.get("title", gameid),
                "path": "",
                "size_bytes": 0,
                "shortcut_files": group.get("original_paths", []),
            })

        self.prefix_list = PrefixShortcutList(items)
        for row in self.prefix_list.liststore:
            row[0] = True
            row[1] = True
            row[2] = row[3]
        self.prefix_list.sync_game_all_checkbox()
        self.prefix_list.sync_prefix_all_checkbox()
        self.prefix_list.sync_shortcut_all_checkbox()
        self.prefix_list.update_total_size()
        self.main_box.append(self.prefix_list.box)

        proton_items = []
        for entry in manifest_protons:
            src = os.path.join(temp_dir, "protons", entry["gameid"])
            size_bytes = get_dir_size(src) if os.path.isdir(src) else 0
            proton_items.append({
                "gameid": entry["gameid"],
                "title": entry.get("title", entry["gameid"]),
                "path": entry.get("original_path", ""),
                "size_bytes": size_bytes,
            })

        self.proton_list = PrefixSelectionList(
            proton_items, title_column_label=_("Proton"), path_column_label=_("Path"))
        for row in self.proton_list.liststore:
            row[0] = True
        self.proton_list.sync_select_all_checkbox()
        self.proton_list.update_total_size()
        self.main_box.append(self.proton_list.box)

        self.button_ok.set_sensitive(True)
        self._hide_progress()

    def _recenter(self):
        self.set_visible(False)
        GLib.idle_add(self._recenter_after_load)

    def _recenter_after_load(self):
        self.present()
        return False

    def _show_progress(self, text):
        self.progress_label.set_text(text)
        self.progress_box.set_visible(True)
        if hasattr(self, "prefix_list"):
            self.prefix_list.box.set_visible(False)
        if hasattr(self, "proton_list"):
            self.proton_list.box.set_visible(False)
        if self.progress_timer_id is None:
            self.progress_timer_id = GLib.timeout_add(100, self._pulse_progress)
        self._recenter()

    def _hide_progress(self):
        if self.progress_timer_id is not None:
            GLib.source_remove(self.progress_timer_id)
            self.progress_timer_id = None
        self.progress_box.set_visible(False)
        self.prefix_list.box.set_visible(True)
        self.proton_list.box.set_visible(True)
        self._recenter()

    def discard(self):
        self.is_closed = True
        if self.progress_timer_id is not None:
            GLib.source_remove(self.progress_timer_id)
            self.progress_timer_id = None
        destroy_and_release(self)

    def on_cancel_clicked(self, widget):
        shutil.rmtree(FAUGUS_TEMP, ignore_errors=True)
        self.discard()

    def on_ok_clicked(self, widget):
        def on_confirm(ok):
            if not ok:
                return

            self.is_closed = True
            self.button_ok.set_sensitive(False)
            self.button_cancel.set_sensitive(False)
            self._show_progress(_("Restoring backup..."))

            temp_dir = self.temp_dir
            selected_shortcuts = self.prefix_list.get_selected_shortcuts()
            selected_prefixes = self.prefix_list.get_selected_prefixes()
            selected_protons = self.proton_list.get_selected()

            def restore_worker():
                error = None
                try:
                    restore_settings(os.path.join(temp_dir, "settings"))

                    for item in selected_shortcuts:
                        restore_shortcut_group(temp_dir, item["gameid"], item["files"])

                    for item in selected_prefixes:
                        restore_backup_item(temp_dir, "prefixes", item["gameid"], item["path"])

                    for item in selected_protons:
                        restore_backup_item(temp_dir, "protons", item["gameid"], item["path"])

                    shutil.rmtree(FAUGUS_TEMP, ignore_errors=True)
                except Exception as e:
                    error = e
                GLib.idle_add(finish_restore, error)

            def finish_restore(error):
                if error is not None:
                    self.is_closed = False
                    self._hide_progress()
                    self.button_ok.set_sensitive(True)
                    self.button_cancel.set_sensitive(True)
                    show_message_dialog(
                        _("Failed to restore backup:") + f"\n{error}",
                        parent=self,
                        confirm_label=_("Ok"),
                    )
                    return False

                self.response(Gtk.ResponseType.OK)
                return False

            run_in_background(restore_worker)

        show_message_dialog(
            _("Are you sure you want to overwrite the settings?"),
            parent=self,
            confirm_label=_("Yes"),
            cancel_label=_("No"),
            callback=on_confirm,
        )


def restore_settings(settings_dir):
    if not os.path.isdir(settings_dir):
        return

    keep = os.path.realpath(FAUGUS_TEMP)
    for root in (os.path.dirname(CONFIG_FILE_DIR), FAUGUS_LAUNCHER_SHARE_DIR, FAUGUS_LAUNCHER_STATE_DIR):
        root = os.path.realpath(root)
        for entry in os.scandir(root) if os.path.isdir(root) else []:
            if entry.path == keep:
                continue
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)
        os.makedirs(root, exist_ok=True)

    faugus_roots = {
        "config": os.path.realpath(os.path.dirname(CONFIG_FILE_DIR)),
        "data": os.path.realpath(FAUGUS_LAUNCHER_SHARE_DIR),
        "state": os.path.realpath(FAUGUS_LAUNCHER_STATE_DIR),
    }

    if any(os.path.isdir(os.path.join(settings_dir, name)) for name in faugus_roots):
        for root_name, root_path in faugus_roots.items():
            src_root = os.path.join(settings_dir, root_name)
            if not os.path.isdir(src_root):
                continue
            os.makedirs(root_path, exist_ok=True)
            for entry in os.scandir(src_root):
                target = os.path.join(root_path, entry.name)
                if entry.is_dir():
                    shutil.copytree(entry.path, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(entry.path, target)
        return

    for item in os.listdir(settings_dir):
        _restore_flat_item(item, os.path.join(settings_dir, item))


def _restore_flat_item(item, src, wipe_existing=False):
    dst = BACKUP_ITEMS.get(item) or LEGACY_BACKUP_DIR_ITEMS.get(item)
    if dst is None:
        legacy = LEGACY_FORMAT_ITEMS.get(item)
        if legacy is None:
            return
        dst, kind = legacy
        convert_legacy_format_file(src, dst, kind)
        return

    if wipe_existing:
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        elif os.path.isfile(dst):
            os.remove(dst)

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)
    elif os.path.isfile(src):
        shutil.copy2(src, dst)


def restore_shortcut_group(temp_dir, gameid, original_paths):
    src_dir = os.path.join(temp_dir, "shortcuts", gameid)
    if not os.path.isdir(src_dir):
        return

    for original_path in original_paths:
        src = os.path.join(src_dir, os.path.basename(original_path))
        if os.path.isfile(src):
            os.makedirs(os.path.dirname(original_path), exist_ok=True)
            shutil.copy2(src, original_path)

    if gameid == "default":
        icons_src = os.path.join(src_dir, "icons")
        if os.path.isdir(icons_src):
            os.makedirs(SHORTCUT_ICONS_DIR, exist_ok=True)
            shutil.copytree(icons_src, SHORTCUT_ICONS_DIR, dirs_exist_ok=True)


def restore_backup_item(temp_dir, category, item_id, original_path):
    src = os.path.join(temp_dir, category, item_id)
    if not os.path.isdir(src) or not original_path:
        return
    os.makedirs(os.path.dirname(original_path), exist_ok=True)
    if os.path.isdir(original_path):
        shutil.rmtree(original_path)
    shutil.copytree(src, original_path, symlinks=True)


def restore_legacy_flat(temp_dir):
    for item in os.listdir(temp_dir):
        if item == ".faugus_marker":
            continue
        _restore_flat_item(item, os.path.join(temp_dir, item), wipe_existing=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        daemon_mode()
