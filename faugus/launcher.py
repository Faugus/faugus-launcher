#!/usr/bin/python3

import shutil
import subprocess
import sys
import threading
import gi
import vdf
import signal

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, AyatanaAppIndicator3, Pango
from faugus.config_manager import *
from faugus.utils import *
from faugus.steam_setup import *
from faugus.ea_fix import *

VERSION = "1.22.6"

faugus_banner = PathManager.system_data('faugus-launcher/faugus-banner.png')
icons_dir = PathManager.user_config('faugus-launcher/icons')
banners_dir = PathManager.user_config('faugus-launcher/banners')
backup_dir = PathManager.user_config("faugus-launcher/games-backup")
faugus_mono_icon = PathManager.get_icon('faugus-mono.svg')

if IS_FLATPAK:
    tray_icon = 'io.github.Faugus.faugus-launcher'
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
    mono_dest = Path(PathManager.user_data('faugus-launcher/faugus-mono.svg'))
    mono_dest.parent.mkdir(parents=True, exist_ok=True)
    if not mono_dest.exists():
        shutil.copy(faugus_mono_icon, mono_dest)
    faugus_mono_icon = PathManager.user_data('faugus-launcher/faugus-mono.svg')
else:
    tray_icon = PathManager.get_icon('faugus-launcher.svg')
    GLib.set_prgname("faugus-launcher")

latest_games = PathManager.user_config('faugus-launcher/latest-games.txt')
categories_file = PathManager.user_config('faugus-launcher/categories.txt')
custom_order = PathManager.user_config('faugus-launcher/custom-order.json')
presets_file = PathManager.user_config('faugus-launcher/presets.json')
faugus_launcher_share_dir = PathManager.user_data('faugus-launcher')
faugus_temp = PathManager.user_data('faugus-launcher/faugus_temp')
running_games = PathManager.user_data('faugus-launcher/running_games.json')

os.makedirs(compatibility_dir, exist_ok=True)

faugus_backup = False

os.makedirs(faugus_launcher_share_dir, exist_ok=True)
os.makedirs(faugus_launcher_dir, exist_ok=True)

_ = setup_gettext('faugus-launcher')

def convert_runner(runner):
    if runner == "Proton-CachyOS Latest":
        return "Proton-CachyOS Latest (default)"

    if runner == "Proton-CachyOS Latest (default)":
        return "Proton-CachyOS Latest"

    if runner == "Proton-GE Latest":
        return "GE-Proton Latest"

    if runner == "GE-Proton Latest":
        return "Proton-GE Latest"

    if runner == "UMU-Proton Latest":
        return ""

    if runner == "":
        return "UMU-Proton Latest"

    return runner

class FaugusApp(Gtk.Application):
    def __init__(self, start_hidden=False):
        super().__init__(application_id="io.github.Faugus.faugus-launcher")
        self.window = None
        self.start_hidden = start_hidden

    def do_startup(self):
        Gtk.Application.do_startup(self)

        app_icon_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "share", "icons"
        )
        app_icon_dir = os.path.normpath(app_icon_dir)
        if os.path.isdir(app_icon_dir):
            Gtk.IconTheme.get_default().prepend_search_path(app_icon_dir)

        apply_dark_theme()

    def do_activate(self):
        if not self.window:
            self.window = Main(self)

            if self.start_hidden:
                self.window.hide()
                return

        self.window.present()

class Main(Gtk.ApplicationWindow, HiDpiMixin):
    def __init__(self, app):
        super().__init__(application=app, title="Faugus Launcher")
        self.connect("delete-event", self.on_close)
        self.set_wmclass("faugus-launcher", "faugus-launcher")
        print(f"Faugus Launcher {VERSION}")

        self.fullscreen_activated = False
        self.system_tray = False
        self.indicator = False
        self.mono_icon = False

        self.current_prefix = None
        self.games = []

        self.last_click_time = 0
        self.last_clicked_item = None
        self.double_click_time_threshold = 400

        self.processes = {}

        if not os.path.exists(running_games):
            save_json_file({}, running_games)

        self.running = load_json_file(running_games, {})
        if not isinstance(self.running, dict):
            self.running = {}

        self.provider = Gtk.CssProvider()
        self.provider.load_from_data(b"""
            .game {
                background-color: alpha(@theme_base_color, 0.5);
                color: @theme_text_color;
            }
            flowboxchild:selected {
                background: transparent;
            }
            flowboxchild:selected .game {
                background-color: alpha(@theme_selected_bg_color, 0.5);
            }
            flowboxchild:selected:focus .game {
                background-color: @theme_selected_bg_color;
                color: @theme_bg_color;
            }
            .banner-container {
                border: 8px solid transparent;
                padding: 0px;
            }
            flowboxchild.banner-container:selected {
                border-color: alpha(@theme_selected_bg_color, 0.5);
            }
            flowboxchild.banner-container:selected:focus {
                border-color: @theme_selected_bg_color;
                box-shadow: 0 0 5px 0 @theme_selected_bg_color;
            }
            .launch-overlay {
                background-color: @theme_text_color;
                opacity: 0;
                transition: opacity 0.8s ease-out;
            }
            .launch-overlay.playing {
                opacity: 0.5;
                transition: opacity 0.05s ease-in;
            }
            button.flash-btn {
                transition: background-color 0.3s ease-out, opacity 0.3s ease-out;
            }
            button.flash-btn.flashing {
                background-color: alpha(@theme_text_color, 0.3);
                opacity: 0.5;
                transition: background-color 0.05s ease-in, opacity 0.05s ease-in;
            }
            .category-list {
                background-color: alpha(@theme_base_color, 0.5);
            }
            .category-list row {
                background-color: transparent;
                color: @theme_text_color;
            }
            .category-list row:selected {
                background-color: alpha(@theme_selected_bg_color, 0.5);
            }
            .category-list row:selected:focus {
                background-color: @theme_selected_bg_color;
                color: @theme_bg_color;
                outline: none;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.context_menu = Gtk.Menu()

        self.menu_title = Gtk.MenuItem(label="")
        self.menu_title.set_sensitive(False)
        self.context_menu.append(self.menu_title)

        self.menu_playtime = Gtk.MenuItem(label="")
        self.menu_playtime.set_sensitive(False)

        self.context_menu.append(Gtk.SeparatorMenuItem())

        self.menu_play = Gtk.MenuItem(label=_("Play"))
        self.menu_play.connect("activate", self.on_context_menu_play)
        self.context_menu.append(self.menu_play)

        self.menu_edit = Gtk.MenuItem(label=_("Edit"))
        self.menu_edit.connect("activate", self.on_context_menu_edit)
        self.context_menu.append(self.menu_edit)

        self.menu_delete = Gtk.MenuItem(label=_("Delete"))
        self.menu_delete.connect("activate", self.on_context_menu_delete)
        self.context_menu.append(self.menu_delete)

        self.menu_duplicate = Gtk.MenuItem(label=_("Duplicate"))
        self.menu_duplicate.connect("activate", self.on_context_menu_duplicate)
        self.context_menu.append(self.menu_duplicate)

        self.menu_hide = Gtk.MenuItem(label=_("Hide"))
        self.menu_hide.connect("activate", self.on_context_menu_hide)
        self.context_menu.append(self.menu_hide)

        self.menu_category = Gtk.MenuItem(label=_("Category"))
        self.submenu_category = Gtk.Menu()
        self.menu_category.set_submenu(self.submenu_category)
        self.context_menu.append(self.menu_category)

        self.menu_game_location = Gtk.MenuItem(label=_("Open game location"))
        self.menu_game_location.connect("activate", self.on_context_menu_game_location)
        self.context_menu.append(self.menu_game_location)

        self.menu_prefix_location = Gtk.MenuItem(label=_("Open prefix location"))
        self.menu_prefix_location.connect("activate", self.on_context_menu_prefix_location)
        self.context_menu.append(self.menu_prefix_location)

        self.menu_run = Gtk.MenuItem(label=_("Run file inside the prefix"))
        self.menu_run.connect("activate", self.on_context_menu_run)
        self.context_menu.append(self.menu_run)

        self.menu_show_logs = Gtk.MenuItem(label=_("Show logs"))
        self.menu_show_logs.connect("activate", self.on_context_show_logs)

        self.load_config()

        if self.interface_mode == "List":
            self.setup_interface()
        if self.interface_mode in ("Blocks", "Banners"):
            if self.window_behavior == "Maximized":
                self.maximize()
            if self.window_behavior == "Fullscreen":
                self.fullscreen()
                self.fullscreen_activated = True
            self.setup_interface(True)
        if not self.interface_mode:
            self.interface_mode = "List"
            self.setup_interface()

        self.flowbox.connect("button-press-event", self.on_item_right_click)
        self.flowbox.connect("selected-children-changed", lambda *_: self.update_icon())

        self.load_tray_icon()

        if self.gamepad_navigation:
            import faugus.gamepad as gamepad
            gamepad.init_gamepad(self)

        GLib.timeout_add(1000, self.check_running)

    def update_icon(self):
        game = self.selected()
        gameid = game.gameid if game else None

        is_running = gameid in self.running if gameid else False
        icon = "faugus-stop-symbolic" if is_running else "faugus-play-symbolic"
        text = _("Stop") if is_running else _("Play")

        self.button_play.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        self.menu_play.get_child().set_text(text)

        if IS_FLATPAK:
            self.button_play.set_sensitive(not is_running)
            self.menu_play.set_sensitive(not is_running)

    def selected(self):
        selected_items = self.flowbox.get_selected_children()
        if not selected_items:
            return None
        return getattr(selected_items[0], 'game', None)

    def check_running(self):
        changed = False

        for gameid, proc in list(self.processes.items()):
            if proc.poll() is not None:
                del self.processes[gameid]
                self.running.pop(gameid, None)
                changed = True

        for gameid, pid in list(self.running.items()):
            if gameid not in self.processes:
                try:
                    if isinstance(pid, dict):
                        pid = next(iter(pid.values()))
                    os.kill(pid, 0)
                except OSError:
                    del self.running[gameid]
                    changed = True

        if changed:
            self.save_running()

        if self.running or changed:
            self.update_icon()

        return True

    def save_running(self):
        save_json_file(self.running, running_games)

    def load_tray_icon(self):
        if not self.system_tray:
            if self.indicator:
                self.indicator.set_status(
                    AyatanaAppIndicator3.IndicatorStatus.PASSIVE
                )
            return

        if not self.indicator:
            icon = faugus_mono_icon if self.mono_icon else tray_icon
            self.indicator = AyatanaAppIndicator3.Indicator.new(
                "faugus-launcher",
                icon,
                AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            self.indicator.set_icon_theme_path("")
            self.indicator.set_status(
                AyatanaAppIndicator3.IndicatorStatus.ACTIVE
            )

        menu = Gtk.Menu()

        games_by_id = {g.gameid: g for g in self.games}

        if os.path.exists(latest_games):
            with open(latest_games) as f:
                added_count = 0
                for gameid in map(str.strip, f):
                    if added_count >= 5:
                        break

                    game = games_by_id.get(gameid)
                    if not game:
                        continue

                    item = Gtk.MenuItem(label=game.title)
                    item.connect("activate", self.on_game_selected, game)
                    menu.append(item)
                    added_count += 1

        if menu.get_children():
            menu.append(Gtk.SeparatorMenuItem())

        restore_item = Gtk.MenuItem(label=_("Open Faugus Launcher"))
        restore_item.connect("activate", self.restore_window)
        menu.append(restore_item)

        quit_item = Gtk.MenuItem(label=_("Quit"))
        quit_item.connect("activate", self.on_quit)
        menu.append(quit_item)

        menu.show_all()

        icon = faugus_mono_icon if self.mono_icon else tray_icon
        self.indicator.set_menu(menu)
        self.indicator.set_icon_full(icon, "Faugus Launcher")
        self.indicator.set_status(
            AyatanaAppIndicator3.IndicatorStatus.ACTIVE
        )

    def on_game_selected(self, widget, game):
        if game.gameid in self.running:
            self.running_dialog(game.title)
        else:
            self.on_button_play_clicked(None, game)

    def save_interface_settings(self):
        config = ConfigManager()

        if self.window_behavior == "Remember":
            width, height = self.get_size()
            config.set_value("width", width)
            config.set_value("height", height)

        if self.banner_size:
            config.set_value("banner-size", self.banner_size)

        if hasattr(self, 'current_sort_id'):
            config.set_value("sort", self.current_sort_id)

        if hasattr(self, 'current_category'):
            cat = self.current_category
            if cat == _("All") or cat is None:
                cat_id = "all"
            elif cat == _("Uncategorized"):
                cat_id = "uncategorized"
            else:
                cat_id = cat
            config.set_value("category", cat_id)

        config.save_config()

    def on_close(self, *args):
        self.save_interface_settings()

        if self.system_tray:
            self.hide()
            return True

        if self.indicator:
            self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        self.get_application().quit()
        return False

    def restore_window(self, *_):
        self.show_all()
        self.present()

    def on_quit(self, *_):
        if self.indicator:
            self.indicator.set_status(
                AyatanaAppIndicator3.IndicatorStatus.PASSIVE
            )
        self.get_application().quit()

    def select_first_child(self):
        for child in self.flowbox.get_children():
            if child.get_child_visible():
                self.flowbox.grab_focus()
                self.flowbox.select_child(child)
                child.grab_focus()
                self.flowbox.emit("child-activated", child)
                break

    def select_game_by_title(self, title):
        for child in self.flowbox.get_children():
            if hasattr(child, 'game') and child.game and child.game.title == title:
                self.flowbox.grab_focus()
                self.flowbox.select_child(child)
                child.grab_focus()
                self.flowbox.emit("child-activated", child)
                break

    def setup_interface(self, is_big=False):
        if is_big:
            self.set_default_size(1280, 720)
            self.set_resizable(True)
            if self.window_behavior == "Remember":
                self.resize(self.window_width, self.window_height)
        else:
            self.set_default_size(-1, 610)
            self.set_resizable(False)

        self.box_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def create_button(icon_name, callback, tooltip=None):
            btn = Gtk.Button()
            btn.get_style_context().add_class("flash-btn")

            def trigger_flash(widget):
                style_ctx = widget.get_style_context()
                style_ctx.add_class("flashing")

                def remove_flash():
                    style_ctx.remove_class("flashing")
                    return False

                GLib.timeout_add(50, remove_flash)

            btn.connect("clicked", trigger_flash)
            btn.connect("clicked", callback)

            btn.set_size_request(50, 50)
            btn.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
            if tooltip:
                btn.set_tooltip_text(tooltip)
            return btn

        self.button_add = create_button("faugus-add-symbolic", self.on_button_add_clicked)
        self.button_settings = create_button("faugus-settings-symbolic", self.on_button_settings_clicked)
        self.button_kill = create_button("faugus-kill-symbolic", self.on_button_kill_clicked, _("Force close all running games"))
        self.button_play = create_button("faugus-play-symbolic", self.on_button_play_clicked)

        self.entry_search = Gtk.Entry()
        self.entry_search.set_placeholder_text(_("Search..."))
        self.entry_search.connect("changed", self.on_search_changed)
        self.entry_search.set_size_request(170, 50)

        self.opt_alpha = _("Alphabetical")
        self.opt_playtime = _("Playtime")
        self.opt_lastplayed = _("Last played")
        self.opt_custom = _("Custom")

        self.sort_map = {
            "alpha": self.opt_alpha,
            "playtime": self.opt_playtime,
            "lastplayed": self.opt_lastplayed,
            "custom": self.opt_custom
        }

        self.current_sort_id = getattr(self, "sort", "alpha")

        if self.current_sort_id not in self.sort_map:
            self.current_sort_id = "alpha"
        self.current_sort = self.sort_map[self.current_sort_id]

        saved_category = getattr(self, "category", "all")
        if saved_category == "all":
            self.current_category = _("All")
        elif saved_category == "uncategorized":
            self.current_category = _("Uncategorized")
        else:
            self.current_category = saved_category

        self.playtime_data = {}
        self.latest_games_order = {}
        self.custom_order_data = {}

        self.button_category = Gtk.Button(label=self.current_category)
        self.button_category.set_size_request(110, -1)
        self.button_category.connect("clicked", self.on_category_button_clicked)

        self.button_sort = Gtk.Button(label=self.current_sort)
        self.button_sort.set_size_request(110, -1)

        def update_sort_data():
            self.playtime_data.clear()
            try:
                data = load_json_file(games_json, [])
                for item in data:
                    if isinstance(item, dict) and "gameid" in item:
                        self.playtime_data[item["gameid"]] = item.get("playtime", 0)
            except:
                pass

            self.latest_games_order.clear()
            try:
                if os.path.exists(latest_games):
                    with open(latest_games) as f:
                        for idx, gid in enumerate(map(str.strip, f)):
                            self.latest_games_order[gid] = idx
            except:
                pass

            self.custom_order_data.clear()
            try:
                if os.path.exists(custom_order):
                    with open(custom_order, "r") as f:
                        self.custom_order_data.update(json.load(f))
            except:
                pass

        def on_sort_button_clicked(widget):
            popover = Gtk.Popover.new(widget)
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            vbox.set_margin_top(10)
            vbox.set_margin_bottom(10)
            vbox.set_margin_start(10)
            vbox.set_margin_end(10)

            focus_btn = None
            for s_id, s_label in self.sort_map.items():
                btn = Gtk.Button(label=s_label)
                if s_id == self.current_sort_id:
                    focus_btn = btn

                def set_sort(btn_widget, target_id=s_id, target_label=s_label):
                    self.current_sort_id = target_id
                    self.current_sort = target_label
                    self.button_sort.set_label(target_label)
                    update_sort_data()
                    self.flowbox.invalidate_sort()
                    popover.popdown()

                btn.connect("clicked", set_sort)
                btn.set_relief(Gtk.ReliefStyle.NONE)
                vbox.pack_start(btn, False, False, 0)

            vbox.show_all()
            popover.add(vbox)
            popover.popup()

            if focus_btn:
                focus_btn.grab_focus()

        self.button_sort.connect("clicked", on_sort_button_clicked)

        adjustment = Gtk.Adjustment(value=self.banner_size, lower=50, upper=100, step_increment=10, page_increment=10, page_size=0)
        self.zoom_slider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        self.zoom_slider.set_size_request(150, -1)
        self.zoom_slider.set_draw_value(True)
        self.zoom_slider.set_digits(0)
        self.zoom_slider.set_margin_end(10)

        def on_zoom_changed(widget):
            val = widget.get_value()
            snapped = round(val / 10.0) * 10.0
            if val != snapped:
                widget.set_value(snapped)
                return

            zoom_pct = int(snapped)

            if hasattr(self, '_last_zoom') and self._last_zoom == zoom_pct:
                return
            self._last_zoom = zoom_pct
            self.banner_size = zoom_pct

            if hasattr(self, 'flowbox'):
                for child in self.flowbox.get_children():
                    if not hasattr(child, 'game') or not child.game:
                        continue
                    game = child.game

                    if self.interface_mode == "Banners" and hasattr(child, 'banner'):
                        banner_path = game.banner if os.path.isfile(game.banner) else faugus_banner
                        zoom_width = int(230 * (zoom_pct / 100.0))
                        zoom_height = int(zoom_width * 1.5)
                        surface = self.get_game_artwork(banner_path, game, zoom_width, zoom_height)
                        child.banner.set_from_surface(surface)

        self.zoom_slider.connect("value-changed", on_zoom_changed)

        scroll_box = Gtk.ScrolledWindow()
        scroll_box.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll_box.set_margin_top(10)
        scroll_box.set_margin_bottom(10)
        scroll_box.set_margin_start(10)
        scroll_box.set_margin_end(10)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.connect('button-release-event', self.on_item_release_event)

        def setup_dnd_for_widget(fb_child):
            if not isinstance(fb_child, Gtk.FlowBoxChild):
                return

            inner = fb_child.get_child()
            if not inner:
                return

            if isinstance(inner, Gtk.EventBox) and getattr(inner, 'is_dnd_wrapper', False):
                ev_box = inner
            else:
                fb_child.remove(inner)
                ev_box = Gtk.EventBox()
                ev_box.is_dnd_wrapper = True
                ev_box.add(inner)
                ev_box.show_all()
                fb_child.add(ev_box)

            targets = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]

            ev_box.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.MOVE)
            fb_child.drag_dest_set(Gtk.DestDefaults.ALL, targets, Gdk.DragAction.MOVE)

            def get_game(w):
                if hasattr(w, 'game') and w.game: return w.game
                if hasattr(w, 'get_child'):
                    c = w.get_child()
                    if hasattr(c, 'game') and c.game: return c.game
                    if hasattr(c, 'get_child'):
                        cc = c.get_child()
                        if hasattr(cc, 'game') and cc.game: return cc.game
                p = w.get_parent()
                while p:
                    if hasattr(p, 'game') and p.game: return p.game
                    p = p.get_parent()
                return None

            def on_drag_begin(widget, drag_context):
                g = get_game(widget)
                if g:
                    self._drag_source_id = g.gameid
                    parent = widget.get_parent()
                    if isinstance(parent, Gtk.FlowBoxChild):
                        self.flowbox.select_child(parent)

                    try:
                        if hasattr(g, 'icon') and g.icon:
                            if os.path.isfile(g.icon):
                                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(g.icon, 48, 48, True)
                            else:
                                theme = Gtk.IconTheme.get_default()
                                pixbuf = theme.load_icon(g.icon, 48, 0)

                            if pixbuf:
                                Gtk.drag_set_icon_pixbuf(drag_context, pixbuf, 24, 24)
                                return
                    except Exception:
                        pass

                Gtk.drag_set_icon_default(drag_context)

            def on_drag_data_get(widget, drag_context, selection_data, info, time):
                g = get_game(widget)
                if g:
                    selection_data.set_text(g.gameid, -1)

            def on_drag_motion(widget, drag_context, x, y, time):
                if self.current_sort_id != "custom" or not getattr(self, '_drag_source_id', None):
                    return False

                target_g = get_game(widget)
                if not target_g:
                    return False

                source_id = self._drag_source_id
                target_id = target_g.gameid

                if source_id == target_id:
                    Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
                    return True

                ordered = []

                for child in self.flowbox.get_children():
                    g = get_game(child)
                    if g:
                        ordered.append(g.gameid)

                ordered.sort(key=lambda gid: self.custom_order_data.get(gid, 999999))

                try:
                    src = ordered.index(source_id)
                    dst = ordered.index(target_id)
                except ValueError:
                    return False

                if src != dst:
                    ordered.pop(src)
                    ordered.insert(dst, source_id)

                    for idx, gid in enumerate(ordered):
                        self.custom_order_data[gid] = idx

                    self.flowbox.invalidate_sort()

                Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
                return True

            def on_drag_data_received(widget, drag_context, x, y, selection_data, info, time):
                drag_context.finish(True, False, time)

            def on_drag_end(widget, drag_context):
                self._drag_source_id = None
                if self.current_sort_id == "custom":
                    try:
                        with open(custom_order, "w") as f:
                            json.dump(self.custom_order_data, f)
                    except:
                        pass

            try:
                ev_box.disconnect_by_func(on_drag_begin)
                ev_box.disconnect_by_func(on_drag_data_get)
                ev_box.disconnect_by_func(on_drag_end)
                fb_child.disconnect_by_func(on_drag_motion)
                fb_child.disconnect_by_func(on_drag_data_received)
            except:
                pass

            ev_box.connect("drag-begin", on_drag_begin)
            ev_box.connect("drag-data-get", on_drag_data_get)
            ev_box.connect("drag-end", on_drag_end)
            fb_child.connect("drag-motion", on_drag_motion)
            fb_child.connect("drag-data-received", on_drag_data_received)

        def on_child_added(container, widget):
            def apply_dnd():
                parent = widget.get_parent()
                if parent and isinstance(parent, Gtk.FlowBoxChild):
                    setup_dnd_for_widget(parent)
                elif isinstance(widget, Gtk.FlowBoxChild):
                    setup_dnd_for_widget(widget)
                return False
            GLib.idle_add(apply_dnd)

        self.flowbox.connect('add', on_child_added)

        if is_big:
            self.flowbox.set_halign(Gtk.Align.CENTER)
            self.flowbox.set_valign(Gtk.Align.CENTER)
            self.flowbox.set_min_children_per_line(2)
            self.flowbox.set_max_children_per_line(20)
        else:
            self.flowbox.set_halign(Gtk.Align.FILL)
            self.flowbox.set_valign(Gtk.Align.START)

        def sort_games(child1, child2, user_data):
            g1 = getattr(child1, 'game', None) or getattr(child1.get_child(), 'game', None)
            g2 = getattr(child2, 'game', None) or getattr(child2.get_child(), 'game', None)

            if g1 and g2:
                if self.current_sort_id == "playtime":
                    pt1 = self.playtime_data.get(g1.gameid, 0)
                    pt2 = self.playtime_data.get(g2.gameid, 0)
                    if pt1 != pt2:
                        return (pt1 < pt2) - (pt1 > pt2)

                elif self.current_sort_id == "lastplayed":
                    idx1 = self.latest_games_order.get(g1.gameid, float('inf'))
                    idx2 = self.latest_games_order.get(g2.gameid, float('inf'))
                    if idx1 != idx2:
                        return (idx1 > idx2) - (idx1 < idx2)

                elif self.current_sort_id == "custom":
                    idx1 = self.custom_order_data.get(g1.gameid, 999999)
                    idx2 = self.custom_order_data.get(g2.gameid, 999999)
                    if idx1 != idx2:
                        return (idx1 > idx2) - (idx1 < idx2)

            return (g1.title > g2.title) - (g1.title < g2.title) if g1 and g2 else 0

        def filter_games(child, user_data):
            game = getattr(child, 'game', None) or getattr(child.get_child(), 'game', None)
            if not game:
                return False

            search_text = self.entry_search.get_text().lower()
            matches_search = search_text in game.title.lower() if search_text else True
            matches_category = True

            if getattr(self, 'show_categories', True) and self.current_category and self.current_category != _("All"):
                raw_cat = game.category

                if isinstance(raw_cat, str):
                    game_cats = [raw_cat]
                elif isinstance(raw_cat, list):
                    game_cats = raw_cat
                else:
                    game_cats = []

                if self.current_category == _("Uncategorized"):
                    matches_category = not game_cats or game_cats == [_("None")]
                else:
                    if not game_cats:
                        game_cats = [_("None")]
                    matches_category = (self.current_category in game_cats)

            return matches_search and matches_category

        self.flowbox.set_sort_func(sort_games, None)
        self.flowbox.set_filter_func(filter_games, None)
        scroll_box.add(self.flowbox)

        if is_big:
            self.main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.box_main.pack_start(self.main_hbox, True, True, 0)

            right_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.main_hbox.pack_start(right_vbox, True, True, 0)

            if self.interface_mode != "Banners":
                self.zoom_slider.set_no_show_all(True)

            bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            bottom_bar.set_margin_top(5)
            bottom_bar.set_margin_bottom(10)
            bottom_bar.set_margin_start(10)
            bottom_bar.set_margin_end(10)

            bottom_bar.pack_start(self.zoom_slider, False, False, 0)

            if getattr(self, 'show_categories', True):
                box_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                box_actions.set_margin_start(10)
                box_actions.pack_start(self.button_sort, False, False, 0)
                box_actions.pack_start(self.button_category, False, False, 0)
                bottom_bar.pack_end(box_actions, False, False, 0)

            center_grid = Gtk.Grid()
            center_grid.set_column_spacing(10)
            center_grid.attach(self.button_add, 0, 0, 1, 1)
            center_grid.attach(self.button_settings, 1, 0, 1, 1)
            center_grid.attach(self.entry_search, 2, 0, 1, 1)
            center_grid.attach(self.button_kill, 3, 0, 1, 1)
            center_grid.attach(self.button_play, 4, 0, 1, 1)

            bottom_bar.set_center_widget(center_grid)

            right_vbox.pack_start(scroll_box, True, True, 0)
            right_vbox.pack_start(bottom_bar, False, False, 0)

        else:
            self.box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.box_bottom = Gtk.Box()

            if getattr(self, 'show_categories', True):
                top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                top_bar.set_margin_top(10)
                top_bar.set_margin_start(10)
                top_bar.set_margin_end(10)
                self.button_sort.set_hexpand(True)
                self.button_category.set_hexpand(True)
                top_bar.pack_start(self.button_sort, True, True, 0)
                top_bar.pack_start(self.button_category, True, True, 0)
                self.box_top.pack_start(top_bar, False, False, 0)

            self.box_top.pack_start(scroll_box, True, True, 0)

            grid_controls = Gtk.Grid()
            grid_controls.set_column_spacing(10)
            grid_controls.set_margin_bottom(10)
            grid_controls.set_margin_start(10)
            grid_controls.set_margin_end(10)
            self.entry_search.set_hexpand(True)

            grid_controls.attach(self.button_add,   0, 0, 1, 1)
            grid_controls.attach(self.button_settings,   1, 0, 1, 1)
            grid_controls.attach(self.entry_search, 2, 0, 1, 1)
            grid_controls.attach(self.button_kill,       3, 0, 1, 1)
            grid_controls.attach(self.button_play,  4, 0, 1, 1)

            self.box_bottom.pack_start(grid_controls, True, True, 0)

            self.box_main.pack_start(self.box_top, True, True, 0)
            self.box_main.pack_end(self.box_bottom, False, True, 0)

        update_sort_data()
        self.load_games()

        for child in self.flowbox.get_children():
            setup_dnd_for_widget(child)

        self.add(self.box_main)
        self.select_first_child()
        self.connect("key-press-event", self.on_key_press_event)
        self.show_all()

    def on_category_button_clicked(self, button):
        popover = Gtk.Popover.new(button)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        categories = [_("All"), _("Uncategorized")] + self._get_current_categories()
        current_label = self.button_category.get_label()
        focus_btn = None

        for cat_name in categories:
            btn = Gtk.Button(label=cat_name)
            if cat_name == current_label:
                focus_btn = btn
            btn.set_relief(Gtk.ReliefStyle.NONE)
            def set_category(btn_widget, cat=cat_name):
                self.on_category_menu_item_selected(btn_widget, cat)
                popover.popdown()
            btn.connect("clicked", set_category)
            vbox.pack_start(btn, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(5)
        separator.set_margin_bottom(5)
        vbox.pack_start(separator, False, False, 0)

        btn_manage = Gtk.Button(label=_("Manage categories..."))
        btn_manage.set_relief(Gtk.ReliefStyle.NONE)

        def manage_categories(btn_widget):
            popover.popdown()
            GLib.idle_add(self.on_manage_categories_clicked, btn_widget)

        btn_manage.connect("clicked", manage_categories)
        vbox.pack_start(btn_manage, False, False, 0)

        vbox.show_all()
        popover.add(vbox)
        popover.popup()

        if focus_btn:
            focus_btn.grab_focus()

    def on_category_menu_item_selected(self, menu_item, category_name):
        self.button_category.set_label(category_name)
        self.current_category = category_name

        if hasattr(self, 'flowbox'):
            self.flowbox.invalidate_filter()

    def on_manage_categories_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Manage Categories"), parent=self)
        dialog.set_modal(True)
        dialog.set_resizable(False)
        dialog.set_default_size(300, 400)

        box = dialog.get_content_area()

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        listbox = Gtk.ListBox()
        listbox.get_style_context().add_class("category-list")
        scroll.add(listbox)
        frame.add(scroll)

        box.pack_start(frame, True, True, 0)

        def populate_dialog_list():
            for child in listbox.get_children():
                listbox.remove(child)

            for c in self._get_current_categories():
                row = Gtk.ListBoxRow()
                row.set_size_request(-1, 40)
                lbl = Gtk.Label(label=c, xalign=0)
                lbl.set_margin_start(10)
                row.add(lbl)
                row.category_name = c
                listbox.add(row)

            listbox.show_all()

        populate_dialog_list()

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        btn_box.set_margin_start(10)
        btn_box.set_margin_end(10)
        btn_box.set_margin_bottom(10)

        btn_add = Gtk.Button(label=_("Add"))
        btn_edit = Gtk.Button(label=_("Edit"))
        btn_remove = Gtk.Button(label=_("Remove"))

        btn_add.set_hexpand(True)
        btn_edit.set_hexpand(True)
        btn_remove.set_hexpand(True)

        btn_box.pack_start(btn_add, True, True, 0)
        btn_box.pack_start(btn_edit, True, True, 0)
        btn_box.pack_start(btn_remove, True, True, 0)

        box.pack_start(btn_box, False, False, 0)

        def on_add(b):
            row = Gtk.ListBoxRow()
            row.set_size_request(-1, 40)
            entry = Gtk.Entry()
            entry.set_margin_start(10)
            entry.set_margin_end(10)
            row.add(entry)
            row.category_name = None

            listbox.add(row)
            listbox.show_all()
            listbox.select_row(row)
            entry.grab_focus()

            finished = False

            def finish_add():
                nonlocal finished
                if finished:
                    return False
                finished = True

                new_cat = entry.get_text().strip()
                reserved_names = [_("None"), _("All"), _("Uncategorized")]
                cats = self._get_current_categories()

                if not new_cat or new_cat in reserved_names or new_cat in cats:
                    if row.get_parent():
                        listbox.remove(row)
                    return False

                cats.append(new_cat)
                self._save_categories(sorted(cats, key=str.lower))
                populate_dialog_list()
                return False

            entry.connect("activate", lambda e: finish_add())
            entry.connect("focus-out-event", lambda e, ev: GLib.idle_add(finish_add))

        def on_edit(b):
            selected_row = listbox.get_selected_row()
            if not selected_row:
                return

            old_cat = getattr(selected_row, 'category_name', None)
            if not old_cat:
                return

            old_child = selected_row.get_child()
            if isinstance(old_child, Gtk.Entry):
                return

            old_label = old_child.get_text()
            selected_row.remove(old_child)

            entry = Gtk.Entry()
            entry.set_margin_start(10)
            entry.set_margin_end(10)
            entry.set_text(old_label)
            selected_row.add(entry)

            listbox.show_all()
            entry.grab_focus()
            entry.set_position(-1)

            finished = False

            def restore_label(text):
                current_child = selected_row.get_child()
                if current_child:
                    selected_row.remove(current_child)
                lbl = Gtk.Label(label=text, xalign=0)
                lbl.set_margin_start(10)
                selected_row.add(lbl)
                selected_row.category_name = text
                listbox.show_all()

            def finish_edit():
                nonlocal finished
                if finished:
                    return False
                finished = True

                new_cat = entry.get_text().strip()
                reserved_names = [_("None"), _("All"), _("Uncategorized")]
                cats = self._get_current_categories()

                if not new_cat or new_cat == old_cat or new_cat in reserved_names or new_cat in cats:
                    restore_label(old_label)
                    return False

                if old_cat in cats:
                    idx = cats.index(old_cat)
                    cats[idx] = new_cat
                    self._save_categories(sorted(cats, key=str.lower))
                    self._update_games_category(old_cat, new_cat)

                    if self.current_category == old_cat:
                        self.current_category = new_cat
                        self.button_category.set_label(new_cat)

                    self.flowbox.invalidate_filter()

                populate_dialog_list()
                return False

            entry.connect("activate", lambda e: finish_edit())
            entry.connect("focus-out-event", lambda e, ev: GLib.idle_add(finish_edit))

        def on_remove(b):
            selected_row = listbox.get_selected_row()
            if not selected_row:
                return

            cat_to_remove = getattr(selected_row, 'category_name', None)
            if not cat_to_remove:
                return

            cats = self._get_current_categories()
            if cat_to_remove in cats:
                cats.remove(cat_to_remove)
                self._save_categories(cats)
                self._remove_games_category(cat_to_remove)

                if self.current_category == cat_to_remove:
                    self.current_category = _("None")
                    self.button_category.set_label(_("All"))

                populate_dialog_list()
                self.flowbox.invalidate_filter()

        btn_add.connect("clicked", on_add)
        btn_edit.connect("clicked", on_edit)
        btn_remove.connect("clicked", on_remove)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def _save_categories(self, categories):
        os.makedirs(os.path.dirname(categories_file), exist_ok=True)
        with open(categories_file, "w", encoding="utf-8") as f:
            for cat in categories:
                f.write(f"{cat}\n")

    def _get_current_categories(self):
        if os.path.exists(categories_file):
            with open(categories_file, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def _update_games_category(self, old_cat, new_cat):
        try:
            data = load_json_file(games_json, [])
            changed = False

            for item in data:
                raw_cat = item.get("category", [])
                if isinstance(raw_cat, str) and raw_cat == old_cat:
                    item["category"] = [new_cat]
                    changed = True
                elif isinstance(raw_cat, list) and old_cat in raw_cat:
                    raw_cat = [new_cat if c == old_cat else c for c in raw_cat]
                    item["category"] = list(dict.fromkeys(raw_cat))
                    changed = True

            if changed:
                save_json_file(data, games_json)
                for flowbox_child in self.flowbox.get_children():
                    if hasattr(flowbox_child, "game"):
                        child_cat = getattr(flowbox_child.game, "category", [])
                        if isinstance(child_cat, str) and child_cat == old_cat:
                            flowbox_child.game.category = [new_cat]
                        elif isinstance(child_cat, list) and old_cat in child_cat:
                            child_cat = [new_cat if c == old_cat else c for c in child_cat]
                            flowbox_child.game.category = list(dict.fromkeys(child_cat))
        except Exception:
            pass

    def _remove_games_category(self, cat_to_remove):
        try:
            data = load_json_file(games_json, [])
            changed = False

            for item in data:
                raw_cat = item.get("category", [])
                if isinstance(raw_cat, str) and raw_cat == cat_to_remove:
                    item.pop("category", None)
                    changed = True
                elif isinstance(raw_cat, list) and cat_to_remove in raw_cat:
                    raw_cat.remove(cat_to_remove)
                    if not raw_cat:
                        item.pop("category", None)
                    else:
                        item["category"] = raw_cat
                    changed = True

            if changed:
                save_json_file(data, games_json)
                for child in self.flowbox.get_children():
                    if hasattr(child, "game"):
                        child_cat = getattr(child.game, "category", [])
                        if isinstance(child_cat, str) and child_cat == cat_to_remove:
                            child.game.category = []
                        elif isinstance(child_cat, list) and cat_to_remove in child_cat:
                            child_cat.remove(cat_to_remove)
                            child.game.category = child_cat
        except Exception:
            pass

    def show_power_menu(self, widget):
        dialog = Gtk.Dialog(title="Faugus Launcher", parent=self)
        dialog.set_modal(True)
        dialog.set_resizable(False)
        dialog.set_default_size(300, -1)

        content = dialog.get_content_area()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        shutdown_btn = Gtk.Button(label=_("Shut down"))
        shutdown_btn.connect("clicked", lambda w: (self.on_shutdown(w), dialog.destroy()))

        reboot_btn = Gtk.Button(label=_("Reboot"))
        reboot_btn.connect("clicked", lambda w: (self.on_reboot(w), dialog.destroy()))

        close_btn = Gtk.Button(label=_("Close"))
        close_btn.connect("clicked", lambda w: (self.on_close_fullscreen(w), dialog.destroy()))

        box.pack_start(shutdown_btn, True, True, 0)
        box.pack_start(reboot_btn, True, True, 0)
        box.pack_start(close_btn, True, True, 0)

        content.add(box)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_shutdown(self, widget):
        subprocess.run(["pkexec", "shutdown", "-h", "now"])

    def on_reboot(self, widget):
        subprocess.run(["pkexec", "reboot"])

    def on_close_fullscreen(self, widget):
        self.get_application().quit()

    def on_item_right_click(self, widget, event):
        if event is None or event.button == Gdk.BUTTON_SECONDARY:
            item = self.get_item_at_event(event) if event else self.flowbox.get_selected_children()[0]

            if item:
                self.flowbox.emit('child-activated', item)
                self.flowbox.select_child(item)

                game = self.selected()
                title = game.title

                self.menu_title.get_child().set_text(title)

                data = load_json_file(games_json, [])

                for item_data in data:
                    if isinstance(item_data, dict) and item_data.get("gameid") == game.gameid:
                        game.playtime = item_data.get("playtime", 0)
                        formatted = self.format_playtime(game.playtime)
                        children = self.context_menu.get_children()

                        if self.menu_playtime in children:
                            self.context_menu.remove(self.menu_playtime)
                        if formatted:
                            self.context_menu.insert(self.menu_playtime, 1)
                            self.menu_playtime.get_child().set_text(formatted)

                        break

                self.proton_log = f"{logs_dir}/{game.gameid}/proton.log"
                self.umu_log = f"{logs_dir}/{game.gameid}/umu.log"

                if os.path.exists(self.proton_log):
                    self.menu_show_logs.set_sensitive(True)
                    self.current_title = title
                else:
                    self.menu_show_logs.set_sensitive(False)

                if game.hidden:
                    self.menu_hide.get_child().set_text(_("Remove from hidden"))
                else:
                    self.menu_hide.get_child().set_text(_("Hide"))

                for child in self.submenu_category.get_children():
                    self.submenu_category.remove(child)

                categories = []

                if os.path.exists(categories_file):
                    with open(categories_file, "r", encoding="utf-8") as f:
                        categories = sorted(
                            [line.strip() for line in f if line.strip()],
                            key=str.lower
                        )

                categories.insert(0, _("None"))

                raw_cat = getattr(game, 'category', [])
                if isinstance(raw_cat, str):
                    current_cats = [raw_cat]
                elif isinstance(raw_cat, list):
                    current_cats = raw_cat
                else:
                    current_cats = []

                if not current_cats:
                    current_cats = [_("None")]

                for cat in categories:
                    label_text = f"✓ {cat}" if cat in current_cats else f"   {cat}"

                    menu_item = Gtk.MenuItem(label=label_text)
                    menu_item.connect("activate", self.on_context_menu_category, cat, game.gameid)
                    self.submenu_category.append(menu_item)

                self.context_menu.show_all()

                if game.runner == "Steam":
                    self.menu_duplicate.set_visible(False)
                    self.menu_game_location.set_visible(False)
                    self.menu_prefix_location.set_visible(False)
                    self.menu_run.set_visible(False)
                    self.menu_show_logs.set_visible(False)
                elif game.runner == "Linux-Native":
                    self.menu_duplicate.set_visible(True)
                    self.menu_game_location.set_visible(True)
                    self.menu_prefix_location.set_visible(False)
                    self.menu_run.set_visible(False)
                    self.menu_show_logs.set_visible(False)
                else:
                    self.menu_duplicate.set_visible(True)
                    self.menu_game_location.set_visible(True)
                    self.menu_prefix_location.set_visible(True)
                    self.menu_run.set_visible(True)

                if os.path.dirname(game.path):
                    self.menu_game_location.set_sensitive(True)
                    self.current_game = os.path.dirname(game.path)
                else:
                    self.menu_game_location.set_sensitive(False)
                    self.current_game = None

                if os.path.isdir(game.prefix):
                    self.menu_prefix_location.set_sensitive(True)
                    self.current_prefix = game.prefix
                else:
                    self.menu_prefix_location.set_sensitive(False)
                    self.current_prefix = None

                if event:
                    self.context_menu.popup_at_pointer(event)
                else:
                    self.context_menu.popup_at_widget(
                        widget,
                        Gdk.Gravity.CENTER,
                        Gdk.Gravity.NORTH,
                        None
                    )

    def format_playtime(self, seconds):
        if not seconds:
            return None

        try:
            seconds = int(seconds)
        except (ValueError, TypeError):
            seconds = 0

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60

        if hours == 0 and minutes == 0:
            return None

        txt_hour   = _("hour")
        txt_hours  = _("hours")
        txt_minute = _("minute")
        txt_minutes = _("minutes")

        parts = []

        if hours > 0:
            word = txt_hour if hours == 1 else txt_hours
            parts.append(f"{hours} {word}")

        if minutes > 0:
            word = txt_minute if minutes == 1 else txt_minutes
            parts.append(f"{minutes} {word}")

        return " ".join(parts)

    def on_context_menu_play(self, menu_item):
        game = self.selected()
        if game:
            self.on_button_play_clicked(None, game)

    def on_context_menu_edit(self, menu_item):
        game = self.selected()
        if game:
            self.on_button_edit_clicked(game)

    def on_context_menu_delete(self, menu_item):
        game = self.selected()
        if game:
            self.on_button_delete_clicked(game)

    def on_context_menu_duplicate(self, menu_item):
        game = self.selected()
        if game:
            self.on_duplicate_clicked()

    def on_context_menu_hide(self, menu_item):
        game = self.selected()
        if not game:
            return

        try:
            data = load_json_file(games_json, [])

            for item in data:
                if item.get("gameid") == game.gameid:
                    item["hidden"] = not item.get("hidden", False)
                    game.hidden = item["hidden"]
                    break

            save_json_file(data, games_json)

        except Exception:
            return

        self.update_list()
        self.select_first_child()

    def on_context_menu_category(self, menu_item, category_name, selected_gameid):
        try:
            data = load_json_file(games_json, [])

            for item in data:
                if item.get("gameid") == selected_gameid:
                    raw_cat = item.get("category", [])
                    if isinstance(raw_cat, str):
                        current_cats = [raw_cat]
                    elif isinstance(raw_cat, list):
                        current_cats = raw_cat.copy()
                    else:
                        current_cats = []

                    if category_name == _("None"):
                        current_cats = []
                    else:
                        if category_name in current_cats:
                            current_cats.remove(category_name)
                        else:
                            current_cats.append(category_name)

                    if not current_cats:
                        item.pop("category", None)
                    else:
                        item["category"] = current_cats

                    for child in self.flowbox.get_children():
                        if hasattr(child, "game") and child.game.gameid == selected_gameid:
                            child.game.category = current_cats if current_cats else None
                            break
                    break

            save_json_file(data, games_json)

        except Exception:
            return

        self.flowbox.invalidate_filter()

        for child in self.flowbox.get_children():
            if hasattr(child, "game") and child.game.gameid == selected_gameid:
                self.flowbox.select_child(child)
                self.flowbox.set_focus_child(child)
                break

    def on_context_menu_game_location(self, menu_item):
        subprocess.run(["xdg-open", self.current_game], check=True)

    def on_context_menu_prefix_location(self, menu_item):
        subprocess.run(["xdg-open", self.current_prefix], check=True)

    def on_context_menu_run(self, menu_item):
        game = self.selected()
        if not game:
            return
        filechooser = Gtk.FileChooserNative(
            title=_("Select a file to run inside the prefix"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        add_windows_file_filters(filechooser)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            prefix = game.prefix
            runner = game.runner
            title_formatted = format_title(game.title)
            file_run = filechooser.get_filename()
            game_directory = os.path.dirname(game.path)
            cwd = game_directory if game_directory and os.path.isdir(game_directory) else None
            escaped_file_run = file_run.replace("'", "'\\''")
            command_parts = []

            command_parts.append(f"FAUGUS_DISABLE_UPDATES=1")
            if title_formatted:
                command_parts.append(f"LOG_DIR={title_formatted}")
            if prefix:
                command_parts.append(f"WINEPREFIX='{prefix}'")
            if runner:
                if runner == "Proton-CachyOS (System)":
                    command_parts.append(f"PROTONPATH='{proton_cachyos}'")
                else:
                    command_parts.append(f"PROTONPATH='{runner}'")
            if escaped_file_run.endswith(".reg"):
                command_parts.append(f"'{umu_run}' regedit '{escaped_file_run}'")
            else:
                command_parts.append(f"'{umu_run}' '{escaped_file_run}'")

            command = ' '.join(command_parts)
            cmd = (sys.executable, "-m", "faugus.runner", command)
            subprocess.Popen(cmd, cwd=cwd if cwd else None)

        filechooser.destroy()

    def on_context_show_logs(self, menu_item):
        game = self.selected()
        if game:
            self.on_show_logs_clicked()

    def on_show_logs_clicked(self):
        dialog = Gtk.Dialog(title=_("%s Logs") % self.current_title, parent=self)
        dialog.set_modal(True)
        dialog.set_default_size(1280, 720)

        scrolled_window1 = Gtk.ScrolledWindow()
        scrolled_window1.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_view1 = Gtk.TextView()
        text_view1.set_editable(False)
        text_buffer1 = text_view1.get_buffer()
        with open(self.proton_log, "r") as log_file:
            text_buffer1.set_text(log_file.read())
        scrolled_window1.add(text_view1)

        scrolled_window2 = Gtk.ScrolledWindow()
        scrolled_window2.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_view2 = Gtk.TextView()
        text_view2.set_editable(False)
        text_buffer2 = text_view2.get_buffer()
        with open(self.umu_log, "r") as log_file:
            text_buffer2.set_text(log_file.read())
        scrolled_window2.add(text_view2)

        def copy_to_clipboard(button):
            current_page = notebook.get_current_page()
            if current_page == 0:  # Tab 1: Proton
                start_iter, end_iter = text_buffer1.get_bounds()
                text_to_copy = text_buffer1.get_text(start_iter, end_iter, False)
            elif current_page == 1:  # Tab 2: UMU-Launcher
                start_iter, end_iter = text_buffer2.get_bounds()
                text_to_copy = text_buffer2.get_text(start_iter, end_iter, False)
            else:
                text_to_copy = ""

            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text_to_copy, -1)
            clipboard.store()

        def open_location(button):
            subprocess.run(["xdg-open", os.path.dirname(self.proton_log)], check=True)

        button_copy_clipboard = Gtk.Button(label=_("Copy to clipboard"))
        button_copy_clipboard.set_size_request(150, -1)
        button_copy_clipboard.connect("clicked", copy_to_clipboard)

        button_open_location = Gtk.Button(label=_("Open file location"))
        button_open_location.set_size_request(150, -1)
        button_open_location.connect("clicked", open_location)

        notebook = Gtk.Notebook()
        notebook.set_margin_start(10)
        notebook.set_margin_end(10)
        notebook.set_margin_top(10)
        notebook.set_margin_bottom(10)
        notebook.set_halign(Gtk.Align.FILL)
        notebook.set_valign(Gtk.Align.FILL)
        notebook.set_vexpand(True)
        notebook.set_hexpand(True)

        tab_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label1 = Gtk.Label(label="Proton")
        tab_label1.set_width_chars(15)
        tab_label1.set_xalign(0.5)
        tab_box1.pack_start(tab_label1, True, True, 0)
        tab_box1.set_hexpand(True)

        tab_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label2 = Gtk.Label(label="UMU-Launcher")
        tab_label2.set_width_chars(15)
        tab_label2.set_xalign(0.5)
        tab_box2.pack_start(tab_label2, True, True, 0)
        tab_box2.set_hexpand(True)

        notebook.append_page(scrolled_window1, tab_box1)
        notebook.append_page(scrolled_window2, tab_box2)

        content_area = dialog.get_content_area()
        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        box_bottom.pack_start(button_copy_clipboard, True, True, 0)
        box_bottom.pack_start(button_open_location, True, True, 0)

        content_area.add(notebook)
        content_area.add(box_bottom)

        tab_box1.show_all()
        tab_box2.show_all()

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_duplicate_clicked(self):
        game = self.selected()
        title = game.title

        load_red_entry_css()

        self._dup_game = game
        self._dup_dialog = DuplicateDialog(self, title)
        self._dup_dialog.connect("response", self._on_confirm_duplicate_response)

    def _on_confirm_duplicate_response(self, dialog, response):
        game = self._dup_game

        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        new_title = dialog.entry_title.get_text().strip()
        gameid = format_title(new_title)

        if not new_title:
            dialog.entry_title.get_style_context().add_class("entry")
            return

        if not gameid:
            dialog.entry_title.get_style_context().add_class("entry")
            return

        if any(new_title.casefold() == g.title.casefold() for g in self.games):
            self.show_warning_dialog_main(
                dialog,
                _("%s already exists.") % new_title,
                ""
            )
            return

        title_formatted = format_title(new_title)

        icon = game.icon
        new_icon = f"{icons_dir}/{title_formatted}.ico"
        if os.path.exists(icon):
            shutil.copyfile(icon, new_icon)

        banner = game.banner
        new_banner = f"{banners_dir}/{title_formatted}.png"
        if os.path.exists(banner):
            shutil.copyfile(banner, new_banner)

        new_addapp_bat = f"{os.path.dirname(game.path)}/faugus-{title_formatted}.bat"
        if os.path.exists(game.addapp_bat):
            shutil.copyfile(game.addapp_bat, new_addapp_bat)

        game.title = new_title
        game.banner = new_banner
        game.addapp_bat = new_addapp_bat

        game_info = game_to_dict(game)
        game_info["gameid"] = title_formatted

        games = load_json_file(games_json, [])

        games.append(game_info)

        save_json_file(games, games_json)

        self.games.append(game)
        self.add_item_list(game)
        self.update_list()
        self.select_game_by_title(new_title)

        dialog.destroy()

    def on_item_release_event(self, widget, event):
        if event.button == Gdk.BUTTON_PRIMARY:
            current_time = event.time
            current_item = self.get_item_at_event(event)

            if current_item:
                self.flowbox.select_child(current_item)
                if current_item == self.last_clicked_item and current_time - self.last_click_time < self.double_click_time_threshold:
                    self.on_item_double_click(current_item)

            self.last_clicked_item = current_item
            self.last_click_time = current_time

    def get_item_at_event(self, event):
        widget = Gtk.get_event_widget(event)

        while widget:
            if isinstance(widget, Gtk.FlowBoxChild):
                return widget
            if isinstance(widget, Gtk.FlowBox):
                break
            widget = widget.get_parent()

        return None

    def on_item_double_click(self, item):
        game = self.selected()
        gameid = game.gameid
        title = game.title

        if gameid in self.running:
            self.running_dialog(title)
        else:
            self.on_button_play_clicked()

    def on_key_press_event(self, widget, event):
        if event.keyval == Gdk.KEY_h and event.state & Gdk.ModifierType.CONTROL_MASK:
            try:
                with open(config_file_dir, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                found = False

                for line in lines:
                    stripped = line.strip()
                    if stripped.lower().startswith("show-hidden"):
                        sep_index = line.find("=")
                        if sep_index != -1:
                            left = line[:sep_index]
                            right = line[sep_index + 1:].strip()
                            new_value = "False" if right.lower() == "true" else "True"
                            new_lines.append(f"{left}={new_value}\n")
                            found = True
                        else:
                            new_lines.append(line)
                    else:
                        new_lines.append(line)

                if not found:
                    new_lines.append("show-hidden=True\n")

                with open(config_file_dir, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

                self.load_config()
                self.update_list()
                self.select_first_child()
                return True
            except Exception:
                return False

        if event.keyval == Gdk.KEY_Return and event.state & Gdk.ModifierType.MOD1_MASK:
            if self.interface_mode != "List":
                if self.get_window().get_state() & Gdk.WindowState.FULLSCREEN:
                    self.fullscreen_activated = False
                    self.unfullscreen()
                else:
                    self.fullscreen_activated = True
                    self.fullscreen()
                return True

        if event.keyval == Gdk.KEY_Escape and getattr(self, 'fullscreen_activated', False):
            self.show_power_menu(widget)
            return True

        game = self.selected()
        if not game:
            return

        gameid = game.gameid
        title = game.title

        child = self.flowbox.get_selected_children()[0]
        current_focus = self.get_focus()

        if not child.is_focus():
            return

        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right):
            if current_focus not in self.flowbox.get_children():
                child.grab_focus()

        if event.keyval == Gdk.KEY_Return:
            if gameid in self.running:
                self.running_dialog(title)
            else:
                self.on_button_play_clicked()

        if event.keyval == Gdk.KEY_Delete:
            self.on_button_delete_clicked()

        return False

    def running_dialog(self, title):
        dialog = Gtk.Dialog(title="Faugus Launcher", parent=self)
        dialog.set_modal(True)
        dialog.set_resizable(False)
        play_notification_sound()

        label = Gtk.Label()
        label.set_label(_("%s is already running.") % title)
        label.set_halign(Gtk.Align.CENTER)

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.OK))

        content_area = dialog.get_content_area()
        content_area.set_border_width(0)
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.pack_start(label, True, True, 0)
        box_bottom.pack_start(button_ok, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def load_config(self):
        cfg = ConfigManager()

        self.system_tray = cfg.config.get('system-tray', 'False') == 'True'
        self.mono_icon = cfg.config.get('mono-icon', 'False') == 'True'
        self.close_on_launch = cfg.config.get('close-onlaunch', 'False') == 'True'
        self.interface_mode = cfg.config.get('interface-mode', '').strip('"')
        self.show_labels = cfg.config.get('show-labels', 'False') == 'True'
        self.enable_logging = cfg.config.get('enable-logging', 'False') == 'True'
        self.gamepad_navigation = cfg.config.get('gamepad-navigation', 'False') == 'True'
        self.language = cfg.config.get('language', '')
        self.show_hidden = cfg.config.get('show-hidden', 'False') == 'True'
        self.show_categories = cfg.config.get('show-categories', 'False') == 'True'
        self.window_behavior = cfg.config.get('window-behavior', '')
        self.window_width = int(cfg.config.get('width', 1280))
        self.window_height = int(cfg.config.get('height', 720))
        self.banner_size = int(cfg.config.get('banner-size', 100))
        self.sort = cfg.config.get('sort', '')
        self.category = cfg.config.get('category', '')

        if self.enable_logging:
            if self.menu_show_logs not in self.context_menu.get_children():
                self.context_menu.append(self.menu_show_logs)
        else:
            if self.menu_show_logs in self.context_menu.get_children():
                self.context_menu.remove(self.menu_show_logs)

    def load_games(self):
        games_data = load_json_file(games_json, [])

        self.games.clear()
        for game_data in games_data:
            game = Game(**prepare_game_kwargs(game_data))

            if not self.show_hidden and game.hidden:
                continue

            self.games.append(game)

        self.games = sorted(self.games, key=lambda x: x.title.lower())

        self.flowbox.foreach(Gtk.Widget.destroy)
        for game in self.games:
            self.add_item_list(game)

    def add_item_list(self, game):
        zoom_pct = self.banner_size

        if self.interface_mode == "List":
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        if self.interface_mode == "Blocks":
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            hbox.set_size_request(200, -1)
        if self.interface_mode == "Banners":
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        hbox.get_style_context().add_class("game")

        game_icon = game.icon
        if not os.path.isfile(game_icon):
            game_icon = faugus_png

        game_label = Gtk.Label.new(game.title)

        if self.interface_mode in ("Blocks", "Banners"):
            game_label.set_line_wrap(True)
            game_label.set_lines(2)
            game_label.set_ellipsize(Pango.EllipsizeMode.END)
            game_label.set_max_width_chars(1)
            game_label.set_justify(Gtk.Justification.CENTER)

        self.flowbox_child = Gtk.FlowBoxChild()
        self.flowbox_child.game = game
        self.flowbox_child.label = game_label
        self.flowbox_child.hbox = hbox

        anim_box = Gtk.Box()
        anim_box.get_style_context().add_class("launch-overlay")
        anim_box.set_hexpand(True)
        anim_box.set_vexpand(True)
        self.flowbox_child.anim_box = anim_box

        if self.interface_mode == "List":
            surface = self.get_game_artwork(game_icon, game, 40, 40)
            image = Gtk.Image.new_from_surface(surface)

            self.flowbox_child.image = image

            image.set_margin_start(10)
            image.set_margin_end(10)
            image.set_margin_top(10)
            image.set_margin_bottom(10)

            game_label.set_margin_start(10)
            game_label.set_margin_end(10)
            game_label.set_margin_top(10)
            game_label.set_margin_bottom(10)

            hbox.pack_start(image, False, False, 0)
            hbox.pack_start(game_label, False, False, 0)

            self.flowbox_child.set_size_request(300, -1)
            self.flowbox.set_homogeneous(True)
            self.flowbox_child.set_valign(Gtk.Align.START)
            self.flowbox_child.set_halign(Gtk.Align.FILL)

        if self.interface_mode == "Blocks":
            self.flowbox_child.set_hexpand(True)
            self.flowbox_child.set_vexpand(True)

            block_size = 100

            surface = self.get_game_artwork(game_icon, game, block_size, block_size)
            image = Gtk.Image.new_from_surface(surface)

            self.flowbox_child.image = image

            image.set_margin_top(10)
            game_label.set_margin_top(10)
            game_label.set_margin_start(10)
            game_label.set_margin_end(10)
            game_label.set_margin_bottom(10)

            hbox.pack_start(image, False, False, 0)
            hbox.pack_start(game_label, True, False, 0)

            self.flowbox_child.set_valign(Gtk.Align.FILL)
            self.flowbox_child.set_halign(Gtk.Align.FILL)

        if self.interface_mode == "Banners":
            self.flowbox_child.set_hexpand(True)
            self.flowbox_child.set_vexpand(True)

            image2 = Gtk.Image()
            self.flowbox_child.banner = image2

            game_label.set_size_request(-1, 50)
            game_label.set_margin_start(10)
            game_label.set_margin_end(10)

            self.flowbox_child.set_margin_start(10)
            self.flowbox_child.set_margin_end(10)
            self.flowbox_child.set_margin_top(10)
            self.flowbox_child.set_margin_bottom(10)

            self.flowbox_child.set_valign(Gtk.Align.FILL)
            self.flowbox_child.set_halign(Gtk.Align.FILL)

            banner_path = game.banner
            if not os.path.isfile(game.banner):
                banner_path = faugus_banner

            zoom_width = int(230 * (zoom_pct / 100.0))
            zoom_height = int(zoom_width * 1.5)

            surface = self.get_game_artwork(banner_path, game, zoom_width, zoom_height)

            image2.set_from_surface(surface)

            hbox.pack_start(image2, False, False, 0)

            self.flowbox_child.get_style_context().add_class("banner-container")

            if not self.show_labels:
                game_label.set_no_show_all(True)

            hbox.pack_start(game_label, True, False, 0)

        overlay = Gtk.Overlay()
        overlay.add(hbox)
        overlay.add_overlay(anim_box)
        try:
            overlay.set_overlay_pass_through(anim_box, True)
        except AttributeError:
            pass
        self.flowbox_child.add(overlay)

        self.flowbox.add(self.flowbox_child)

    def update_game_visual(self, flowbox_child):
        game = flowbox_child.game

        if hasattr(flowbox_child, "image"):
            game_icon = game.icon
            if not os.path.isfile(game_icon):
                game_icon = faugus_png

            if self.interface_mode == "List":
                surface = self.get_game_artwork(game_icon, game, 40, 40)
            else:
                surface = self.get_game_artwork(game_icon, game, 100, 100)

            flowbox_child.image.set_from_surface(surface)

        if hasattr(flowbox_child, "banner"):
            banner_path = game.banner
            if not os.path.isfile(game.banner):
                banner_path = faugus_banner

            zoom_pct = getattr(self, "banner_size", 100)
            zoom_width = int(230 * (zoom_pct / 100.0))
            zoom_height = int(zoom_width * 1.5)

            surface = self.get_game_artwork(banner_path, game, zoom_width, zoom_height)

            flowbox_child.banner.set_from_surface(surface)

    def get_game_artwork(self, path, game, width=None, height=None):
        scale = self.get_scale_factor()
        w = int(width * scale) if width else None
        h = int(height * scale) if height else None

        pixbuf = safe_load_pixbuf(path, w, h, False)

        if not self.is_game_installed(game):
            pixbuf.saturate_and_pixelate(pixbuf, 0.0, False)

        surface = Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, None)
        return surface

    def is_game_installed(self, game):
        if game.runner == "Steam":
            for appid, name in read_installed_games():
                if hasattr(game, "appid") and str(game.appid) == str(appid):
                    return True
                if game.title.lower() == name.lower():
                    return True
            return False

        return os.path.exists(game.path)

    def on_search_changed(self, entry):
        self.flowbox.invalidate_filter()

        for child in self.flowbox.get_children():
            if child.get_visible():
                self.flowbox.select_child(child)
                break

    def on_button_settings_clicked(self, widget):
        # Handle add button click event
        settings_dialog = Settings(self)
        settings_dialog.connect("response", self.on_settings_dialog_response, settings_dialog)

        settings_dialog.show()

    def on_settings_dialog_response(self, dialog, response_id, settings_dialog):
        if faugus_backup:
            os.execv(sys.executable, [sys.executable] + sys.argv)

        if response_id == Gtk.ResponseType.OK:
            default_prefix = settings_dialog.entry_default_prefix.get_text()
            validation_result = self.validate_settings_fields(settings_dialog, default_prefix)
            if not validation_result:
                return

            if not settings_dialog.logging_warning:
                if settings_dialog.checkbox_enable_logging.get_active():
                    self.show_warning_dialog_main(
                        self,
                        _("Proton may generate huge log files."),
                        _("Enable logging only when debugging a problem.")
                    )
                    settings_dialog.logging_warning = True

            self.save_interface_settings()
            settings_dialog.update_config_file()
            self.manage_autostart_file(settings_dialog.checkbox_start_boot.get_active(), settings_dialog.checkbox_start_minimized.get_active())

            self.system_tray = settings_dialog.checkbox_system_tray.get_active()

            GLib.timeout_add(1000, self.load_tray_icon)

            combobox_language = settings_dialog.combobox_language.get_active_text()

            if self.interface_mode != settings_dialog.combobox_interface.get_active_id():
                os.execv(sys.executable, [sys.executable] + sys.argv)

            if self.show_labels != settings_dialog.checkbox_show_labels.get_active():
                os.execv(sys.executable, [sys.executable] + sys.argv)

            if self.language != settings_dialog.lang_codes.get(combobox_language, "en_US"):
                os.execv(sys.executable, [sys.executable] + sys.argv)

            if self.gamepad_navigation != settings_dialog.checkbox_gamepad_navigation.get_active():
                os.execv(sys.executable, [sys.executable] + sys.argv)

            if self.show_categories != settings_dialog.checkbox_show_categories.get_active():
                os.execv(sys.executable, [sys.executable] + sys.argv)

            settings_dialog.update_envar_file()

            if self.show_hidden != settings_dialog.checkbox_show_hidden.get_active():
                self.load_config()
                self.update_list()

            self.load_config()
            settings_dialog.destroy()

        else:
            settings_dialog.destroy()

    def validate_settings_fields(self, settings_dialog, default_prefix):
        settings_dialog.entry_default_prefix.get_style_context().remove_class("entry")

        if not default_prefix:
            settings_dialog.entry_default_prefix.get_style_context().add_class("entry")
            return False

        return True

    def manage_autostart_file(self, start_boot, start_minimized):
        autostart_path = PathManager.user_home('.config/autostart/faugus-launcher.desktop')
        autostart_dir = os.path.dirname(autostart_path)

        if not os.path.exists(autostart_dir):
            os.makedirs(autostart_dir)

        if start_boot:
            hide_arg = " --hide" if start_minimized else ""

            with open(autostart_path, "w") as f:
                if IS_FLATPAK:
                    f.write(
                        "[Desktop Entry]\n"
                        "Type=Application\n"
                        "Name=Faugus Launcher\n"
                        f"Exec=flatpak run io.github.Faugus.faugus-launcher{hide_arg}\n"
                        "Icon=io.github.Faugus.faugus-launcher\n"
                        "Categories=Game;\n"
                        "StartupWMClass=faugus-launcher\n"
                    )
                else:
                    f.write(
                        "[Desktop Entry]\n"
                        "Type=Application\n"
                        "Name=Faugus Launcher\n"
                        f"Exec=faugus-launcher{hide_arg}\n"
                        "Icon=faugus-launcher\n"
                        "Categories=Game;\n"
                        "StartupWMClass=faugus-launcher\n"
                    )
        else:
            if os.path.exists(autostart_path):
                os.remove(autostart_path)

    def on_button_play_clicked(self, widget=None, game=None):
        self.button_play.set_sensitive(False)
        def reenable():
            if not IS_FLATPAK:
                self.button_play.set_sensitive(True)
            return False
        GLib.timeout_add(1000, reenable)

        if game is None:
            game = self.selected()

        if not game:
            return

        selected = self.flowbox.get_selected_children()
        if selected:
            child = selected[0]
            self.update_game_visual(child)

            if hasattr(child, 'anim_box') and child.anim_box:
                child.anim_box.get_style_context().add_class("playing")

                def remove_anim():
                    child.anim_box.get_style_context().remove_class("playing")
                    return False
                GLib.timeout_add(150, remove_anim)

        gameid = game.gameid
        title = game.title
        game_directory = os.path.dirname(game.path)
        cwd = game_directory if game_directory and os.path.isdir(game_directory) else None

        def update_latest_and_sort():
            self.update_latest_games_file(game.gameid)
            if hasattr(self, 'current_sort') and self.current_sort == self.opt_lastplayed:
                self.latest_games_order.clear()
                try:
                    if os.path.exists(latest_games):
                        with open(latest_games) as f:
                            for idx, gid in enumerate(map(str.strip, f)):
                                self.latest_games_order[gid] = idx
                except:
                    pass
                if hasattr(self, 'flowbox'):
                    self.flowbox.invalidate_sort()

        if game.runner == "Steam":
            update_latest_and_sort()
            subprocess.Popen(
                [sys.executable, "-m", "faugus.runner", "--game", gameid],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True
            )
            return

        if gameid in self.running:
            try:
                os.kill(self.running[gameid], signal.SIGUSR1)
            except ProcessLookupError:
                pass

            self.running.pop(gameid, None)
            self.processes.pop(gameid, None)
            self.save_running()
            self.update_icon()
            return

        update_latest_and_sort()
        cmd = (sys.executable, "-m", "faugus.runner", "--game", gameid)
        proc = subprocess.Popen(cmd, cwd=cwd if cwd else None)

        if not IS_FLATPAK or not self.close_on_launch:
            self.running[gameid] = proc.pid
            self.processes[gameid] = proc
            GLib.child_watch_add(proc.pid, self.on_exit, gameid)
            self.save_running()

        if self.close_on_launch:
            sys.exit()

        self.update_icon()

        return False

    def on_exit(self, pid, status, game):
        self.running.pop(game, None)
        self.processes.pop(game, None)
        self.save_running()

        if hasattr(self, 'current_sort') and hasattr(self, 'opt_playtime') and self.current_sort == self.opt_playtime:
            try:
                data = load_json_file(games_json, [])
                for item in data:
                    if isinstance(item, dict) and "gameid" in item:
                        self.playtime_data[item["gameid"]] = item.get("playtime", 0)
            except:
                pass

            if hasattr(self, 'flowbox'):
                GLib.idle_add(self.flowbox.invalidate_sort)

        GLib.idle_add(self.update_icon)

    def update_latest_games_file(self, gameid):
        try:
            with open(latest_games) as f:
                games = f.read().splitlines()
        except FileNotFoundError:
            games = []

        valid_ids = {g.gameid for g in self.games}

        games = [g for g in games if g in valid_ids and g != gameid]
        games.insert(0, gameid)

        with open(latest_games, 'w') as f:
            f.write('\n'.join(games))

        self.load_tray_icon()

    def on_button_kill_clicked(self, widget):
        if not IS_FLATPAK:
            for gameid, pid in list(self.running.items()):
                try:
                    os.kill(pid, signal.SIGUSR1)
                except ProcessLookupError:
                    pass

            self.running.clear()
            self.processes.clear()
            self.save_running()
            self.update_icon()

        subprocess.run(r"""
    for pid in $(ls -l /proc/*/exe 2>/dev/null | grep -E 'wine(64)?-preloader|wineserver|winedevice.exe' | awk -F'/' '{print $3}'); do
        kill -9 "$pid"
    done
""", shell=True)

    def on_button_add_clicked(self, widget):
        # Handle add button click event
        add_game_dialog = AddGame(self, self.interface_mode)
        add_game_dialog.combobox_steam_title.connect("changed", add_game_dialog.on_combobox_steam_changed)
        add_game_dialog.connect("response", self.on_dialog_response, add_game_dialog)

        add_game_dialog.show()

    def on_button_edit_clicked(self, widget):
        game = self.selected()
        gameid = game.gameid
        title = game.title

        if game:
            edit_game_dialog = AddGame(self, self.interface_mode)
            edit_game_dialog.connect("response", self.on_edit_dialog_response, edit_game_dialog, game)

            model_steam_title = edit_game_dialog.combobox_steam_title.get_model()
            for i, row in enumerate(model_steam_title):
                if row[0] == title:
                    edit_game_dialog.combobox_steam_title.set_active(i)
                    break

            game_runner = convert_runner(game.runner)

            if game_runner == "Linux-Native":
                edit_game_dialog.combobox_launcher.set_active_id("linux")
            if game_runner == "Steam":
                edit_game_dialog.combobox_launcher.set_active_id("steam")

            model_runner = edit_game_dialog.combobox_runner.get_model()
            index_runner = 0

            for i, row in enumerate(model_runner):
                if row[0] == game_runner:
                    index_runner = i
                    break
            if not game_runner:
                index_runner = 1

            edit_game_dialog.combobox_runner.set_active(index_runner)
            edit_game_dialog.entry_title.set_text(game.title)
            edit_game_dialog.entry_path.set_text(game.path)
            edit_game_dialog.entry_prefix.set_text(game.prefix)
            edit_game_dialog.launch_arguments = game.launch_arguments
            edit_game_dialog.entry_game_arguments.set_text(game.game_arguments)
            edit_game_dialog.set_title(_("Edit %s") % game.title)
            edit_game_dialog.entry_protonfix.set_text(game.protonfix)
            edit_game_dialog.grid_launcher.set_visible(False)

            edit_game_dialog.addapp_enabled = game.addapp_checkbox
            edit_game_dialog.addapp = game.addapp
            edit_game_dialog.addapp_delay = game.addapp_delay
            edit_game_dialog.addapp_first = game.addapp_first

            edit_game_dialog.lossless_enabled = game.lossless_enabled
            edit_game_dialog.lossless_multiplier = game.lossless_multiplier
            edit_game_dialog.lossless_flow = game.lossless_flow
            edit_game_dialog.lossless_performance = game.lossless_performance
            edit_game_dialog.lossless_hdr = game.lossless_hdr
            edit_game_dialog.lossless_present = game.lossless_present

            banner_path = game.banner
            if not os.path.isfile(banner_path):
                banner_path = faugus_banner

            shutil.copyfile(banner_path, edit_game_dialog.banner_path_temp)
            surface = self.new_surface_from_image(banner_path, 260, 390, True)
            edit_game_dialog.image_banner.set_from_surface(surface)
            edit_game_dialog.image_banner2.set_from_surface(surface)

            icon_path = game.icon
            if not os.path.isfile(icon_path):
                icon_path = faugus_png

            shutil.copyfile(icon_path, edit_game_dialog.icon_temp)
            surface = self.new_surface_from_image(icon_path, 50, 50)
            image = Gtk.Image.new_from_surface(surface)
            edit_game_dialog.button_shortcut_icon.set_image(image)

            mangohud_enabled = os.path.exists(mangohud_dir)
            if mangohud_enabled:
                if game.mangohud == True:
                    edit_game_dialog.checkbox_mangohud.set_active(True)
                else:
                    edit_game_dialog.checkbox_mangohud.set_active(False)

            gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
            if gamemode_enabled:
                if game.gamemode == True:
                    edit_game_dialog.checkbox_gamemode.set_active(True)
                else:
                    edit_game_dialog.checkbox_gamemode.set_active(False)

            if game.disable_hidraw == True:
                edit_game_dialog.checkbox_disable_hidraw.set_active(True)
            else:
                edit_game_dialog.checkbox_disable_hidraw.set_active(False)

            if game.prevent_sleep == True:
                edit_game_dialog.checkbox_prevent_sleep.set_active(True)
            else:
                edit_game_dialog.checkbox_prevent_sleep.set_active(False)

            if detect_steam_id() is not None:
                if self.check_steam_shortcut(title):
                    edit_game_dialog.checkbox_shortcut_steam.set_active(True)
                else:
                    edit_game_dialog.checkbox_shortcut_steam.set_active(False)
            else:
                edit_game_dialog.checkbox_shortcut_steam.set_active(False)
                edit_game_dialog.checkbox_shortcut_steam.set_sensitive(False)
                edit_game_dialog.checkbox_shortcut_steam.set_tooltip_text(
                    _("Add or remove a shortcut from Steam. Steam needs to be restarted. NO STEAM USERS FOUND."))

            edit_game_dialog.check_existing_shortcut()

            edit_game_dialog.entry_title.set_sensitive(False)
            edit_game_dialog.combobox_steam_title.set_sensitive(False)

            if gameid in self.running:
                edit_game_dialog.button_winetricks.set_sensitive(False)
                edit_game_dialog.button_winetricks.set_tooltip_text(_("%s is running. Please close it first.") % game.title)

    def check_steam_shortcut(self, title):
        if os.path.exists(steam_shortcuts_path):
            try:
                with open(steam_shortcuts_path, 'rb') as f:
                    shortcuts = vdf.binary_load(f)
                for game in shortcuts["shortcuts"].values():
                    if isinstance(game, dict) and "AppName" in game and game["AppName"] == title:
                        return True
                return False
            except SyntaxError:
                return False
        return False

    def on_button_delete_clicked(self, *_):
        self.reload_playtimes()
        game = self.selected()
        gameid = game.gameid
        title = game.title

        if game:
            delete_dialog = DeleteDialog(self, title, game.prefix, game.runner)
            delete_dialog.connect("response", self._on_confirm_delete_response, game)

    def _on_confirm_delete_response(self, dialog, response, game):
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            gameid = game.gameid
            title = game.title

            if gameid in self.running:
                try:
                    os.kill(self.running[gameid], signal.SIGUSR1)
                except ProcessLookupError:
                    pass

                self.running.pop(gameid, None)
                self.processes.pop(gameid, None)
                self.save_running()
                self.update_icon()

            # Remove game and associated files if required
            if dialog.checkbox.get_active():
                prefix_path = os.path.expanduser(game.prefix)

                try:
                    shutil.rmtree(prefix_path)
                except PermissionError as e:
                    try:
                        os.system(f'chmod -R u+rwX "{prefix_path}"')
                        shutil.rmtree(prefix_path)
                    except Exception as e2:
                        self.show_warning_dialog_main(
                            self,
                            _("Failed to remove prefix."),
                            str(e2)
                        )
                except FileNotFoundError:
                    pass

            # Remove the shortcut
            self.remove_shortcut(game, "both")
            self.remove_steam_shortcut(title)
            self.remove_banner_icon(game)

            if os.path.exists(game.addapp_bat):
                os.remove(game.addapp_bat)

            self._deleted_gameid = gameid
            self.save_games()
            self.update_list()

            # Remove the game from the latest-games file if it exists
            self.remove_latest_and_order(gameid)
            self.select_first_child()

    def reload_playtimes(self):
        games_data = load_json_file(games_json, [])
        if not games_data:
            return

        playtime_map = {g["gameid"]: g.get("playtime", 0) for g in games_data}

        for game in self.games:
            if game.gameid in playtime_map:
                game.playtime = playtime_map[game.gameid]

    def remove_steam_shortcut(self, title):
        if os.path.exists(steam_shortcuts_path):
            try:
                with open(steam_shortcuts_path, 'rb') as f:
                    shortcuts = vdf.binary_load(f)

                to_remove = [app_id for app_id, game in shortcuts["shortcuts"].items() if
                             isinstance(game, dict) and "AppName" in game and game["AppName"] == title]
                for app_id in to_remove:
                    del shortcuts["shortcuts"][app_id]

                with open(steam_shortcuts_path, 'wb') as f:
                    vdf.binary_dump(shortcuts, f)
            except SyntaxError:
                pass

    def remove_latest_and_order(self, gameid):
        try:
            with open(latest_games, 'r') as f:
                recent_games = f.read().splitlines()

            if gameid in recent_games:
                recent_games.remove(gameid)

                with open(latest_games, 'w') as f:
                    f.write("\n".join(recent_games))

            self.load_tray_icon()

        except FileNotFoundError:
            pass

        try:
            with open(custom_order, 'r') as f:
                custom_order_data = json.load(f)

            if gameid in custom_order_data:
                del custom_order_data[gameid]

                with open(custom_order, 'w') as f:
                    json.dump(custom_order_data, f)

        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def show_warning_dialog_main(self, parent, text1, text2):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_modal(True)
        dialog.set_resizable(False)
        play_notification_sound()

        label1 = Gtk.Label()
        label1.set_label(text1)
        label1.set_halign(Gtk.Align.CENTER)

        label2 = Gtk.Label()
        label2.set_label(text2)
        label2.set_halign(Gtk.Align.CENTER)

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.YES))

        content_area = dialog.get_content_area()
        content_area.set_border_width(0)
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.pack_start(label1, True, True, 0)
        if text2:
            box_top.pack_start(label2, True, True, 0)
        box_bottom.pack_start(button_ok, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_dialog_response(self, dialog, response_id, add_game_dialog):
        if response_id == Gtk.ResponseType.OK:
            if not add_game_dialog.validate_fields(entry="path+prefix"):
                return True
            launcher_id = add_game_dialog.combobox_launcher.get_active_id()

            prefix = os.path.normpath(add_game_dialog.entry_prefix.get_text())
            if launcher_id in ("windows", "linux", "steam"):
                title = add_game_dialog.entry_title.get_text()
            else:
                title = add_game_dialog.combobox_launcher.get_active_text()

            games = load_json_file(games_json, [])

            if any(game.get("title", "").casefold() == title.casefold() for game in games):
                    self.show_warning_dialog_main(
                        add_game_dialog,
                        _("%s already exists.") % title,
                        ""
                    )
                    return True

            path = add_game_dialog.entry_path.get_text()
            launch_arguments = add_game_dialog.launch_arguments
            game_arguments = add_game_dialog.entry_game_arguments.get_text()
            protonfix = add_game_dialog.entry_protonfix.get_text()
            runner = add_game_dialog.combobox_runner.get_active_text()
            addapp = add_game_dialog.addapp
            addapp_delay = add_game_dialog.addapp_delay
            addapp_first = add_game_dialog.addapp_first
            lossless_enabled = add_game_dialog.lossless_enabled
            lossless_multiplier = add_game_dialog.lossless_multiplier
            lossless_flow = add_game_dialog.lossless_flow
            lossless_performance = add_game_dialog.lossless_performance
            lossless_hdr = add_game_dialog.lossless_hdr
            lossless_present = add_game_dialog.lossless_present
            playtime = 0
            hidden = False
            category = False

            if launcher_id == "battle":
                path = f"{prefix}/drive_c/Program Files (x86)/Battle.net/Battle.net.exe"
            if launcher_id == "ea":
                path = f"{prefix}/drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe"
            if launcher_id == "epic":
                path = f"{prefix}/drive_c/Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"
            if launcher_id == "ubisoft":
                path = f"{prefix}/drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/UbisoftConnect.exe"
            if launcher_id == "rockstar":
                path = f"{prefix}/drive_c/Program Files/Rockstar Games/Launcher/Launcher.exe"
            if launcher_id == "wargaming":
                path = f"{prefix}/drive_c/ProgramData/Wargaming.net/GameCenter/wgc.exe"

            title_formatted = format_title(title)

            addapp_bat = f"{os.path.dirname(path)}/faugus-{title_formatted}.bat"

            if self.interface_mode == "Banners":
                banner = os.path.join(banners_dir, f"{title_formatted}.png")
                temp_banner_path = add_game_dialog.banner_path_temp
                try:
                    command_magick = shutil.which("magick") or shutil.which("convert")
                    subprocess.run([command_magick, temp_banner_path, "-resize", "230x345!", banner], check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error resizing banner: {e}")
            else:
                banner = ""

            icon_temp = os.path.expanduser(add_game_dialog.icon_temp)
            icon_final = f'{add_game_dialog.icons_path}/{title_formatted}.ico'
            icon = icon_final

            runner = convert_runner(runner)
            if launcher_id == "linux":
                runner = "Linux-Native"
            if launcher_id == "steam":
                runner = "Steam"

            if runner == "Steam":
                mangohud = ""
                gamemode = ""
                disable_hidraw = ""
                addapp_checkbox = ""
                prevent_sleep = ""
            else:
                mangohud = True if add_game_dialog.checkbox_mangohud.get_active() else ""
                gamemode = True if add_game_dialog.checkbox_gamemode.get_active() else ""
                disable_hidraw = True if add_game_dialog.checkbox_disable_hidraw.get_active() else ""
                addapp_checkbox = "addapp_enabled" if add_game_dialog.addapp_enabled else ""
                prevent_sleep = True if add_game_dialog.checkbox_prevent_sleep.get_active() else ""

            game = Game(
                title_formatted,
                title,
                path,
                prefix,
                launch_arguments,
                game_arguments,
                mangohud,
                gamemode,
                disable_hidraw,
                protonfix,
                runner,
                addapp_checkbox,
                addapp,
                addapp_bat,
                addapp_delay,
                addapp_first,
                banner,
                lossless_enabled,
                lossless_multiplier,
                lossless_flow,
                lossless_performance,
                lossless_hdr,
                lossless_present,
                playtime,
                hidden,
                prevent_sleep,
                category,
                icon,
            )

            desktop_shortcut_state = add_game_dialog.checkbox_shortcut_desktop.get_active()
            appmenu_shortcut_state = add_game_dialog.checkbox_shortcut_appmenu.get_active()
            steam_shortcut_state = add_game_dialog.checkbox_shortcut_steam.get_active()

            def check_internet_connection():
                import socket
                try:
                    socket.gethostbyname("github.com")
                    return True
                except socket.gaierror:
                    return False

            if launcher_id not in ("windows", "linux", "steam"):
                if not check_internet_connection():
                    self.show_warning_dialog_main(add_game_dialog, _("No internet connection."), "")
                    return True

                if launcher_id in ("battle", "ea", "epic", "ubisoft", "rockstar", "wargaming"):
                    add_game_dialog.destroy()
                    self.launcher_screen(
                        title, launcher_id, title_formatted, runner, prefix, umu_run,
                        game, desktop_shortcut_state, appmenu_shortcut_state,
                        steam_shortcut_state, icon_temp, icon_final
                    )

            game_info = game_to_dict(game)

            games = load_json_file(games_json, [])

            games.append(game_info)

            self.backup_games()

            save_json_file(games, games_json)

            self.games.append(game)

            if launcher_id in ("windows", "linux", "steam"):
                self.add_shortcut(game, desktop_shortcut_state, "desktop", icon_temp, icon_final)
                self.add_shortcut(game, appmenu_shortcut_state, "appmenu", icon_temp, icon_final)
                self.add_steam_shortcut(game, steam_shortcut_state, icon_temp, icon_final)

                if addapp_checkbox == "addapp_enabled":
                    write_addapp_bat(addapp_bat, path, addapp, addapp_delay, addapp_first, game_arguments)

                self.add_item_list(game)
                self.update_list()

                self.select_game_by_title(title)

        else:
            if os.path.isfile(add_game_dialog.icon_temp):
                os.remove(add_game_dialog.icon_temp)
            if os.path.isdir(add_game_dialog.icon_directory):
                shutil.rmtree(add_game_dialog.icon_directory)
            add_game_dialog.destroy()
        if os.path.isfile(add_game_dialog.banner_path_temp):
            os.remove(add_game_dialog.banner_path_temp)
        add_game_dialog.destroy()

    def launcher_screen(self, title, launcher, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final):
        self.box_launcher = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box_launcher.set_hexpand(True)
        self.box_launcher.set_vexpand(True)

        self.bar_download = Gtk.ProgressBar()
        self.bar_download.set_margin_start(20)
        self.bar_download.set_margin_end(20)
        self.bar_download.set_margin_bottom(40)

        grid_launcher = Gtk.Grid()
        grid_launcher.set_halign(Gtk.Align.CENTER)
        grid_launcher.set_valign(Gtk.Align.CENTER)

        grid_labels = Gtk.Grid()
        grid_labels.set_size_request(-1, 128)

        self.box_launcher.pack_start(grid_launcher, True, True, 0)

        self.label_download = Gtk.Label()
        self.label_download.set_margin_start(20)
        self.label_download.set_margin_end(20)
        self.label_download.set_margin_bottom(20)
        self.label_download.set_text(_("Installing %s...") % title)
        self.label_download.set_size_request(256, -1)

        self.label_download2 = Gtk.Label()
        self.label_download2.set_margin_start(20)
        self.label_download2.set_margin_end(20)
        self.label_download2.set_margin_bottom(20)
        self.label_download2.set_text("")
        self.label_download2.set_visible(False)
        self.label_download2.set_size_request(256, -1)

        if launcher == "battle":
            self.label_download.set_text(_("Downloading") + " Battle.net...")
            self.download_launcher("battle", title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final)

        elif launcher == "ea":
            self.label_download.set_text(_("Downloading") + " EA App...")
            self.download_launcher("ea", title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final)

        elif launcher == "epic":
            self.label_download.set_text(_("Downloading") + " Epic Games...")
            self.download_launcher("epic", title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final)

        elif launcher == "ubisoft":
            self.label_download.set_text(_("Downloading") + " Ubisoft Connect...")
            self.download_launcher("ubisoft", title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final)

        elif launcher == "rockstar":
            self.label_download.set_text(_("Downloading") + " Rockstar Launcher...")
            self.download_launcher("rockstar", title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final)

        elif launcher == "wargaming":
            self.label_download.set_text(_("Downloading") + " Wargaming Game Center...")
            self.download_launcher("wargaming", title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final)

        grid_launcher.attach(grid_labels, 0, 1, 1, 1)
        grid_labels.attach(self.label_download, 0, 0, 1, 1)
        grid_labels.attach(self.bar_download, 0, 1, 1, 1)
        grid_labels.attach(self.label_download2, 0, 2, 1, 1)

        if self.interface_mode != "List":
            self.box_main.remove(self.main_hbox)
        else:
            self.box_main.remove(self.box_top)
            self.box_main.remove(self.box_bottom)
        self.box_main.add(self.box_launcher)
        self.box_main.show_all()

    def monitor_process(self, processo, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, title):
        retcode = processo.poll()

        if retcode is not None:
            if os.path.exists(faugus_temp):
                shutil.rmtree(faugus_temp)
            self.box_main.remove(self.box_launcher)
            self.box_launcher.destroy()
            if self.interface_mode != "List":
                self.box_main.add(self.main_hbox)
            else:
                self.box_main.pack_start(self.box_top, True, True, 0)
                self.box_main.pack_end(self.box_bottom, False, True, 0)
            self.box_main.show_all()

            if game.gameid == "ea-app":
                game.path = update_ea_path(game.prefix)

            if os.path.exists(game.path):
                extracted_icon = self.extract_best_icon(game.path, game.gameid)

                if extracted_icon:
                    icon_temp = extracted_icon
                    icon_final = icon_temp
                print(f"{title} installed.")
                self.add_shortcut(game, desktop_shortcut_state, "desktop", icon_temp, icon_final)
                self.add_shortcut(game, appmenu_shortcut_state, "appmenu", icon_temp, icon_final)
                self.add_steam_shortcut(game, steam_shortcut_state, icon_temp, icon_final)
                self.add_item_list(game)
                self.update_list()
                self.select_game_by_title(title)
            else:
                if os.path.exists(game.prefix):
                    shutil.rmtree(game.prefix)
                self.remove_shortcut(game, "both")
                self.remove_steam_shortcut(title)
                self.remove_banner_icon(game)
                self.games.remove(game)
                self.save_games()
                self.update_list()
                self.remove_latest_and_order(game.gameid)
                self.show_warning_dialog_main(self, _("%s was not installed!") % title, "")

            return False

        return True

    def extract_best_icon(self, exe_path, gameid):
        icons_dir = PathManager.user_config('faugus-launcher/icons')
        os.makedirs(icons_dir, exist_ok=True)
        final = os.path.join(icons_dir, f"{gameid}.ico")
        status = extract_ico_frames(exe_path, final)
        return final if status == "ok" else None

    def download_launcher(self, launcher, title, title_formatted, runner, prefix, umu_run, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final):
            urls = {"ea": "https://origin-a.akamaihd.net/EA-Desktop-Client-Download/installer-releases/EAappInstaller.exe",
                "epic": "https://github.com/Faugus/components/releases/download/v1.0.0/epic.msi",
                "battle": "https://downloader.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe",
                "ubisoft": "https://static3.cdn.ubi.com/orbit/launcher_installer/UbisoftConnectInstaller.exe",
                "rockstar": "https://gamedownloads.rockstargames.com/public/installer/Rockstar-Games-Launcher.exe",
                "wargaming": "https://redirect.wargaming.net/WGC/Wargaming_Game_Center_Install_NA.exe"}

            file_name = {"ea": "EAappInstaller.exe", "epic": "EpicGamesLauncherInstaller.msi",
                "battle": "Battle.net-Setup.exe", "ubisoft": "UbisoftConnectInstaller.exe",
                "rockstar": "Rockstar-Games-Launcher.exe", "wargaming": "wargaming_game_center_install_na_dgp3m1ci2u7l.exe"}

            if launcher not in urls:
                return None

            os.makedirs(faugus_temp, exist_ok=True)
            file_path = os.path.join(faugus_temp, file_name[launcher])

            def report_progress(block_num, block_size, total_size):
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(downloaded / total_size, 1.0)
                    GLib.idle_add(self.bar_download.set_fraction, percent)
                    GLib.idle_add(self.bar_download.set_text, f"{int(percent * 100)}%")

            def start_download():
                try:
                    import urllib.request
                    urllib.request.urlretrieve(urls[launcher], file_path, reporthook=report_progress)
                    GLib.idle_add(self.bar_download.set_fraction, 1.0)
                    GLib.idle_add(self.bar_download.set_text, _("Download complete"))
                    GLib.idle_add(on_download_complete)
                except Exception as e:
                    GLib.idle_add(self.show_warning_dialog_main, self, _("Error during download: %s") % e, "")

            def on_download_complete():
                self.label_download.set_text(_("Installing %s...") % title)
                if launcher == "battle":
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 WINE_SIMULATE_WRITECOPY=1 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {umu_run} '{file_path}' --installpath='C:\\Program Files (x86)\\Battle.net' --lang=enUS"
                elif launcher == "ea":
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {umu_run} '{file_path}' /S"
                elif launcher == "epic":
                    self.label_download2.set_text("")
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {umu_run} msiexec /i '{file_path}' /passive"
                elif launcher == "ubisoft":
                    self.label_download2.set_text("")
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {umu_run} '{file_path}' /S"
                elif launcher == "rockstar":
                    self.label_download.set_text(_("Please don't change the installation path."))
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {umu_run} '{file_path}'"
                elif launcher == "wargaming":
                    self.label_download2.set_text(_("Please close Wargaming to finish the installation."))
                    command = f"LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {umu_run} '{file_path}' /SILENT"

                if runner:
                    if runner == "Proton-CachyOS (System)":
                        command = f"PROTONPATH='{proton_cachyos}' {command}"
                    else:
                        command = f"PROTONPATH='{runner}' {command}"

                self.bar_download.set_visible(False)
                self.label_download2.set_visible(True)
                processo = subprocess.Popen([sys.executable, "-m", "faugus.runner", command])
                GLib.timeout_add(100, self.monitor_process, processo, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, title)

            threading.Thread(target=start_download).start()

            return file_path

    def on_edit_dialog_response(self, dialog, response_id, edit_game_dialog, game):
        if response_id == Gtk.ResponseType.OK:
            if not edit_game_dialog.validate_fields(entry="path+prefix"):
                return True
            game.title = edit_game_dialog.entry_title.get_text()
            game.path = edit_game_dialog.entry_path.get_text()
            game.prefix = os.path.normpath(edit_game_dialog.entry_prefix.get_text())
            game.launch_arguments = edit_game_dialog.launch_arguments
            game.game_arguments = edit_game_dialog.entry_game_arguments.get_text()
            game.mangohud = edit_game_dialog.checkbox_mangohud.get_active()
            game.gamemode = edit_game_dialog.checkbox_gamemode.get_active()
            game.disable_hidraw = edit_game_dialog.checkbox_disable_hidraw.get_active()
            game.protonfix = edit_game_dialog.entry_protonfix.get_text()
            game.runner = edit_game_dialog.combobox_runner.get_active_text()
            game.addapp_checkbox = edit_game_dialog.addapp_enabled
            game.addapp = edit_game_dialog.addapp
            game.addapp_delay = edit_game_dialog.addapp_delay
            game.addapp_first = edit_game_dialog.addapp_first
            game.lossless_enabled = edit_game_dialog.lossless_enabled
            game.lossless_multiplier = edit_game_dialog.lossless_multiplier
            game.lossless_flow = edit_game_dialog.lossless_flow
            game.lossless_performance = edit_game_dialog.lossless_performance
            game.lossless_hdr = edit_game_dialog.lossless_hdr
            game.lossless_present = edit_game_dialog.lossless_present
            game.prevent_sleep = edit_game_dialog.checkbox_prevent_sleep.get_active()

            title_formatted = format_title(game.title)

            game.gameid = title_formatted
            game.addapp_bat = f"{os.path.dirname(game.path)}/faugus-{title_formatted}.bat"

            if self.interface_mode == "Banners":
                banner = os.path.join(banners_dir, f"{title_formatted}.png")
                temp_banner_path = edit_game_dialog.banner_path_temp
                try:
                    command_magick = shutil.which("magick") or shutil.which("convert")
                    subprocess.run([command_magick, temp_banner_path, "-resize", "230x345!", banner], check=True)
                    game.banner = banner
                except subprocess.CalledProcessError as e:
                    print(f"Error resizing banner: {e}")

            icon_temp = os.path.expanduser(edit_game_dialog.icon_temp)
            icon_final = f'{edit_game_dialog.icons_path}/{title_formatted}.ico'
            game.icon = icon_final

            game.runner = convert_runner(game.runner)
            if edit_game_dialog.combobox_launcher.get_active_id() == "linux":
                game.runner = "Linux-Native"
            if edit_game_dialog.combobox_launcher.get_active_id() == "steam":
                game.runner = "Steam"

            desktop_shortcut_state = edit_game_dialog.checkbox_shortcut_desktop.get_active()
            appmenu_shortcut_state = edit_game_dialog.checkbox_shortcut_appmenu.get_active()
            steam_shortcut_state = edit_game_dialog.checkbox_shortcut_steam.get_active()

            self.add_shortcut(game, desktop_shortcut_state, "desktop", icon_temp, icon_final)
            self.add_shortcut(game, appmenu_shortcut_state, "appmenu", icon_temp, icon_final)
            self.add_steam_shortcut(game, steam_shortcut_state, icon_temp, icon_final)

            if game.addapp_checkbox == True:
                write_addapp_bat(game.addapp_bat, game.path, game.addapp, game.addapp_delay, game.addapp_first, game.game_arguments)

            self.save_games()
            self.update_list()

            self.select_game_by_title(game.title)
        else:
            if os.path.isfile(edit_game_dialog.icon_temp):
                os.remove(edit_game_dialog.icon_temp)

        if os.path.isdir(edit_game_dialog.icon_directory):
            shutil.rmtree(edit_game_dialog.icon_directory)
        os.remove(edit_game_dialog.banner_path_temp)
        edit_game_dialog.destroy()

    def add_shortcut(self, game, shortcut_state, shortcut, icon_temp, icon_final):
        applications_shortcut_path = f"{app_dir}/{game.gameid}.desktop"
        desktop_shortcut_path = f"{desktop_dir}/{game.gameid}.desktop"

        # Check if the shortcut checkbox is checked
        if shortcut == "desktop" and not shortcut_state:
            # Remove existing shortcut if it exists
            self.remove_shortcut(game, shortcut)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return
        if shortcut == "appmenu" and not shortcut_state:
            # Remove existing shortcut if it exists
            self.remove_shortcut(game, shortcut)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return

        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        # Check if the icon file exists
        new_icon_path = f"{icons_dir}/{game.gameid}.ico"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        # Get the directory containing the executable
        game_directory = os.path.dirname(game.path)

        # Create a .desktop file
        if IS_FLATPAK:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={game.title}\n'
                f'Exec=flatpak run --command={launcher_path} io.github.Faugus.faugus-launcher --game {game.gameid}\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )
        else:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={game.title}\n'
                f'Exec={launcher_path} --game {game.gameid}\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )

        # Check if the destination directory exists and create if it doesn't
        if not os.path.exists(app_dir):
            os.makedirs(app_dir)

        if not os.path.exists(desktop_dir):
            os.makedirs(desktop_dir)

        if shortcut == "appmenu":
            with open(applications_shortcut_path, 'w') as appmenu_file:
                appmenu_file.write(desktop_file_content)
            os.chmod(applications_shortcut_path, 0o755)

        if shortcut == "desktop":
            with open(desktop_shortcut_path, 'w') as desktop_file:
                desktop_file.write(desktop_file_content)
            os.chmod(desktop_shortcut_path, 0o755)

    def add_steam_shortcut(self, game, steam_shortcut_state, icon_temp, icon_final):
        def add_game_to_steam(title, game_directory, icon):
            shortcuts = load_shortcuts(title)

            existing_app_id = None
            for app_id, game_info in shortcuts["shortcuts"].items():
                if isinstance(game_info, dict) and "AppName" in game_info and game_info["AppName"] == title:
                    existing_app_id = app_id
                    break

            if IS_FLATPAK:
                if IS_STEAM_FLATPAK:
                    exe = '"flatpak-spawn"'
                    launch_options = f'--host flatpak run --command=/app/bin/faugus-launcher io.github.Faugus.faugus-launcher --game {game.gameid}'
                else:
                    exe = '"flatpak"'
                    launch_options = f'run --command=/app/bin/faugus-launcher io.github.Faugus.faugus-launcher --game {game.gameid}'
            else:
                if IS_STEAM_FLATPAK:
                    exe = '"flatpak-spawn"'
                    launch_options = f'--host {launcher_path} --game {game.gameid}'
                else:
                    exe = f'"{launcher_path}"'
                    launch_options = f'--game {game.gameid}'

            if existing_app_id:
                game_info = shortcuts["shortcuts"][existing_app_id]
                game_info.update({
                    "Exe": exe,
                    "StartDir": game_directory,
                    "icon": icon,
                    "LaunchOptions": launch_options
                })
            else:
                new_app_id = max([int(k) for k in shortcuts["shortcuts"].keys() if k.isdigit()] or [0]) + 1

                shortcuts["shortcuts"][str(new_app_id)] = {
                    "appid": new_app_id,
                    "AppName": title,
                    "Exe": exe,
                    "StartDir": game_directory,
                    "icon": icon,
                    "ShortcutPath": "",
                    "LaunchOptions": launch_options,
                    "IsHidden": 0,
                    "AllowDesktopConfig": 1,
                    "AllowOverlay": 1,
                    "OpenVR": 0,
                    "Devkit": 0,
                    "DevkitGameID": "",
                    "LastPlayTime": 0,
                    "FlatpakAppID": "",
                }
            save_shortcuts(shortcuts)

        def remove_shortcuts(shortcuts, title):
            # Find and remove existing shortcuts with the same title
            if os.path.exists(steam_shortcuts_path):
                to_remove = [app_id for app_id, game in shortcuts["shortcuts"].items() if
                             isinstance(game, dict) and "AppName" in game and game["AppName"] == title]
                for app_id in to_remove:
                    del shortcuts["shortcuts"][app_id]
                save_shortcuts(shortcuts)

        def load_shortcuts(title):
            # Check if the file exists
            if os.path.exists(steam_shortcuts_path):
                try:
                    # Attempt to load existing shortcuts
                    with open(steam_shortcuts_path, 'rb') as f:
                        return vdf.binary_load(f)
                except SyntaxError:
                    # If the file is corrupted, create a new one
                    return {"shortcuts": {}}
            else:
                # If the file does not exist, create a new one
                return {"shortcuts": {}}

        def save_shortcuts(shortcuts):
            if not os.path.exists(steam_shortcuts_path):
                open(steam_shortcuts_path, 'wb').close()

            with open(steam_shortcuts_path, 'wb') as f:
                vdf.binary_dump(shortcuts, f)

        # Check if the shortcut checkbox is checked
        if not steam_shortcut_state:
            # Remove existing shortcut if it exists
            shortcuts = load_shortcuts(game.title)
            remove_shortcuts(shortcuts, game.title)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return

        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        # Check if the icon file exists
        new_icon_path = f"{icons_dir}/{game.gameid}.ico"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        # Get the directory containing the executable
        game_directory = os.path.dirname(game.path)

        add_game_to_steam(game.title, game_directory, new_icon_path)

    def remove_banner_icon(self, game):
        banner_file_path = f"{banners_dir}/{game.gameid}.png"
        icon_file_path = f"{icons_dir}/{game.gameid}.ico"
        if os.path.exists(banner_file_path):
            os.remove(banner_file_path)
        if os.path.exists(icon_file_path):
            os.remove(icon_file_path)

    def remove_shortcut(self, game, shortcut):
        applications_shortcut_path = f"{app_dir}/{game.gameid}.desktop"
        desktop_shortcut_path = f"{desktop_dir}/{game.gameid}.desktop"

        if shortcut == "appmenu":
            if os.path.exists(applications_shortcut_path):
                os.remove(applications_shortcut_path)
        if shortcut == "desktop":
            if os.path.exists(desktop_shortcut_path):
                os.remove(desktop_shortcut_path)
        if shortcut == "both":
            if os.path.exists(applications_shortcut_path):
                os.remove(applications_shortcut_path)
            if os.path.exists(desktop_shortcut_path):
                os.remove(desktop_shortcut_path)

    def update_list(self):
        self.load_games()
        self.entry_search.set_text("")
        self.show_all()

    def save_games(self):
        all_games_data = load_json_file(games_json, [])

        visible_games_map = {game.gameid: game for game in self.games}
        deleted_id = getattr(self, "_deleted_gameid", None)
        new_games_data = []

        for game_data in all_games_data:
            gameid = game_data.get("gameid")
            hidden = game_data.get("hidden", False)

            if deleted_id and gameid == deleted_id:
                continue
            if not hidden and gameid not in visible_games_map:
                continue

            if gameid in visible_games_map:
                game = visible_games_map.pop(gameid)
                game_data = game_to_save_dict(game, hidden=hidden)

            new_games_data.append(game_data)

        if hasattr(self, "_deleted_gameid"):
            del self._deleted_gameid

        self.backup_games()

        save_json_file(new_games_data, games_json)

    def backup_games(self):
        if os.path.isfile(games_json):
            os.makedirs(backup_dir, exist_ok=True)

            now = GLib.DateTime.new_now_local()
            timestamp = now.format("%Y-%m-%d_%H-%M-%S")

            backup_file = os.path.join(
                backup_dir,
                f"games-data-{timestamp}.json"
            )

            shutil.copy2(games_json, backup_file)

            backups = sorted(
                f for f in os.listdir(backup_dir)
                if f.startswith("games-data-") and f.endswith(".json")
            )

            while len(backups) > 20:
                oldest = backups.pop(0)
                os.remove(os.path.join(backup_dir, oldest))

class Settings(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title=_("Settings"))
        self.set_modal(True)
        self.set_resizable(False)

        self.parent = parent
        self.logging_warning = False
        self.modified = False

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        .paypal {
            color: white;
            background: #001C64;
        }
        .kofi {
            color: white;
            background: #1AC0FF;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.LANG_NAMES = {
            "af": "Afrikaans",
            "am": "Amharic",
            "ar": "Arabic",
            "az": "Azerbaijani",
            "be": "Belarusian",
            "bg": "Bulgarian",
            "bn": "Bengali",
            "bs": "Bosnian",
            "ca": "Catalan",
            "cs": "Czech",
            "cy": "Welsh",
            "da": "Danish",
            "de": "German",
            "el": "Greek",
            "en_US": "English",
            "eo": "Esperanto",
            "es": "Spanish",
            "et": "Estonian",
            "eu": "Basque",
            "fa": "Persian",
            "fi": "Finnish",
            "fil": "Filipino",
            "fr": "French",
            "ga": "Irish",
            "gl": "Galician",
            "gu": "Gujarati",
            "he": "Hebrew",
            "hi": "Hindi",
            "hr": "Croatian",
            "ht": "Haitian Creole",
            "hu": "Hungarian",
            "hy": "Armenian",
            "id": "Indonesian",
            "is": "Icelandic",
            "it": "Italian",
            "ja": "Japanese",
            "jv": "Javanese",
            "ka": "Georgian",
            "kk": "Kazakh",
            "km": "Khmer",
            "kn": "Kannada",
            "ko": "Korean",
            "ku": "Kurdish (Kurmanji)",
            "ky": "Kyrgyz",
            "lo": "Lao",
            "lt": "Lithuanian",
            "lv": "Latvian",
            "mg": "Malagasy",
            "mi": "Maori",
            "mk": "Macedonian",
            "ml": "Malayalam",
            "mn": "Mongolian",
            "mr": "Marathi",
            "ms": "Malay",
            "mt": "Maltese",
            "my": "Burmese",
            "nb": "Norwegian (Bokmål)",
            "ne": "Nepali",
            "nl": "Dutch",
            "nn": "Norwegian (Nynorsk)",
            "pa": "Punjabi",
            "pl": "Polish",
            "ps": "Pashto",
            "pt": "Portuguese (Portugal)",
            "pt_BR": "Portuguese (Brazil)",
            "ro": "Romanian",
            "ru": "Russian",
            "sd": "Sindhi",
            "si": "Sinhala",
            "sk": "Slovak",
            "sl": "Slovenian",
            "so": "Somali",
            "sq": "Albanian",
            "sr": "Serbian",
            "sv": "Swedish",
            "sw": "Swahili",
            "ta": "Tamil",
            "te": "Telugu",
            "tg": "Tajik",
            "th": "Thai",
            "tk": "Turkmen",
            "tl": "Tagalog",
            "tr": "Turkish",
            "tt": "Tatar",
            "ug": "Uyghur",
            "uk": "Ukrainian",
            "ur": "Urdu",
            "uz": "Uzbek",
            "vi": "Vietnamese",
            "xh": "Xhosa",
            "yi": "Yiddish",
            "zh_CN": "Chinese (Simplified)",
            "zh_TW": "Chinese (Traditional)",
            "zu": "Zulu",
        }

        self.lang_codes = {}

        self.label_language = Gtk.Label(label=_("Language"))
        self.label_language.set_halign(Gtk.Align.START)
        self.combobox_language = Gtk.ComboBoxText()
        self.combobox_language.set_wrap_width(4)

        self.label_interface = Gtk.Label(label=_("Interface Mode"))
        self.label_interface.set_halign(Gtk.Align.START)
        self.combobox_interface = Gtk.ComboBoxText()
        self.combobox_interface.connect("changed", self.on_combobox_interface_changed)
        self.combobox_interface.append("List", _("List"))
        self.combobox_interface.append("Blocks", _("Blocks"))
        self.combobox_interface.append("Banners", _("Banners"))

        self.combobox_window_behavior = Gtk.ComboBoxText()
        self.combobox_window_behavior.append("None", _("Default window size"))
        self.combobox_window_behavior.append("Remember", _("Remember window size"))
        self.combobox_window_behavior.append("Maximized", _("Start maximized"))
        self.combobox_window_behavior.append("Fullscreen", _("Start in fullscreen"))
        self.combobox_window_behavior.set_tooltip_text(_("Alt+Enter toggles fullscreen"))

        self.checkbox_show_labels = Gtk.CheckButton(label=_("Show labels"))
        self.checkbox_show_labels.set_active(False)

        self.label_default_prefix = Gtk.Label(label=_("Default Prefixes Location"))
        self.label_default_prefix.set_halign(Gtk.Align.START)

        self.entry_default_prefix = Gtk.Entry()
        self.entry_default_prefix.set_tooltip_text(_("/path/to/the/prefix"))
        self.entry_default_prefix.set_has_tooltip(True)
        self.entry_default_prefix.connect("query-tooltip", on_entry_query_tooltip)
        self.entry_default_prefix.connect("changed", on_entry_changed, self.entry_default_prefix)

        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        self.label_lossless = Gtk.Label(label=_("Lossless Scaling Location"))
        self.label_lossless.set_halign(Gtk.Align.START)

        self.entry_lossless = Gtk.Entry()
        self.entry_lossless.set_tooltip_text(_("/path/to/Lossless.dll"))
        self.entry_lossless.set_has_tooltip(True)
        self.entry_lossless.connect("query-tooltip", on_entry_query_tooltip)

        self.button_search_lossless = Gtk.Button()
        self.button_search_lossless.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_lossless.connect("clicked", self.on_button_search_lossless_clicked)
        self.button_search_lossless.set_size_request(50, -1)

        self.label_default_prefix_tools = Gtk.Label(label=_("Default Prefix Tools"))
        self.label_default_prefix_tools.set_halign(Gtk.Align.START)
        self.label_default_prefix_tools.set_margin_start(10)
        self.label_default_prefix_tools.set_margin_end(10)
        self.label_default_prefix_tools.set_margin_top(10)

        self.label_runner = Gtk.Label(label=_("Default Proton"))
        self.label_runner.set_halign(Gtk.Align.START)
        self.combobox_runner = Gtk.ComboBoxText()

        self.button_proton_manager = Gtk.Button(label=_("Proton Manager"))
        self.button_proton_manager.connect("clicked", self.on_button_proton_manager_clicked)

        self.label_miscellaneous = Gtk.Label(label=_("Miscellaneous"))
        self.label_miscellaneous.set_halign(Gtk.Align.START)
        self.label_miscellaneous.set_margin_start(10)
        self.label_miscellaneous.set_margin_end(10)

        self.checkbox_discrete_gpu = Gtk.CheckButton(label=_("Use discrete GPU"))

        self.checkbox_close_after_launch = Gtk.CheckButton(label=_("Close when running a game/app"))

        self.checkbox_start_boot = Gtk.CheckButton(label=_("Start on boot"))

        self.checkbox_system_tray = Gtk.CheckButton(label=_("System tray icon"))
        self.checkbox_system_tray.connect("toggled", self.on_checkbox_system_tray_toggled)

        self.checkbox_start_minimized = Gtk.CheckButton(label=_("Start minimized to tray"))
        self.checkbox_start_minimized.set_sensitive(False)

        self.checkbox_mono_icon = Gtk.CheckButton(label=_("Monochrome icon"))
        self.checkbox_mono_icon.set_sensitive(False)

        self.checkbox_splash_disable = Gtk.CheckButton(label=_("Disable splash window"))
        self.checkbox_splash_disable.set_active(False)

        self.checkbox_disable_updates = Gtk.CheckButton(label=_("Disable automatic updates"))
        self.checkbox_disable_updates.set_active(False)

        self.checkbox_enable_logging = Gtk.CheckButton(label=_("Enable logging"))
        self.checkbox_enable_logging.set_active(False)

        self.checkbox_show_categories = Gtk.CheckButton(label=_("Show categories and sort buttons"))

        self.checkbox_show_hidden = Gtk.CheckButton(label=_("Show hidden games"))
        self.checkbox_show_hidden.set_tooltip_text(_("Press Ctrl+H to show/hide games."))

        self.checkbox_gamepad_navigation = Gtk.CheckButton(label=_("Gamepad navigation"))
        self.checkbox_gamepad_navigation.set_active(False)

        self.checkbox_wayland_driver = Gtk.CheckButton(label=_("Use Wayland driver (experimental)"))
        self.checkbox_wayland_driver.set_active(False)

        self.checkbox_enable_wow64 = Gtk.CheckButton(label=_("Enable WOW64 (experimental)"))

        self.button_winetricks_default = Gtk.Button(label="Winetricks")
        self.button_winetricks_default.connect("clicked", self.on_button_winetricks_default_clicked)
        self.button_winetricks_default.set_size_request(120, -1)

        self.button_winecfg_default = Gtk.Button(label="Winecfg")
        self.button_winecfg_default.connect("clicked", self.on_button_winecfg_default_clicked)
        self.button_winecfg_default.set_size_request(120, -1)

        self.button_run_default = Gtk.Button(label=_("Run"))
        self.button_run_default.set_size_request(120, -1)
        self.button_run_default.connect("clicked", self.on_button_run_default_clicked)
        self.button_run_default.set_tooltip_text(_("Run a file inside the prefix"))

        create_mangohud_gamemode_checkboxes(self)
        self.checkbox_disable_hidraw = Gtk.CheckButton(label=_("Disable Hidraw"))
        self.checkbox_prevent_sleep = Gtk.CheckButton(label=_("Prevent Sleep"))

        self.label_support = Gtk.Label(label=_("Support the Project"))
        self.label_support.set_halign(Gtk.Align.START)
        self.label_support.set_margin_start(10)
        self.label_support.set_margin_end(10)
        self.label_support.set_margin_top(10)

        button_kofi, button_paypal = make_donate_buttons()

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        self.button_cancel.set_size_request(150, -1)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        self.button_ok.set_size_request(150, -1)

        self.label_settings = Gtk.Label(label=_("Backup/Restore Settings"))
        self.label_settings.set_halign(Gtk.Align.START)
        self.label_settings.set_margin_start(10)
        self.label_settings.set_margin_end(10)
        self.label_settings.set_margin_top(10)

        button_backup = Gtk.Button(label=_("Backup"))
        button_backup.connect("clicked", self.on_button_backup_clicked)

        button_restore = Gtk.Button(label=_("Restore"))
        button_restore.connect("clicked", self.on_button_restore_clicked)

        self.button_clearlogs = Gtk.Button()
        self.update_button_label()
        self.button_clearlogs.connect("clicked", self.on_clear_logs_clicked)

        self.label_envar = Gtk.Label(label=_("Global Environment Variables"))
        self.label_envar.set_halign(Gtk.Align.START)

        self.liststore = Gtk.ListStore(str)
        self.liststore.append([""])

        treeview = Gtk.TreeView(model=self.liststore)
        treeview.set_has_tooltip(True)
        treeview.connect("query-tooltip", self.on_query_tooltip)
        treeview.connect("key-press-event", self.on_envar_key_press)

        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.set_property("ellipsize", 3)
        renderer.connect("edited", self.on_cell_edited, 0)

        column = Gtk.TreeViewColumn("", renderer, text=0)
        treeview.set_headers_visible(False)

        treeview.append_column(column)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(130)
        scrolled_window.add(treeview)

        self.box = self.get_content_area()
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)
        self.box.set_halign(Gtk.Align.CENTER)
        self.box.set_valign(Gtk.Align.CENTER)
        self.box.set_vexpand(True)
        self.box.set_hexpand(True)

        url = f"https://github.com/Faugus/faugus-launcher/releases"
        label_version = Gtk.Label()
        label_version.set_markup(f'<span underline="none"><a href="{url}"> {VERSION} </a></span>')
        label_version.set_use_markup(True)

        frame = Gtk.Frame()
        frame.set_label_widget(label_version)
        frame.set_label_align(0.99, 0.5)
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_bottom(10)

        box_main = Gtk.Grid()
        box_main.set_column_homogeneous(True)
        box_main.set_column_spacing(10)
        box_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        box_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        grid_language = Gtk.Grid()
        grid_language.set_row_spacing(10)
        grid_language.set_column_spacing(10)
        grid_language.set_margin_start(10)
        grid_language.set_margin_end(10)
        grid_language.set_margin_top(10)
        grid_language.set_margin_bottom(10)

        grid_prefix = Gtk.Grid()
        grid_prefix.set_row_spacing(10)
        grid_prefix.set_column_spacing(10)
        grid_prefix.set_margin_start(10)
        grid_prefix.set_margin_end(10)
        grid_prefix.set_margin_bottom(10)

        grid_runner = Gtk.Grid()
        grid_runner.set_row_spacing(10)
        grid_runner.set_column_spacing(10)
        grid_runner.set_margin_start(10)
        grid_runner.set_margin_end(10)
        grid_runner.set_margin_top(10)
        grid_runner.set_margin_bottom(10)

        grid_lossless = Gtk.Grid()
        grid_lossless.set_row_spacing(10)
        grid_lossless.set_column_spacing(10)
        grid_lossless.set_margin_start(10)
        grid_lossless.set_margin_end(10)
        grid_lossless.set_margin_top(10)
        grid_lossless.set_margin_bottom(10)

        grid_tools = Gtk.Grid()
        grid_tools.set_row_spacing(10)
        grid_tools.set_column_spacing(10)
        grid_tools.set_margin_start(10)
        grid_tools.set_margin_end(10)
        grid_tools.set_margin_top(10)
        grid_tools.set_margin_bottom(10)

        grid_logs = Gtk.Grid()
        grid_logs.set_row_spacing(10)
        grid_logs.set_column_spacing(10)
        grid_logs.set_margin_start(10)
        grid_logs.set_margin_end(10)
        grid_logs.set_margin_top(10)
        grid_logs.set_margin_bottom(10)

        grid_miscellaneous = Gtk.Grid()
        grid_miscellaneous.set_row_spacing(10)
        grid_miscellaneous.set_column_spacing(10)
        grid_miscellaneous.set_margin_start(10)
        grid_miscellaneous.set_margin_end(10)
        grid_miscellaneous.set_margin_top(10)
        grid_miscellaneous.set_margin_bottom(10)

        grid_envar = Gtk.Grid()
        grid_envar.set_row_spacing(10)
        grid_envar.set_column_spacing(10)
        grid_envar.set_margin_start(10)
        grid_envar.set_margin_end(10)
        grid_envar.set_margin_bottom(10)

        grid_interface_mode = Gtk.Grid()
        grid_interface_mode.set_row_spacing(10)
        grid_interface_mode.set_column_spacing(10)
        grid_interface_mode.set_margin_start(10)
        grid_interface_mode.set_margin_end(10)
        grid_interface_mode.set_margin_top(10)
        grid_interface_mode.set_margin_bottom(10)

        grid_support = Gtk.Grid()
        grid_support.set_column_homogeneous(True)
        grid_support.set_row_spacing(10)
        grid_support.set_column_spacing(10)
        grid_support.set_margin_start(10)
        grid_support.set_margin_end(10)
        grid_support.set_margin_top(10)
        grid_support.set_margin_bottom(10)

        grid_backup = Gtk.Grid()
        grid_backup.set_column_homogeneous(True)
        grid_backup.set_row_spacing(10)
        grid_backup.set_column_spacing(10)
        grid_backup.set_margin_start(10)
        grid_backup.set_margin_end(10)
        grid_backup.set_margin_top(10)
        grid_backup.set_margin_bottom(10)

        self.grid_big_interface = Gtk.Grid()
        self.grid_big_interface.set_row_spacing(10)
        self.grid_big_interface.set_column_spacing(10)
        self.grid_big_interface.set_margin_start(10)
        self.grid_big_interface.set_margin_end(10)
        self.grid_big_interface.set_margin_bottom(10)

        grid_language.attach(self.label_language, 0, 0, 1, 1)
        grid_language.attach(self.combobox_language, 0, 1, 1, 1)
        self.combobox_language.set_hexpand(True)

        grid_prefix.attach(self.label_default_prefix, 0, 0, 1, 1)
        grid_prefix.attach(self.entry_default_prefix, 0, 1, 3, 1)
        self.entry_default_prefix.set_hexpand(True)
        grid_prefix.attach(self.button_search_prefix, 3, 1, 1, 1)

        grid_runner.attach(self.label_runner, 0, 6, 1, 1)
        grid_runner.attach(self.combobox_runner, 0, 7, 1, 1)
        grid_runner.attach(self.button_proton_manager, 0, 8, 1, 1)

        grid_lossless.attach(self.label_lossless, 0, 0, 1, 1)
        grid_lossless.attach(self.entry_lossless, 0, 1, 3, 1)
        grid_lossless.attach(self.button_search_lossless, 3, 1, 1, 1)

        self.combobox_runner.set_hexpand(True)
        self.button_proton_manager.set_hexpand(True)
        self.entry_lossless.set_hexpand(True)

        box_buttons.pack_start(self.button_winetricks_default, True, True, 0)
        box_buttons.pack_start(self.button_winecfg_default, True, True, 0)
        box_buttons.pack_start(self.button_run_default, True, True, 0)

        grid_tools.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        grid_tools.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        grid_tools.attach(self.checkbox_prevent_sleep, 0, 2, 1, 1)
        grid_tools.attach(self.checkbox_disable_hidraw, 0, 3, 1, 1)
        grid_tools.attach(box_buttons, 2, 0, 1, 4)

        grid_logs.attach(self.checkbox_enable_logging, 0, 0, 1, 1)
        grid_logs.attach(self.button_clearlogs, 0, 1, 1, 1)
        self.button_clearlogs.set_hexpand(True)

        grid_miscellaneous.attach(self.checkbox_discrete_gpu, 0, 0, 1, 1)
        grid_miscellaneous.attach(self.checkbox_splash_disable, 0, 1, 1, 1)
        grid_miscellaneous.attach(self.checkbox_disable_updates, 0, 2, 1, 1)
        grid_miscellaneous.attach(self.checkbox_close_after_launch, 0, 3, 1, 1)
        grid_miscellaneous.attach(self.checkbox_show_categories, 0, 4, 1, 1)
        grid_miscellaneous.attach(self.checkbox_show_hidden, 0, 5, 1, 1)
        grid_miscellaneous.attach(self.checkbox_gamepad_navigation, 0, 6, 1, 1)
        grid_miscellaneous.attach(self.checkbox_start_boot, 0, 7, 1, 1)
        grid_miscellaneous.attach(self.checkbox_system_tray, 0, 8, 1, 1)
        grid_miscellaneous.attach(self.checkbox_start_minimized, 0, 9, 1, 1)
        grid_miscellaneous.attach(self.checkbox_mono_icon, 0, 10, 1, 1)
        grid_miscellaneous.attach(self.checkbox_wayland_driver, 0, 11, 1, 1)
        grid_miscellaneous.attach(self.checkbox_enable_wow64, 0, 12, 1, 1)

        grid_interface_mode.attach(self.label_interface, 0, 0, 1, 1)
        grid_interface_mode.attach(self.combobox_interface, 0, 1, 1, 1)
        self.combobox_interface.set_hexpand(True)

        grid_envar.attach(self.label_envar, 0, 0, 1, 1)
        grid_envar.attach(scrolled_window, 0, 1, 1, 1)
        scrolled_window.set_hexpand(True)

        grid_backup.attach(button_backup, 0, 1, 1, 1)
        grid_backup.attach(button_restore, 1, 1, 1, 1)

        self.grid_big_interface.attach(self.combobox_window_behavior, 0, 0, 1, 1)
        self.grid_big_interface.attach(self.checkbox_show_labels, 0, 1, 1, 1)
        self.combobox_window_behavior.set_hexpand(True)

        grid_support.attach(button_kofi, 0, 1, 1, 1)
        grid_support.attach(button_paypal, 1, 1, 1, 1)

        box_left.pack_start(grid_prefix, False, False, 0)
        box_left.pack_start(grid_runner, False, False, 0)
        box_left.pack_start(self.label_default_prefix_tools, False, False, 0)
        box_left.pack_start(grid_tools, False, False, 0)
        box_left.pack_start(grid_lossless, False, False, 0)
        box_left.pack_end(grid_language, False, False, 0)

        box_mid.pack_start(self.label_miscellaneous, False, False, 0)
        box_mid.pack_start(grid_miscellaneous, False, False, 0)
        box_mid.pack_end(grid_support, False, False, 0)
        box_mid.pack_end(self.label_support, False, False, 0)

        box_right.pack_start(grid_envar, False, False, 0)
        box_right.pack_start(grid_logs, False, False, 0)
        box_right.pack_start(grid_interface_mode, False, False, 0)
        box_right.pack_start(self.grid_big_interface, False, False, 0)
        box_right.pack_end(grid_backup, False, False, 0)
        box_right.pack_end(self.label_settings, False, False, 0)

        box_main.attach(box_left, 0, 0, 1, 1)
        box_main.attach(box_mid, 1, 0, 1, 1)
        box_main.attach(box_right, 2, 0, 1, 1)
        box_left.set_hexpand(True)
        box_mid.set_hexpand(True)
        frame.add(box_main)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        box_bottom.pack_start(self.button_cancel, True, True, 0)
        box_bottom.pack_start(self.button_ok, True, True, 0)

        self.box.add(frame)
        self.box.add(box_bottom)

        self.populate_combobox_with_runners()
        self.populate_languages()
        self.load_config()

        self.show_all()
        self.on_combobox_interface_changed(self.combobox_interface)

        disable_mangohud_gamemode_if_missing(self)
        self.track_modifications(self.box)

    def on_envar_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Delete:
            selection = widget.get_selection()
            model, treeiter = selection.get_selected()

            if not treeiter:
                return False

            path = model.get_path(treeiter)
            index = path.get_indices()[0]

            if index == len(model) - 1:
                return True

            model.remove(treeiter)
            return True

        return False

    def get_dir_size(self, path):
        total = 0
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    total += os.path.getsize(fp)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if total < 1024.0:
                return f"{total:.1f} {unit}"
            total /= 1024.0
        return f"{total:.1f} TB"

    def update_button_label(self):
        if os.path.exists(logs_dir):
            size = self.get_dir_size(logs_dir)
            self.button_clearlogs.set_label(_("Clear Logs (%s)") % size)
            self.button_clearlogs.set_sensitive(True)
        else:
            self.button_clearlogs.set_label(_("Clear Logs"))
            self.button_clearlogs.set_sensitive(False)

    def on_clear_logs_clicked(self, button):
        if os.path.exists(logs_dir):
            shutil.rmtree(logs_dir)
        self.update_button_label()

    def on_query_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        result = widget.get_path_at_pos(x, y)
        if result is not None:
            path, column, cell_x, cell_y = result
            tree_iter = self.liststore.get_iter(path)
            value = self.liststore.get_value(tree_iter, 0)
            if value.strip():
                tooltip.set_text(value)
                return True
        return False

    def on_cell_edited(self, widget, path, text, column_index):
        self.liststore[path][column_index] = text
        self.adjust_rows()

    def adjust_rows(self):
        filled_rows = [row[0] for row in self.liststore if row[0].strip() != ""]
        self.liststore.clear()

        for value in filled_rows:
            self.liststore.append([value])

        self.liststore.append([""])

    def populate_languages(self):
        self.combobox_language.remove_all()

        available_langs = [("English", "en_US")]

        if os.path.isdir(LOCALE_DIR):
            for lang in os.listdir(LOCALE_DIR):
                mo_file = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "faugus-launcher.mo")
                if os.path.isfile(mo_file):
                    lang_name = self.LANG_NAMES.get(lang, lang)
                    if lang != "en_US":
                        available_langs.append((lang_name, lang))

        available_langs.sort(key=lambda x: x[0])

        for lang_name, lang_code in available_langs:
            self.combobox_language.append_text(lang_name)
            self.lang_codes[lang_name] = lang_code

        self.combobox_language.set_active(0)

    def on_combobox_interface_changed(self, combobox):
        active_id = combobox.get_active_id()
        if active_id == "List":
            self.grid_big_interface.set_visible(False)
        if active_id == "Blocks":
            self.grid_big_interface.set_visible(True)
            self.checkbox_show_labels.set_visible(False)
        if active_id == "Banners":
            self.grid_big_interface.set_visible(True)
            self.checkbox_show_labels.set_visible(True)

    def on_checkbox_system_tray_toggled(self, widget):
        if not widget.get_active():
            self.checkbox_start_minimized.set_sensitive(False)
            self.checkbox_mono_icon.set_sensitive(False)
        else:
            self.checkbox_start_minimized.set_sensitive(True)
            self.checkbox_mono_icon.set_sensitive(True)

    def populate_combobox_with_runners(self):
        populate_combobox_with_runners(self.combobox_runner)

    def update_config_file(self):
        combobox_language = self.combobox_language.get_active_text()
        entry_default_prefix = os.path.expanduser(self.entry_default_prefix.get_text())
        combobox_default_runner = self.get_default_runner()
        entry_lossless = os.path.expanduser(self.entry_lossless.get_text())
        language = self.lang_codes.get(combobox_language, "en_US")
        logging_warning = self.logging_warning

        config = ConfigManager()
        config.set_value("language", language)
        config.set_value("default-prefix", entry_default_prefix)
        config.set_value("default-runner", combobox_default_runner)
        config.set_value("lossless-location", entry_lossless)
        config.set_value("mangohud", self.checkbox_mangohud.get_active())
        config.set_value("gamemode", self.checkbox_gamemode.get_active())
        config.set_value("disable-hidraw", self.checkbox_disable_hidraw.get_active())
        config.set_value("prevent-sleep", self.checkbox_prevent_sleep.get_active())
        config.set_value("discrete-gpu", self.checkbox_discrete_gpu.get_active())
        config.set_value("splash-disable", self.checkbox_splash_disable.get_active())
        config.set_value("disable-updates", self.checkbox_disable_updates.get_active())
        config.set_value("system-tray", self.checkbox_system_tray.get_active())
        config.set_value("start-boot", self.checkbox_start_boot.get_active())
        config.set_value("mono-icon", self.checkbox_mono_icon.get_active())
        config.set_value("close-onlaunch", self.checkbox_close_after_launch.get_active())
        config.set_value("enable-logging", self.checkbox_enable_logging.get_active())
        config.set_value("show-hidden", self.checkbox_show_hidden.get_active())
        config.set_value("wayland-driver", self.checkbox_wayland_driver.get_active())
        config.set_value("enable-wow64", self.checkbox_enable_wow64.get_active())
        config.set_value("interface-mode", self.combobox_interface.get_active_id())
        config.set_value("show-labels", self.checkbox_show_labels.get_active())
        config.set_value("logging-warning", logging_warning)
        config.set_value("gamepad-navigation", self.checkbox_gamepad_navigation.get_active())
        config.set_value("start-minimized", self.checkbox_start_minimized.get_active())
        config.set_value("show-categories", self.checkbox_show_categories.get_active())
        config.set_value("window-behavior", self.combobox_window_behavior.get_active_id())
        config.save_config()

        self.set_sensitive(False)

    def get_default_runner(self):
        default_runner = self.combobox_runner.get_active_text()
        default_runner = convert_runner(default_runner)
        return default_runner

    def update_envar_file(self):
        if hasattr(self, "liststore"):
            values = [row[0] for row in self.liststore if row[0].strip() != ""]
            with open(envar_dir, "w", encoding="utf-8") as f:
                for val in values:
                    f.write(val + "\n")

    def on_button_proton_manager_clicked(self, widget):
        current_runner = self.combobox_runner.get_active_text()

        from faugus.proton_manager import ProtonDownloader
        dialog = ProtonDownloader()
        dialog.run()
        dialog.destroy()

        self.combobox_runner.remove_all()
        self.populate_combobox_with_runners()

        if current_runner:
            for i, text in enumerate(self.combobox_runner.get_model()):
                if text[0] == current_runner:
                    self.combobox_runner.set_active(i)
                    break

    def track_modifications(self, container):
        for child in container.get_children():
            if isinstance(child, Gtk.Entry):
                child.connect("changed", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.CheckButton):
                child.connect("toggled", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.ComboBox):
                child.connect("changed", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.TreeView):
                selection = child.get_selection()
                selection.connect("changed", lambda sel: setattr(self, "modified", True))
            elif isinstance(child, Gtk.Container):
                self.track_modifications(child)

    def check_modified(self):
        self.track_modifications(self.box)
        if self.modified:
            proceed = self.show_warning_dialog_settings(self.parent, _("Do you want to save the changes?"), True)
            if proceed:
                if self.entry_default_prefix.get_text() == "":
                    self.entry_default_prefix.get_style_context().add_class("entry")
                    return
                self.update_envar_file()
                self.update_config_file()
                self.parent.manage_autostart_file(self.checkbox_start_boot.get_active(), self.checkbox_start_minimized.get_active())
                if self.checkbox_system_tray.get_active():
                    self.parent.system_tray = True
                else:
                    self.parent.system_tray = False
                GLib.timeout_add(1000, self.parent.load_tray_icon)
                self.modified = False

            else:
                self.load_config()
                self.modified = False

    def on_button_winetricks_default_clicked(self, widget):
        self.check_modified()
        self.set_sensitive(False)

        default_runner = self.get_default_runner()
        command_parts = []

        command_parts.append(f"GAMEID=winetricks-gui")
        command_parts.append(f"STORE=none")
        if default_runner:
            if default_runner == "Proton-CachyOS (System)":
                command_parts.append(f"PROTONPATH='{proton_cachyos}'")
            else:
                command_parts.append(f"PROTONPATH='{default_runner}'")

        command_parts.append(f"'{umu_run}'")
        command_parts.append("''")
        command = ' '.join(command_parts)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command, "winetricks"])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)

        threading.Thread(target=run_command, daemon=True).start()

    def on_button_winecfg_default_clicked(self, widget):
        self.check_modified()
        self.set_sensitive(False)

        default_runner = self.get_default_runner()
        command_parts = []

        if default_runner:
            if default_runner == "Proton-CachyOS (System)":
                command_parts.append(f"PROTONPATH='{proton_cachyos}'")
            else:
                command_parts.append(f"PROTONPATH='{default_runner}'")

        command_parts.append(f"'{umu_run}'")
        command_parts.append("'winecfg'")
        command = ' '.join(command_parts)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)

        threading.Thread(target=run_command, daemon=True).start()

    def on_button_run_default_clicked(self, widget):
        self.check_modified()
        default_runner = self.get_default_runner()

        filechooser = Gtk.FileChooserNative(
            title=_("Select a file to run inside the prefix"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        add_windows_file_filters(filechooser)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            file_run = filechooser.get_filename()
            game_directory = os.path.dirname(file_run)
            cwd = game_directory if game_directory and os.path.isdir(game_directory) else None
            escaped_file_run = file_run.replace("'", "'\\''")
            command_parts = []

            if not escaped_file_run.endswith(".reg"):
                if default_runner:
                    if default_runner == "Proton-CachyOS (System)":
                        command_parts.append(f"PROTONPATH='{proton_cachyos}'")
                    else:
                        command_parts.append(f"PROTONPATH='{default_runner}'")
                command_parts.append(f"'{umu_run}' '{escaped_file_run}'")
            else:
                if default_runner:
                    if default_runner == "Proton-CachyOS (System)":
                        command_parts.append(f"PROTONPATH='{proton_cachyos}'")
                    else:
                        command_parts.append(f"PROTONPATH='{default_runner}'")
                command_parts.append(f"'{umu_run}' regedit '{escaped_file_run}'")

            command = ' '.join(command_parts)
            cmd = (sys.executable, "-m", "faugus.runner", command)

            def run_command():
                process = subprocess.Popen(cmd, cwd=cwd if cwd else None)
                process.wait()

            threading.Thread(target=run_command, daemon=True).start()
        else:
            self.set_sensitive(True)

    def on_button_backup_clicked(self, widget):
        self.check_modified()

        from faugus.backup import BackupWindow

        self.destroy()

        backup_win = BackupWindow(None, faugus_launcher_dir)
        backup_win.show_all()

    def on_button_restore_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select a backup file to restore"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        zip_filter = Gtk.FileFilter()
        zip_filter.set_name(_("ZIP files"))
        zip_filter.add_pattern("*.zip")
        filechooser.add_filter(zip_filter)
        filechooser.set_filter(zip_filter)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            zip_file = filechooser.get_filename()
            if not os.path.isfile(zip_file):
                filechooser.destroy()
                self.show_warning_dialog_settings(self, _("This is not a valid Faugus Launcher backup file."), False)
                return

            temp_dir = os.path.join(faugus_launcher_dir, "temp-restore")
            shutil.unpack_archive(zip_file, temp_dir, "zip")

            marker_path = os.path.join(temp_dir, ".faugus_marker")
            if not os.path.exists(marker_path):
                shutil.rmtree(temp_dir)
                filechooser.destroy()
                self.show_warning_dialog_settings(self, _("This is not a valid Faugus Launcher backup file."), False)
                return

            if self.show_warning_dialog_settings(self, _("Are you sure you want to overwrite the settings?"), True):
                for item in os.listdir(temp_dir):
                    if item == ".faugus_marker":
                        continue
                    src = os.path.join(temp_dir, item)
                    dst = os.path.join(faugus_launcher_dir, item)

                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    elif os.path.isfile(dst):
                        os.remove(dst)

                    if os.path.isdir(src):
                        shutil.copytree(src, dst)
                    elif os.path.isfile(src):
                        shutil.copy2(src, dst)

                shutil.rmtree(temp_dir)
                global faugus_backup
                faugus_backup = True
                self.response(Gtk.ResponseType.OK)

        filechooser.destroy()

    def show_warning_dialog_settings(self, parent, title, buttons):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_modal(True)
        dialog.set_resizable(False)
        play_notification_sound()

        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.CENTER)

        button_confirm = Gtk.Button(label=_("Yes"))
        button_confirm.set_size_request(150, -1)
        button_confirm.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.OK))

        button_no = Gtk.Button(label=_("No"))
        button_no.set_size_request(150, -1)
        button_no.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.CANCEL))

        content_area = dialog.get_content_area()

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.pack_start(label, True, True, 0)

        if buttons:
            box_bottom.pack_start(button_no, True, True, 0)
        else:
            button_confirm.set_label(_("Ok"))

        box_bottom.pack_start(button_confirm, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        return response == Gtk.ResponseType.OK

    def on_button_search_prefix_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select a prefix location"),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        if os.path.isdir(self.default_prefix):
            filechooser.set_current_folder(self.default_prefix)
        else:
            filechooser.set_current_folder(os.path.expanduser("~"))

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            folder = filechooser.get_filename()
            if folder:
                self.entry_default_prefix.set_text(folder)

        filechooser.destroy()

    def on_button_search_lossless_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select the Lossless.dll file"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        filter_dll = Gtk.FileFilter()
        filter_dll.set_name("Lossless.dll")
        filter_dll.add_pattern("Lossless.dll")
        filechooser.add_filter(filter_dll)
        filechooser.set_filter(filter_dll)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            selected_file = filechooser.get_filename()
            if selected_file and os.path.basename(selected_file) == "Lossless.dll":
                self.entry_lossless.set_text(selected_file)

        filechooser.destroy()

    def load_config(self):
        cfg = ConfigManager()

        close_on_launch = cfg.config.get('close-onlaunch', 'False') == 'True'
        self.default_prefix = cfg.config.get('default-prefix', '').strip('"')
        mangohud = cfg.config.get('mangohud', 'False') == 'True'
        gamemode = cfg.config.get('gamemode', 'False') == 'True'
        disable_hidraw = cfg.config.get('disable-hidraw', 'False') == 'True'
        prevent_sleep = cfg.config.get('prevent-sleep', 'False') == 'True'
        self.default_runner = cfg.config.get('default-runner', '').strip('"')
        lossless_location = cfg.config.get('lossless-location', '').strip('"')
        discrete_gpu = cfg.config.get('discrete-gpu', 'False') == 'True'
        splash_disable = cfg.config.get('splash-disable', 'False') == 'True'
        disable_updates = cfg.config.get('disable-updates', 'False') == 'True'
        system_tray = cfg.config.get('system-tray', 'False') == 'True'
        self.start_boot = cfg.config.get('start-boot', 'False') == 'True'
        self.mono_icon = cfg.config.get('mono-icon', 'False') == 'True'
        self.interface_mode = cfg.config.get('interface-mode', '').strip('"')
        show_labels = cfg.config.get('show-labels', 'False') == 'True'
        enable_logging = cfg.config.get('enable-logging', 'False') == 'True'
        show_hidden = cfg.config.get('show-hidden', 'False') == 'True'
        gamepad_navigation = cfg.config.get('gamepad-navigation', 'False') == 'True'
        wayland_driver = cfg.config.get('wayland-driver', 'False') == 'True'
        enable_wow64 = cfg.config.get('enable-wow64', 'False') == 'True'
        self.language = cfg.config.get('language', '')
        self.logging_warning = cfg.config.get('logging-warning', 'False') == 'True'
        start_minimized = cfg.config.get('start-minimized', 'False') == 'True'
        show_categories = cfg.config.get('show-categories', 'False') == 'True'
        window_behavior = cfg.config.get('window-behavior', '')

        self.checkbox_close_after_launch.set_active(close_on_launch)
        self.entry_default_prefix.set_text(self.default_prefix)

        self.checkbox_mangohud.set_active(mangohud)
        self.checkbox_gamemode.set_active(gamemode)
        self.checkbox_disable_hidraw.set_active(disable_hidraw)
        self.checkbox_prevent_sleep.set_active(prevent_sleep)

        if not lossless_location:
            if lossless_dll:
                self.entry_lossless.set_text(str(lossless_dll))
        else:
            self.entry_lossless.set_text(lossless_location)

        self.default_runner = convert_runner(self.default_runner)
        model_runner = self.combobox_runner.get_model()
        index_runner = 0
        for i, row in enumerate(model_runner):
            if row[0] == self.default_runner:
                index_runner = i
                break

        self.combobox_runner.set_active(index_runner)
        self.checkbox_discrete_gpu.set_active(discrete_gpu)
        self.checkbox_splash_disable.set_active(splash_disable)
        self.checkbox_disable_updates.set_active(disable_updates)
        self.checkbox_system_tray.set_active(system_tray)
        self.checkbox_start_boot.set_active(self.start_boot)
        self.checkbox_mono_icon.set_active(self.mono_icon)
        self.checkbox_show_labels.set_active(show_labels)
        self.checkbox_enable_logging.set_active(enable_logging)
        self.checkbox_show_hidden.set_active(show_hidden)
        self.checkbox_gamepad_navigation.set_active(gamepad_navigation)
        self.checkbox_wayland_driver.set_active(wayland_driver)
        self.checkbox_enable_wow64.set_active(enable_wow64)
        self.combobox_interface.set_active_id(self.interface_mode)
        self.checkbox_start_minimized.set_active(start_minimized)
        self.checkbox_show_categories.set_active(show_categories)
        self.combobox_window_behavior.set_active_id(window_behavior)

        model_language = self.combobox_language.get_model()
        index_language = 0

        if self.language == "":
            self.combobox_language.set_active(index_language)
        else:
            for i, row in enumerate(model_language):
                lang_name = row[0]
                lang_code = self.lang_codes.get(lang_name, "")
                if lang_code == self.language:
                    index_language = i
                    break

            self.combobox_language.set_active(index_language)
        self.load_liststore_from_file(envar_dir)

    def load_liststore_from_file(self, filename=envar_dir):
        self.liststore.clear()

        try:
            with open(filename, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
        except FileNotFoundError:
            lines = []

        for line in lines:
            self.liststore.append([line])

        self.liststore.append([""])

class Game:
    def __init__(
        self,
        gameid,
        title,
        path,
        prefix,
        launch_arguments,
        game_arguments,
        mangohud,
        gamemode,
        disable_hidraw,
        protonfix,
        runner,
        addapp_checkbox,
        addapp,
        addapp_bat,
        addapp_delay,
        addapp_first,
        banner,
        lossless_enabled,
        lossless_multiplier,
        lossless_flow,
        lossless_performance,
        lossless_hdr,
        lossless_present,
        playtime,
        hidden,
        prevent_sleep,
        category,
        icon,
    ):
        self.gameid = gameid
        self.title = title
        self.path = path
        self.launch_arguments = launch_arguments
        self.game_arguments = game_arguments
        self.mangohud = mangohud
        self.gamemode = gamemode
        self.prefix = prefix
        self.disable_hidraw = disable_hidraw
        self.protonfix = protonfix
        self.runner = runner
        self.addapp_checkbox = addapp_checkbox
        self.addapp = addapp
        self.addapp_bat = addapp_bat
        self.addapp_delay = addapp_delay
        self.addapp_first = addapp_first
        self.banner = banner
        self.lossless_enabled = lossless_enabled
        self.lossless_multiplier = lossless_multiplier
        self.lossless_flow = lossless_flow
        self.lossless_performance = lossless_performance
        self.lossless_hdr = lossless_hdr
        self.lossless_present = lossless_present
        self.playtime = playtime
        self.hidden = hidden
        self.prevent_sleep = prevent_sleep
        self.category = category
        self.icon = icon

class DuplicateDialog(Gtk.Dialog):
    def __init__(self, parent, title):
        super().__init__(title=_("Duplicate %s") % title)
        self.set_modal(True)
        self.set_resizable(False)

        label_title = Gtk.Label(label=_("Title"))
        label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.set_tooltip_text(_("Game Title"))

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        button_cancel.set_size_request(150, -1)

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        button_ok.set_size_request(150, -1)

        content_area = self.get_content_area()
        content_area.set_border_width(0)
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(10)
        box_top.set_margin_end(10)
        box_top.set_margin_top(10)
        box_top.set_margin_bottom(20)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.pack_start(label_title, True, True, 0)
        box_top.pack_start(self.entry_title, True, True, 0)

        box_bottom.pack_start(button_cancel, True, True, 0)
        box_bottom.pack_start(button_ok, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        self.show_all()

class DeleteDialog(Gtk.Dialog):
    def __init__(self, parent, title, prefix, runner):
        super().__init__(title=_("Delete %s") % title)
        self.set_modal(True)
        self.set_resizable(False)
        play_notification_sound()

        label = Gtk.Label()
        label.set_label(_("Are you sure you want to delete %s?") % title)
        label.set_halign(Gtk.Align.CENTER)

        prefix_label = Gtk.Label()
        prefix_label.set_label(prefix)
        prefix_label.set_halign(Gtk.Align.CENTER)

        # display a warning message if the prefix about to get deleted is shared with other games
        pfx_count = prefixes_count(prefix)
        if pfx_count > 0:
            warn_msg = _("WARNING: This prefix is used by %d other games.") % pfx_count
            if pfx_count == 1:
                warn_msg = _("WARNING: This prefix is used by 1 other game.")
            warn_label = Gtk.Label()
            warn_label.set_markup(f'<span color="red">{warn_msg}</span>')
            warn_label.set_use_markup(True)
            warn_label.set_halign(Gtk.Align.CENTER)

        button_no = Gtk.Button(label=_("No"))
        button_no.set_size_request(150, -1)
        button_no.connect("clicked", lambda x: self.response(Gtk.ResponseType.NO))

        button_yes = Gtk.Button(label=_("Yes"))
        button_yes.set_size_request(150, -1)
        button_yes.connect("clicked", lambda x: self.response(Gtk.ResponseType.YES))

        self.checkbox = Gtk.CheckButton(label=_("Also remove the prefix:"))
        self.checkbox.set_halign(Gtk.Align.CENTER)

        content_area = self.get_content_area()
        content_area.set_border_width(0)
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.pack_start(label, True, True, 0)
        if os.path.basename(prefix) != "default" and runner != "Linux-Native" and runner != "Steam":
            box_top.pack_start(self.checkbox, True, True, 0)
            box_top.pack_start(prefix_label, True, True, 0)
            if pfx_count > 0:
                box_top.pack_start(warn_label, True, True, 0)

        box_bottom.pack_start(button_no, True, True, 0)
        box_bottom.pack_start(button_yes, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        self.show_all()

class AddGame(Gtk.Dialog, HiDpiMixin):
    def __init__(self, parent, interface_mode):
        super().__init__(title=_("New Game/App"), parent=parent)
        self.set_modal(True)
        self.set_resizable(False)

        self.parent_window = parent
        self.interface_mode = interface_mode

        init_addon_defaults(self)

        if not os.path.exists(banners_dir):
            os.makedirs(banners_dir)

        self.banner_path_temp = os.path.join(banners_dir, "banner_temp.png")
        shutil.copyfile(faugus_banner, self.banner_path_temp)
        self.icon_directory = f"{icons_dir}/icon_temp/"

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        self.icons_path = icons_dir
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.ico'

        self.box = self.get_content_area()
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)
        self.content_area = self.get_content_area()
        self.content_area.set_border_width(0)
        self.content_area.set_halign(Gtk.Align.CENTER)
        self.content_area.set_valign(Gtk.Align.CENTER)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)

        box_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        self.grid_page1 = Gtk.Grid()
        self.grid_page1.set_column_homogeneous(True)
        self.grid_page1.set_column_spacing(10)
        self.grid_page2 = Gtk.Grid()
        self.grid_page2.set_column_homogeneous(True)
        self.grid_page2.set_column_spacing(10)

        self.grid_launcher = Gtk.Grid()
        self.grid_launcher.set_row_spacing(10)
        self.grid_launcher.set_column_spacing(10)
        self.grid_launcher.set_margin_start(10)
        self.grid_launcher.set_margin_end(10)
        self.grid_launcher.set_margin_top(10)

        self.grid_title = Gtk.Grid()
        self.grid_title.set_row_spacing(10)
        self.grid_title.set_column_spacing(10)
        self.grid_title.set_margin_start(10)
        self.grid_title.set_margin_end(10)
        self.grid_title.set_margin_top(10)

        self.grid_steam_title = Gtk.Grid()
        self.grid_steam_title.set_row_spacing(10)
        self.grid_steam_title.set_column_spacing(10)
        self.grid_steam_title.set_margin_start(10)
        self.grid_steam_title.set_margin_end(10)
        self.grid_steam_title.set_margin_top(10)

        self.grid_path = Gtk.Grid()
        self.grid_path.set_row_spacing(10)
        self.grid_path.set_column_spacing(10)
        self.grid_path.set_margin_start(10)
        self.grid_path.set_margin_end(10)
        self.grid_path.set_margin_top(10)

        self.grid_prefix = Gtk.Grid()
        self.grid_prefix.set_row_spacing(10)
        self.grid_prefix.set_column_spacing(10)
        self.grid_prefix.set_margin_start(10)
        self.grid_prefix.set_margin_end(10)
        self.grid_prefix.set_margin_top(10)

        self.grid_runner = Gtk.Grid()
        self.grid_runner.set_row_spacing(10)
        self.grid_runner.set_column_spacing(10)
        self.grid_runner.set_margin_start(10)
        self.grid_runner.set_margin_end(10)
        self.grid_runner.set_margin_top(10)

        self.grid_shortcut = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.grid_shortcut.set_row_spacing(10)
        self.grid_shortcut.set_column_spacing(10)
        self.grid_shortcut.set_margin_start(10)
        self.grid_shortcut.set_margin_end(10)
        self.grid_shortcut.set_margin_top(10)
        self.grid_shortcut.set_margin_bottom(10)

        self.grid_shortcut_icon = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.grid_shortcut_icon.set_row_spacing(10)
        self.grid_shortcut_icon.set_column_spacing(10)
        self.grid_shortcut_icon.set_margin_start(10)
        self.grid_shortcut_icon.set_margin_end(10)
        self.grid_shortcut_icon.set_margin_top(10)
        self.grid_shortcut_icon.set_margin_bottom(10)

        self.grid_protonfix = Gtk.Grid()
        self.grid_protonfix.set_row_spacing(10)
        self.grid_protonfix.set_column_spacing(10)
        self.grid_protonfix.set_margin_start(10)
        self.grid_protonfix.set_margin_end(10)
        self.grid_protonfix.set_margin_top(10)

        self.grid_launch_arguments = Gtk.Grid()
        self.grid_launch_arguments.set_row_spacing(10)
        self.grid_launch_arguments.set_column_spacing(10)
        self.grid_launch_arguments.set_margin_start(10)
        self.grid_launch_arguments.set_margin_end(10)
        self.grid_launch_arguments.set_margin_top(10)

        self.grid_game_arguments = Gtk.Grid()
        self.grid_game_arguments.set_row_spacing(10)
        self.grid_game_arguments.set_column_spacing(10)
        self.grid_game_arguments.set_margin_start(10)
        self.grid_game_arguments.set_margin_end(10)
        self.grid_game_arguments.set_margin_top(10)

        self.grid_lossless = Gtk.Grid()
        self.grid_lossless.set_row_spacing(10)
        self.grid_lossless.set_column_spacing(10)
        self.grid_lossless.set_margin_start(10)
        self.grid_lossless.set_margin_end(10)
        self.grid_lossless.set_margin_top(10)

        self.grid_addapp = Gtk.Grid()
        self.grid_addapp.set_row_spacing(10)
        self.grid_addapp.set_column_spacing(10)
        self.grid_addapp.set_margin_start(10)
        self.grid_addapp.set_margin_end(10)
        self.grid_addapp.set_margin_top(10)

        self.grid_tools = Gtk.Grid()
        self.grid_tools.set_row_spacing(10)
        self.grid_tools.set_column_spacing(10)
        self.grid_tools.set_margin_start(10)
        self.grid_tools.set_margin_end(10)
        self.grid_tools.set_margin_top(10)
        self.grid_tools.set_margin_bottom(10)

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        .combobox {
            border: 1px solid red;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.combobox_launcher = Gtk.ComboBoxText()

        self.label_steam_title = Gtk.Label(label=_("Title"))
        self.label_steam_title.set_halign(Gtk.Align.START)
        self.combobox_steam_title = Gtk.ComboBoxText()

        FILTER_KEYWORDS = [
            "Proton",
            "Steam Linux Runtime",
            "Steamworks Common Redistributables",
        ]

        for appid, name in read_installed_games():
            lname = name.lower()
            if any(keyword.lower() in lname for keyword in FILTER_KEYWORDS):
                continue

            self.combobox_steam_title.append(appid, name)

        self.label_title = Gtk.Label(label=_("Title"))
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", on_entry_changed, self.entry_title)
        if interface_mode == "Banners":
            self.entry_title.connect("focus-out-event", self.on_entry_focus_out)
        self.entry_title.set_tooltip_text(_("Game Title"))
        self.entry_title.set_has_tooltip(True)
        self.entry_title.connect("query-tooltip", on_entry_query_tooltip)

        self.label_path = Gtk.Label(label=_("Path"))
        self.label_path.set_halign(Gtk.Align.START)
        self.entry_path = Gtk.Entry()
        self.entry_path.connect("changed", on_entry_changed, self.entry_path)
        self.entry_path.set_tooltip_text(_("/path/to/the/exe"))
        self.entry_path.set_has_tooltip(True)
        self.entry_path.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search = Gtk.Button()
        self.button_search.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search.connect("clicked", self.on_button_search_clicked)
        self.button_search.set_size_request(50, -1)

        self.label_prefix = Gtk.Label(label=_("Prefix"))
        self.label_prefix.set_halign(Gtk.Align.START)
        self.entry_prefix = Gtk.Entry()
        self.entry_prefix.connect("changed", on_entry_changed, self.entry_prefix)
        self.entry_prefix.set_tooltip_text(_("/path/to/the/prefix"))
        self.entry_prefix.set_has_tooltip(True)
        self.entry_prefix.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        self.label_runner = Gtk.Label(label=_("Proton"))
        self.label_runner.set_halign(Gtk.Align.START)
        self.combobox_runner = Gtk.ComboBoxText()

        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.entry_protonfix.set_has_tooltip(True)
        self.entry_protonfix.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_image(
            Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_protonfix.connect("clicked", on_button_search_protonfix_clicked)
        self.button_search_protonfix.set_size_request(50, -1)

        self.label_game_arguments = Gtk.Label(label=_("Game Arguments"))
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text(_("e.g.: -d3d11 -fullscreen"))
        self.entry_game_arguments.set_has_tooltip(True)
        self.entry_game_arguments.connect("query-tooltip", on_entry_query_tooltip)

        self.button_launch_arguments = Gtk.Button(label=_("Launch Arguments"))
        self.button_launch_arguments.connect("clicked", self.on_button_launch_arguments_clicked)
        self.button_launch_arguments.set_tooltip_text(_("e.g.: PROTON_USE_WINED3D=1 gamescope -W 2560 -H 1440"))

        self.button_addapp = Gtk.Button(label=_("Additional Application"))
        self.button_addapp.connect("clicked", self.on_button_addapp_clicked)
        self.button_addapp.set_tooltip_text(
            _("Additional application to run with the game, like Cheat Engine, Trainers, Mods..."))

        self.button_lossless = Gtk.Button(label=_("Lossless Scaling Frame Generation"))
        self.button_lossless.connect("clicked", self.on_button_lossless_clicked)

        create_mangohud_gamemode_checkboxes(self)
        self.checkbox_disable_hidraw = Gtk.CheckButton(label=_("Disable Hidraw"))
        self.checkbox_prevent_sleep = Gtk.CheckButton(label=_("Prevent Sleep"))

        self.button_winecfg = Gtk.Button(label="Winecfg")
        self.button_winecfg.set_size_request(120, -1)
        self.button_winecfg.connect("clicked", self.on_button_winecfg_clicked)

        self.button_winetricks = Gtk.Button(label="Winetricks")
        self.button_winetricks.set_size_request(120, -1)
        self.button_winetricks.connect("clicked", self.on_button_winetricks_clicked)

        self.button_run = Gtk.Button(label=_("Run"))
        self.button_run.set_size_request(120, -1)
        self.button_run.connect("clicked", self.on_button_run_clicked)
        self.button_run.set_tooltip_text(_("Run a file inside the prefix"))

        self.label_shortcut = Gtk.Label(label=_("Shortcut"))
        self.label_shortcut.set_margin_start(10)
        self.label_shortcut.set_margin_end(10)
        self.label_shortcut.set_margin_top(10)
        self.label_shortcut.set_halign(Gtk.Align.START)
        self.checkbox_shortcut_desktop = Gtk.CheckButton(label=_("Desktop"))
        self.checkbox_shortcut_desktop.set_tooltip_text(
            _("Add or remove a shortcut from the Desktop."))
        self.checkbox_shortcut_appmenu = Gtk.CheckButton(label=_("App Menu"))
        self.checkbox_shortcut_appmenu.set_tooltip_text(
            _("Add or remove a shortcut from the Application Menu."))
        self.checkbox_shortcut_steam = Gtk.CheckButton(label=_("Steam"))
        self.checkbox_shortcut_steam.set_tooltip_text(
            _("Add or remove a shortcut from Steam. Steam needs to be restarted."))

        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_size_request(120, -1)
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)
        self.button_shortcut_icon.set_tooltip_text(_("Select an icon for the shortcut"))

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        self.button_cancel.set_size_request(150, -1)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        self.button_ok.set_size_request(150, -1)

        self.load_config()

        self.entry_title.connect("changed", self.update_prefix_entry)

        self.notebook = Gtk.Notebook()
        self.notebook.set_margin_start(10)
        self.notebook.set_margin_end(10)
        self.notebook.set_margin_top(10)
        self.notebook.set_margin_bottom(10)

        self.box.add(self.notebook)

        self.image_banner = Gtk.Image()
        self.image_banner.set_margin_top(10)
        self.image_banner.set_margin_bottom(10)
        self.image_banner.set_margin_start(10)
        self.image_banner.set_margin_end(10)
        self.image_banner.set_vexpand(True)
        self.image_banner.set_valign(Gtk.Align.CENTER)

        self.image_banner2 = Gtk.Image()
        self.image_banner2.set_margin_top(10)
        self.image_banner2.set_margin_bottom(10)
        self.image_banner2.set_margin_start(10)
        self.image_banner2.set_margin_end(10)
        self.image_banner2.set_vexpand(True)
        self.image_banner2.set_valign(Gtk.Align.CENTER)

        event_box = Gtk.EventBox()
        event_box.add(self.image_banner)
        event_box.connect("button-press-event", self.on_image_clicked)

        event_box2 = Gtk.EventBox()
        event_box2.add(self.image_banner2)
        event_box2.connect("button-press-event", self.on_image_clicked)

        self.menu = Gtk.Menu()

        refresh_item = Gtk.MenuItem(label=_("Refresh"))
        refresh_item.connect("activate", self.on_refresh)
        self.menu.append(refresh_item)

        load_item = Gtk.MenuItem(label=_("Load from file"))
        load_item.connect("activate", self.on_load_file)
        self.menu.append(load_item)

        load_url = Gtk.MenuItem(label=_("Load from URL"))
        load_url.connect("activate", self.on_load_url)
        self.menu.append(load_url)

        self.menu.show_all()

        page1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.tab_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label1 = Gtk.Label(label=_("Game/App"))
        tab_label1.set_width_chars(8)
        tab_label1.set_xalign(0.5)
        self.tab_box1.pack_start(tab_label1, True, True, 0)
        self.tab_box1.set_hexpand(True)

        self.grid_page1.attach(page1, 0, 0, 1, 1)
        if interface_mode == "Banners":
            self.grid_page1.attach(event_box, 1, 0, 1, 1)
        page1.set_hexpand(True)
        event_box.set_hexpand(True)

        self.notebook.append_page(self.grid_page1, self.tab_box1)

        page2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.tab_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label2 = Gtk.Label(label=_("Tools"))
        tab_label2.set_width_chars(8)
        tab_label2.set_xalign(0.5)
        self.tab_box2.pack_start(tab_label2, True, True, 0)
        self.tab_box2.set_hexpand(True)

        self.grid_page2.attach(page2, 0, 0, 1, 1)
        if interface_mode == "Banners":
            self.grid_page2.attach(event_box2, 1, 0, 1, 1)
        page2.set_hexpand(True)
        event_box2.set_hexpand(True)

        self.notebook.append_page(self.grid_page2, self.tab_box2)

        self.grid_launcher.attach(self.combobox_launcher, 1, 0, 1, 1)
        self.combobox_launcher.set_hexpand(True)
        self.combobox_launcher.set_valign(Gtk.Align.CENTER)

        self.grid_steam_title.attach(self.label_steam_title, 0, 0, 4, 1)
        self.grid_steam_title.attach(self.combobox_steam_title, 0, 1, 4, 1)
        self.combobox_steam_title.set_hexpand(True)

        self.grid_title.attach(self.label_title, 0, 0, 4, 1)
        self.grid_title.attach(self.entry_title, 0, 1, 4, 1)
        self.entry_title.set_hexpand(True)

        self.grid_path.attach(self.label_path, 0, 0, 1, 1)
        self.grid_path.attach(self.entry_path, 0, 1, 3, 1)
        self.entry_path.set_hexpand(True)
        self.grid_path.attach(self.button_search, 3, 1, 1, 1)

        self.grid_prefix.attach(self.label_prefix, 0, 0, 1, 1)
        self.grid_prefix.attach(self.entry_prefix, 0, 1, 3, 1)
        self.entry_prefix.set_hexpand(True)
        self.grid_prefix.attach(self.button_search_prefix, 3, 1, 1, 1)

        self.grid_runner.attach(self.label_runner, 0, 0, 1, 1)
        self.grid_runner.attach(self.combobox_runner, 0, 1, 1, 1)
        self.combobox_runner.set_hexpand(True)

        self.label_shortcut.set_hexpand(True)
        self.grid_shortcut.add(self.checkbox_shortcut_desktop)
        self.grid_shortcut.add(self.checkbox_shortcut_appmenu)
        self.grid_shortcut.add(self.checkbox_shortcut_steam)
        self.grid_shortcut_icon.add(self.button_shortcut_icon)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)

        self.box_shortcut = Gtk.Box()
        self.box_shortcut.pack_start(self.grid_shortcut, False, False, 0)
        self.box_shortcut.pack_end(self.grid_shortcut_icon, False, False, 0)

        page1.add(self.grid_launcher)
        page1.add(self.grid_steam_title)
        page1.add(self.grid_title)
        page1.add(self.grid_path)
        page1.add(self.grid_prefix)
        page1.add(self.grid_runner)
        page1.add(self.label_shortcut)
        page1.add(self.box_shortcut)

        self.grid_protonfix.attach(self.label_protonfix, 0, 0, 1, 1)
        self.grid_protonfix.attach(self.entry_protonfix, 0, 1, 3, 1)
        self.entry_protonfix.set_hexpand(True)
        self.grid_protonfix.attach(self.button_search_protonfix, 3, 1, 1, 1)

        self.grid_game_arguments.attach(self.label_game_arguments, 0, 0, 4, 1)
        self.grid_game_arguments.attach(self.entry_game_arguments, 0, 1, 4, 1)
        self.entry_game_arguments.set_hexpand(True)

        self.grid_lossless.attach(self.button_lossless, 0, 0, 1, 1)
        self.button_lossless.set_hexpand(True)

        self.grid_launch_arguments.attach(self.button_launch_arguments, 0, 0, 1, 1)
        self.button_launch_arguments.set_hexpand(True)

        self.grid_addapp.attach(self.button_addapp, 0, 0, 1, 1)
        self.button_addapp.set_hexpand(True)

        box_buttons.pack_start(self.button_winetricks, True, True, 0)
        box_buttons.pack_start(self.button_winecfg, True, True, 0)
        box_buttons.pack_start(self.button_run, True, True, 0)

        self.grid_tools.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        self.checkbox_gamemode.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_prevent_sleep, 0, 2, 1, 1)
        self.checkbox_prevent_sleep.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_disable_hidraw, 0, 3, 1, 1)
        self.checkbox_disable_hidraw.set_hexpand(True)
        self.grid_tools.attach(box_buttons, 2, 0, 1, 4)

        page2.add(self.grid_protonfix)
        page2.add(self.grid_game_arguments)
        page2.add(self.grid_launch_arguments)
        page2.add(self.grid_addapp)
        page2.add(self.grid_lossless)
        page2.add(self.grid_tools)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)
        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        bottom_box.pack_start(self.button_cancel, True, True, 0)
        bottom_box.pack_start(self.button_ok, True, True, 0)

        self.box.add(bottom_box)

        self.populate_combobox_with_launchers()
        self.combobox_launcher.set_active_id("windows")
        self.combobox_launcher.connect("changed", self.on_combobox_changed)

        self.populate_combobox_with_runners()

        model = self.combobox_runner.get_model()
        index_to_activate = 0

        self.default_runner = convert_runner(self.default_runner)

        for i, row in enumerate(model):
            if row[0] == self.default_runner:
                index_to_activate = i
                break
        self.combobox_runner.set_active(index_to_activate)

        self.checkbox_mangohud.set_active(self.default_mangohud)
        self.checkbox_gamemode.set_active(self.default_gamemode)
        self.checkbox_prevent_sleep.set_active(self.default_prevent_sleep)
        self.checkbox_disable_hidraw.set_active(self.default_disable_hidraw)

        disable_mangohud_gamemode_if_missing(self)

        if not detect_steam_id():
            self.checkbox_shortcut_steam.set_sensitive(False)
            self.checkbox_shortcut_steam.set_tooltip_text(
                _("Add or remove a shortcut from Steam. Steam needs to be restarted. NO STEAM USERS FOUND."))

        self.lossless_location = ConfigManager().config.get('lossless-location', '')
        if os.path.exists(lsfgvk_path):
            if lossless_dll or os.path.exists(self.lossless_location):
                self.button_lossless.set_sensitive(True)
            else:
                self.button_lossless.set_sensitive(False)
                self.button_lossless.set_tooltip_text(_("Lossless.dll NOT FOUND. If it's installed, go to Faugus Launcher's settings and set the location."))
        else:
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Lossless Scaling Vulkan Layer NOT INSTALLED."))

        self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())

        self.tab_box1.show_all()
        self.tab_box2.show_all()
        self.show_all()
        self.grid_steam_title.set_visible(False)
        if interface_mode != "Banners":
            self.image_banner.set_visible(False)
            self.image_banner2.set_visible(False)
        surface = self.new_surface_from_image(self.banner_path_temp, 260, 390, True)
        self.image_banner.set_from_surface(surface)
        self.image_banner2.set_from_surface(surface)

    def on_combobox_steam_changed(self, combobox):
        self.combobox_steam_title.get_style_context().remove_class("combobox")

        title = self.combobox_steam_title.get_active_text()
        steamid = self.combobox_steam_title.get_active_id()

        if not title or not steamid:
            return

        self.entry_title.set_text(title)
        self.entry_path.set_text(steamid)

        icon_path = get_steam_icon_path(steamid)
        if not icon_path:
            icon_path = faugus_png

        self.on_entry_focus_out(self.entry_title, None)

        shutil.copyfile(icon_path, os.path.expanduser(self.icon_temp))
        surface = self.new_surface_from_image(self.icon_temp, 50, 50)
        image = Gtk.Image.new_from_surface(surface)
        self.button_shortcut_icon.set_image(image)

    def on_button_launch_arguments_clicked(self, widget):
        self.launch_arguments = show_launch_arguments_dialog(self, presets_file, self.launch_arguments)

    def on_button_addapp_clicked(self, widget):
        (self.addapp_enabled, self.addapp,
         self.addapp_delay, self.addapp_first) = show_addapp_dialog(
            self, self.addapp_enabled, self.addapp,
            self.addapp_delay, self.addapp_first)

    def on_button_lossless_clicked(self, widget):
        (self.lossless_enabled, self.lossless_multiplier,
         self.lossless_flow, self.lossless_performance,
         self.lossless_hdr, self.lossless_present) = show_lossless_dialog(
            self, self.lossless_enabled, self.lossless_multiplier,
            self.lossless_flow, self.lossless_performance,
            self.lossless_hdr, self.lossless_present)

    def on_image_clicked(self, widget, event):
        self.menu.popup_at_pointer(event)

    def on_refresh(self, widget):
        if self.entry_title.get_text() != "":
            self.get_banner()
        else:
            shutil.copyfile(faugus_banner, self.banner_path_temp)
            self.update_image_banner()

    def on_load_file(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select an image for the banner"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        add_image_file_filters(filechooser, include_ico=False)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            file_path = filechooser.get_filename()
            if not file_path or not is_valid_image(file_path):
                show_invalid_image_dialog()
            else:
                shutil.copyfile(file_path, self.banner_path_temp)
                self.update_image_banner()

        filechooser.destroy()

    def on_load_url(self, widget):
        dialog = Gtk.Dialog(title=_("Enter the image URL"))
        dialog.set_modal(True)
        dialog.set_resizable(False)

        entry = Gtk.Entry()
        entry.set_tooltip_text("https://example.com/banner.png")

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(120, -1)
        button_ok.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.OK))

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.set_size_request(120, -1)
        button_cancel.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.CANCEL))

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(10)
        box_top.set_margin_end(10)
        box_top.set_margin_top(10)
        box_top.set_margin_bottom(10)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.pack_start(entry, False, False, 0)

        box_bottom.pack_start(button_cancel, True, True, 0)
        box_bottom.pack_start(button_ok, True, True, 0)

        dialog.get_content_area().add(box_top)
        dialog.get_content_area().add(box_bottom)

        dialog.show_all()

        while True:
            response = dialog.run()

            if response == Gtk.ResponseType.CANCEL:
                break

            if response == Gtk.ResponseType.OK:
                url = entry.get_text().strip().replace(" ", "%20")
                valid_exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg")

                if not url.lower().endswith(valid_exts):
                    show_invalid_image_dialog()
                    dialog.show_all()
                    continue

                try:
                    import urllib.request
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req) as r, open(self.banner_path_temp, "wb") as f:
                        f.write(r.read())

                    self.update_image_banner()
                    break

                except Exception:
                    show_invalid_image_dialog()
                    dialog.show_all()
                    continue

        dialog.destroy()

    def get_banner(self):
        import requests
        def fetch_banner():
            game_name = self.entry_title.get_text().strip()
            if not game_name:
                return

            api_url = f"https://steamgrid.usebottles.com/api/search/{game_name}"
            try:
                response = requests.get(api_url)
                response.raise_for_status()
                image_url = response.text.strip('"')

                with open(self.banner_path_temp, "wb") as image_file:
                    image_file.write(requests.get(image_url).content)

                GLib.idle_add(self.update_image_banner)

            except requests.RequestException as e:
                print(f"Error fetching the banner: {e}")

        # Start the thread
        threading.Thread(target=fetch_banner, daemon=True).start()

    def update_image_banner(self):
        surface = self.new_surface_from_image(self.banner_path_temp, 260, 390, True)
        self.image_banner.set_from_surface(surface)
        self.image_banner2.set_from_surface(surface)

    def on_entry_focus_out(self, entry_title, event):
        if entry_title.get_text() != "":
            self.get_banner()
        else:
            shutil.copyfile(faugus_banner, self.banner_path_temp)
            self.update_image_banner()

    def on_combobox_changed(self, combobox):
        active_id = combobox.get_active_id()

        def cleanup_fields():
            self.entry_title.set_text("")
            self.launch_arguments = ""
            self.entry_path.set_text("")
            self.entry_prefix.set_text("")
            self.checkbox_shortcut_desktop.set_active(False)
            self.checkbox_shortcut_appmenu.set_active(False)
            self.checkbox_shortcut_steam.set_active(False)
            self.entry_protonfix.set_text("")
            self.entry_game_arguments.set_text("")
            self.checkbox_mangohud.set_active(self.default_mangohud)
            self.checkbox_gamemode.set_active(self.default_gamemode)
            self.checkbox_disable_hidraw.set_active(self.default_disable_hidraw)
            self.checkbox_prevent_sleep.set_active(self.default_prevent_sleep)
            self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
            shutil.copyfile(faugus_banner, self.banner_path_temp)
            self.update_image_banner()

            for w in (self.combobox_steam_title, self.entry_title,
                      self.entry_prefix, self.entry_path):
                w.get_style_context().remove_class("entry")

        cleanup_fields()

        self.grid_title.set_visible(False)
        self.grid_steam_title.set_visible(False)
        self.grid_path.set_visible(False)
        self.grid_runner.set_visible(False)
        self.grid_prefix.set_visible(False)
        self.button_winetricks.set_visible(False)
        self.button_winecfg.set_visible(False)
        self.button_run.set_visible(False)
        self.grid_protonfix.set_visible(False)
        self.grid_addapp.set_visible(False)
        self.checkbox_disable_hidraw.set_visible(False)
        self.checkbox_prevent_sleep.set_visible(True)
        self.checkbox_shortcut_steam.set_visible(True)
        self.grid_page2.set_visible(True)
        self.tab_box2.set_visible(True)
        self.notebook.set_show_tabs(True)
        self.button_shortcut_icon.set_visible(True)

        if active_id == "windows":
            self.grid_title.set_visible(True)
            self.grid_path.set_visible(True)
            self.grid_runner.set_visible(True)
            self.grid_prefix.set_visible(True)
            self.button_winetricks.set_visible(True)
            self.button_winecfg.set_visible(True)
            self.button_run.set_visible(True)
            self.grid_protonfix.set_visible(True)
            self.grid_addapp.set_visible(True)
            self.checkbox_disable_hidraw.set_visible(True)
            self.button_shortcut_icon.set_visible(True)

        elif active_id == "linux":
            self.grid_title.set_visible(True)
            self.grid_path.set_visible(True)
            self.button_shortcut_icon.set_visible(True)

        elif active_id == "steam":
            self.grid_steam_title.set_visible(True)
            self.checkbox_shortcut_steam.set_visible(False)
            self.grid_page2.set_visible(False)
            self.tab_box2.set_visible(False)
            self.notebook.set_show_tabs(False)
            self.button_shortcut_icon.set_visible(True)

        else:
            self.grid_runner.set_visible(True)
            self.grid_prefix.set_visible(True)
            self.button_winetricks.set_visible(True)
            self.button_winecfg.set_visible(True)
            self.button_run.set_visible(True)
            self.grid_protonfix.set_visible(True)
            self.checkbox_disable_hidraw.set_visible(True)
            self.button_shortcut_icon.set_visible(False)

            self.entry_title.set_text(self.combobox_launcher.get_active_text())

            if active_id == "battle":
                self.launch_arguments = "WINE_SIMULATE_WRITECOPY=1\nPROTON_ENABLE_WAYLAND=0"
                path = "drive_c/Program Files (x86)/Battle.net/Battle.net.exe"

            elif active_id == "ea":
                self.launch_arguments = "PROTON_ENABLE_WAYLAND=0"
                path = "drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe"

            elif active_id == "epic":
                self.launch_arguments = "PROTON_ENABLE_WAYLAND=0"
                path = "drive_c/Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"

            elif active_id == "ubisoft":
                self.launch_arguments = "PROTON_ENABLE_WAYLAND=0"
                path = "drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/UbisoftConnect.exe"

            elif active_id == "rockstar":
                self.launch_arguments = "PROTON_ENABLE_WAYLAND=0"
                path = "drive_c/Program Files/Rockstar Games/Launcher/Launcher.exe"

            elif active_id == "wargaming":
                path = "drive_c/ProgramData/Wargaming.net/GameCenter/wgc.exe"

            else:
                path = ""

            if path:
                self.entry_path.set_text(f"{self.entry_prefix.get_text()}/{path}")

        if self.interface_mode == "Banners":
            if self.entry_title.get_text():
                self.get_banner()

    def populate_combobox_with_launchers(self):
        self.combobox_launcher.append("windows", _("Windows Game"))
        self.combobox_launcher.append("linux", _("Linux Game"))
        self.combobox_launcher.append("steam", _("Steam Game"))
        self.combobox_launcher.append("battle", "Battle.net")
        self.combobox_launcher.append("ea", "EA App")
        #self.combobox_launcher.append("epic", "Epic Games")
        self.combobox_launcher.append("rockstar", "Rockstar Launcher")
        self.combobox_launcher.append("ubisoft", "Ubisoft Connect")
        self.combobox_launcher.append("wargaming", "Wargaming Game Center")

    def populate_combobox_with_runners(self):
        populate_combobox_with_runners(self.combobox_runner)

    def load_config(self):
        cfg = ConfigManager()

        self.default_runner = cfg.config.get('default-runner', '')
        self.default_prefix = cfg.config.get('default-prefix', '')
        self.default_mangohud = cfg.config.get('mangohud') == 'True'
        self.default_gamemode = cfg.config.get('gamemode') == 'True'
        self.default_disable_hidraw = cfg.config.get('disable-hidraw') == 'True'
        self.default_prevent_sleep = cfg.config.get('prevent-sleep') == 'True'

    def on_button_run_clicked(self, widget):
        validation_result = self.validate_fields(entry="prefix")
        if not validation_result:
            return

        filechooser = Gtk.FileChooserNative(
            title=_("Select a file to run inside the prefix"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        add_windows_file_filters(filechooser)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            file_run = filechooser.get_filename()
            title = self.entry_title.get_text()
            prefix = self.entry_prefix.get_text()
            title_formatted = format_title(title)
            runner = self.combobox_runner.get_active_text()
            game_directory = os.path.dirname(file_run)
            cwd = game_directory if game_directory and os.path.isdir(game_directory) else None
            escaped_file_run = file_run.replace("'", "'\\''")
            runner = convert_runner(runner)
            command_parts = []

            if title_formatted:
                command_parts.append(f"LOG_DIR={title_formatted}")
            if prefix:
                command_parts.append(f"WINEPREFIX='{prefix}'")
            if runner:
                if runner == "Proton-CachyOS (System)":
                    command_parts.append(f"PROTONPATH='{proton_cachyos}'")
                else:
                    command_parts.append(f"PROTONPATH='{runner}'")
            if escaped_file_run.endswith(".reg"):
                command_parts.append(f"'{umu_run}' regedit '{escaped_file_run}'")
            else:
                command_parts.append(f"'{umu_run}' '{escaped_file_run}'")

            command = ' '.join(command_parts)
            cmd = (sys.executable, "-m", "faugus.runner", command)

            def run_command():
                process = subprocess.Popen(cmd, cwd=cwd if cwd else None)
                process.wait()

            command_thread = threading.Thread(target=run_command)
            command_thread.start()

        filechooser.destroy()

    def set_image_shortcut_icon(self):
        image_path = faugus_png
        shutil.copyfile(image_path, self.icon_temp)

        surface = self.new_surface_from_image(self.icon_temp, 50, 50)
        image = Gtk.Image.new_from_surface(surface)

        return image

    def on_button_shortcut_icon_clicked(self, widget):
        validation_result = self.validate_fields(entry="path")
        if not validation_result:
            return

        path = self.entry_path.get_text()

        if os.path.isfile(path):
            os.makedirs(self.icon_directory, exist_ok=True)
            status = extract_ico_simple(path, self.icon_converted)
            if status == "no_icons":
                self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())

        choose_shortcut_icon(self)

    def check_existing_shortcut(self):
        # Check if the shortcut already exists and mark or unmark the checkbox
        title = self.entry_title.get_text().strip()
        if not title:
            return  # If there's no title, there's no shortcut to check

        title_formatted = format_title(title)
        desktop_file_path = f"{desktop_dir}/{title_formatted}.desktop"
        applications_shortcut_path = f"{app_dir}/{title_formatted}.desktop"

        # Mark the checkbox if the shortcut exists
        self.checkbox_shortcut_desktop.set_active(os.path.exists(desktop_file_path))
        self.checkbox_shortcut_appmenu.set_active(os.path.exists(applications_shortcut_path))

    def update_prefix_entry(self, entry):
        # Update the prefix entry based on the title and self.default_prefix
        title_formatted = format_title(entry.get_text())
        prefix = os.path.expanduser(self.default_prefix) + "/" + title_formatted
        self.entry_prefix.set_text(prefix)

    def on_button_winecfg_clicked(self, widget):
        self.set_sensitive(False)
        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields(entry="prefix")
        if not validation_result:
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        prefix = self.entry_prefix.get_text()
        title_formatted = format_title(title)
        runner = self.combobox_runner.get_active_text()

        runner = convert_runner(runner)

        command_parts = []

        # Add command parts if they are not empty
        if title_formatted:
            command_parts.append(f"LOG_DIR='{title_formatted}'")
        if prefix:
            command_parts.append(f"WINEPREFIX='{prefix}'")
        if runner:
            if runner == "Proton-CachyOS (System)":
                command_parts.append(f"PROTONPATH='{proton_cachyos}'")
            else:
                command_parts.append(f"PROTONPATH='{runner}'")

        # Add the fixed command and remaining arguments
        command_parts.append(f"'{umu_run}'")
        command_parts.append("'winecfg'")

        # Join all parts into a single command
        command = ' '.join(command_parts)

        print(command)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent_window.set_sensitive, True)

        command_thread = threading.Thread(target=run_command)
        command_thread.start()

    def on_button_winetricks_clicked(self, widget):
        self.set_sensitive(False)
        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields(entry="prefix")
        if not validation_result:
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        prefix = self.entry_prefix.get_text()
        title_formatted = format_title(title)
        runner = self.combobox_runner.get_active_text()

        runner = convert_runner(runner)

        command_parts = []

        # Add command parts if they are not empty
        if title_formatted:
            command_parts.append(f"LOG_DIR={title_formatted}")
        if prefix:
            command_parts.append(f"WINEPREFIX='{prefix}'")
        command_parts.append(f"GAMEID=winetricks-gui")
        command_parts.append(f"STORE=none")
        if runner:
            if runner == "Proton-CachyOS (System)":
                command_parts.append(f"PROTONPATH='{proton_cachyos}'")
            else:
                command_parts.append(f"PROTONPATH='{runner}'")

        # Add the fixed command and remaining arguments
        command_parts.append(f"'{umu_run}'")
        command_parts.append("''")

        # Join all parts into a single command
        command = ' '.join(command_parts)

        print(command)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command, "winetricks"])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent_window.set_sensitive, True)

        command_thread = threading.Thread(target=run_command)
        command_thread.start()

    def on_button_search_clicked(self, widget):
        if not self.entry_path.get_text():
            initial_folder = os.path.expanduser("~/")
        else:
            initial_folder = os.path.dirname(self.entry_path.get_text())

        filechooser = Gtk.FileChooserNative(
            title=_("Select the game's .exe"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        filechooser.set_current_folder(initial_folder)

        if self.combobox_launcher.get_active_id() != "linux":
            add_windows_file_filters(filechooser)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            path = filechooser.get_filename()

            os.makedirs(self.icon_directory, exist_ok=True)

            status = extract_ico_frames(path, self.icon_temp)
            if status == "ok":
                surface = self.new_surface_from_image(self.icon_temp, 50, 50)
                self.button_shortcut_icon.set_image(Gtk.Image.new_from_surface(surface))
            elif status == "no_icons":
                self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())

            self.entry_path.set_text(path)

        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)

        filechooser.destroy()

    def on_button_search_prefix_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select a prefix location"),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        if not self.entry_prefix.get_text():
            filechooser.set_current_folder(os.path.expanduser(self.default_prefix))
        else:
            filechooser.set_current_folder(self.entry_prefix.get_text())

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            new_prefix = filechooser.get_filename()
            self.default_prefix = new_prefix
            self.entry_prefix.set_text(self.default_prefix)

        filechooser.destroy()

    def validate_fields(self, entry):
        # Validate the input fields for title, prefix and path
        title = self.entry_title.get_text()
        gameid = format_title(title)
        prefix = self.entry_prefix.get_text()
        path = self.entry_path.get_text()
        combobox_steam = self.combobox_steam_title.get_active_text()

        self.combobox_steam_title.get_style_context().remove_class("combobox")
        self.entry_title.get_style_context().remove_class("entry")
        self.entry_prefix.get_style_context().remove_class("entry")
        self.entry_path.get_style_context().remove_class("entry")

        if self.grid_steam_title.get_visible():
            if not combobox_steam:
                self.combobox_steam_title.get_style_context().add_class("combobox")
                self.notebook.set_current_page(0)

        if entry == "prefix":
            if not title or not prefix:
                if not title:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not prefix:
                    self.entry_prefix.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                return False

        if entry == "path":
            if not title or not path:
                if not title:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not path:
                    self.entry_path.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                return False

        if entry == "path+prefix":
            if not title or not path or not prefix or not gameid:
                if not title:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not path:
                    self.entry_path.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not prefix:
                    self.entry_prefix.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not gameid:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                return False

        return True

def run_file(file_path):
    cfg = ConfigManager()

    default_prefix = cfg.config.get('default-prefix', '').strip('"')
    mangohud = cfg.config.get('mangohud', 'False') == 'True'
    gamemode = cfg.config.get('gamemode', 'False') == 'True'
    disable_hidraw = cfg.config.get('disable-hidraw', 'False') == 'True'
    prevent_sleep = cfg.config.get('prevent-sleep', 'False') == 'True'
    default_runner = cfg.config.get('default-runner', '').strip('"')

    if file_path.endswith(".reg"):
        mangohud = False
        gamemode = False
        disable_hidraw = False
        prevent_sleep = False

    file_dir = os.path.dirname(os.path.abspath(file_path))
    command_parts = []

    if disable_hidraw:
        command_parts.append("PROTON_DISABLE_HIDRAW=1")
    if prevent_sleep:
        command_parts.append("PREVENT_SLEEP=1")
    command_parts.append(os.path.expanduser(f'WINEPREFIX="{default_prefix}/default"'))
    if default_runner:
        if default_runner == "Proton-CachyOS (System)":
            command_parts.append(f'PROTONPATH="{proton_cachyos}"')
        else:
            command_parts.append(f'PROTONPATH="{default_runner}"')
    if gamemode:
        command_parts.append("gamemoderun")
    if mangohud:
        command_parts.append("mangohud")
    command_parts.append(f'"{umu_run}"')
    if file_path.endswith(".reg"):
        command_parts.append(f'regedit "{file_path}"')
    else:
        command_parts.append(f'"{file_path}"')

    command = ' '.join(command_parts)
    subprocess.Popen([sys.executable, "-m", "faugus.runner", command], cwd=file_dir)

def main():
    start_hidden = "--hide" in sys.argv
    sys.argv = [arg for arg in sys.argv if arg != "--hide"]

    if len(sys.argv) == 2:
        run_file(sys.argv[1])
        sys.exit(0)

    app = FaugusApp(start_hidden)
    app.run(sys.argv)

# returns the number of other games using the same prefix
def prefixes_count(prefix):
    games = load_json_file(games_json, None)
    if games is None:
        return
    return sum(1 for x in games if x.get("prefix") == prefix) - 1

if __name__ == "__main__":
    update_games_json()
    main()
