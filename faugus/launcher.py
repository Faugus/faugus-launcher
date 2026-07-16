#!/usr/bin/python3

import shutil
import subprocess
import sys
import threading
import warnings
import gi
import vdf
import signal

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, GObject, Pango, Adw
from faugus.config_manager import *
from faugus.utils import *
from faugus.steam_setup import *
from faugus.ea_fix import *
from faugus.tray_sni import TrayIcon
from faugus.migration import fix_legacy_shortcut_icons

VERSION = "2.0.0"

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


os.makedirs(compatibility_dir, exist_ok=True)

faugus_backup = False

os.makedirs(faugus_launcher_share_dir, exist_ok=True)
os.makedirs(faugus_launcher_dir, exist_ok=True)
os.makedirs(faugus_launcher_state_dir, exist_ok=True)
fix_legacy_shortcut_icons()

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


class FaugusApp(Adw.Application):
    def __init__(self, start_hidden=False):
        super().__init__(application_id="io.github.Faugus.faugus-launcher")
        self.window = None
        self.start_hidden = start_hidden

    def do_startup(self):
        Adw.Application.do_startup(self)

        app_icon_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "assets"
        )
        app_icon_dir = os.path.normpath(app_icon_dir)
        if os.path.isdir(app_icon_dir):
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(app_icon_dir)

        cfg = ConfigManager()
        apply_interface_customization(
            cfg.config.get('interface-theme', 'system'),
            cfg.config.get('accent-color', 'system'),
        )

    def do_activate(self):
        if not self.window:
            self.window = Main(self)

            if self.start_hidden:
                self.window.set_visible(False)
                return

        self.window.present()


class Main(Gtk.ApplicationWindow, HiDpiMixin):
    def __init__(self, app):
        super().__init__(application=app, title="Faugus")
        self.add_css_class("main-window")
        self.connect("close-request", self.on_close)
        print(f"Faugus {VERSION}")

        self.fullscreen_activated = False
        self.system_tray = False
        self.tray_icon = None
        self.mono_icon = False

        self.current_prefix = None
        self.games = []

        self.processes = {}

        if not os.path.exists(running_games):
            save_json_file({}, running_games)

        self.running = load_json_file(running_games, {})
        if not isinstance(self.running, dict):
            self.running = {}

        add_css_once("main_window", """
            .game {
                background-color: @theme_base_color;
                color: @theme_text_color;
            }
            flowboxchild:not(.banner-container) {
                background: transparent;
                border: none;
                outline: none;
                box-shadow: none;
            }
            flowboxchild:not(.banner-container):focus,
            flowboxchild:not(.banner-container):selected,
            flowboxchild:not(.banner-container):focus-within {
                background: transparent;
                border: none;
                outline: none;
                box-shadow: none;
            }
            flowboxchild:selected:not(.banner-container) .game {
                background-color: alpha(@theme_selected_bg_color, 0.5);
            }
            flowboxchild:selected:focus:not(.banner-container) .game {
                background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color;
            }
            .category-list row:selected {
                background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color;
            }
            .envar-list:selected {
                background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color;
            }
            flowboxchild.banner-container {
                border: 4px solid transparent;
                border-radius: 12px;
                padding: 0px;
                transition: transform 200ms cubic-bezier(0.25, 0.46, 0.45, 0.94),
                            border-color 200ms ease;
            }
            flowboxchild.banner-container:selected {
                transform: scale(1.05);
                border-color: alpha(@theme_selected_bg_color, 0.5);
                box-shadow: 0 0 25px 5px alpha(@theme_selected_bg_color, 0.3);
            }
            flowboxchild.banner-container:selected:focus {
                border-color: @theme_selected_bg_color;
            }
            .banner-placeholder,
            .hero-placeholder {
                background-color: alpha(@accent_bg_color, 0.4);
            }
            .banner-placeholder {
                border-radius: 12px;
            }
            .spinner-dim-overlay {
                background-color: alpha(black, 0.3);
            }
            .spinner-dim-overlay-banner {
                border-radius: 12px;
            }
            .spinner-dim-overlay-icon {
                border-radius: 8px;
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
            .accent-background {
                background-color: alpha(@accent_bg_color, 0.2);
            }
        """, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        load_frame_css()

        self.context_menu = Gtk.Popover()
        self.context_menu.set_has_arrow(False)
        self.context_menu.set_autohide(True)
        context_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        context_box.set_margin_start(6)
        context_box.set_margin_end(6)
        context_box.set_margin_top(6)
        context_box.set_margin_bottom(6)
        self.context_menu.set_child(context_box)

        self.menu_title = Gtk.Label(label="")
        self.menu_title.set_halign(Gtk.Align.START)
        self.menu_title.add_css_class("heading")
        self.menu_title.set_margin_bottom(4)
        context_box.append(self.menu_title)

        self.menu_playtime = Gtk.Label(label="")
        self.menu_playtime.set_halign(Gtk.Align.START)
        self.menu_playtime.set_margin_bottom(4)
        context_box.append(self.menu_playtime)

        context_box.append(Gtk.Separator())

        def context_menu_button(label):
            btn = Gtk.Button(label=label)
            btn.set_has_frame(False)
            btn.get_child().set_halign(Gtk.Align.START)
            context_box.append(btn)
            return btn

        self.menu_play = context_menu_button(_("Play"))
        self.menu_play.connect("clicked", self.on_context_menu_play)

        self.menu_edit = context_menu_button(_("Edit"))
        self.menu_edit.connect("clicked", self.on_context_menu_edit)

        self.menu_delete = context_menu_button(_("Delete"))
        self.menu_delete.connect("clicked", self.on_context_menu_delete)

        self.menu_duplicate = context_menu_button(_("Duplicate"))
        self.menu_duplicate.connect("clicked", self.on_context_menu_duplicate)

        self.menu_hide = context_menu_button(_("Hide"))
        self.menu_hide.connect("clicked", self.on_context_menu_hide)

        self.menu_category = context_menu_button(_("Category"))
        self.submenu_category = Gtk.Popover()
        self.submenu_category.set_parent(self.menu_category)
        self.submenu_category_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.submenu_category_box.set_margin_start(6)
        self.submenu_category_box.set_margin_end(6)
        self.submenu_category_box.set_margin_top(6)
        self.submenu_category_box.set_margin_bottom(6)
        self.submenu_category.set_child(self.submenu_category_box)

        def on_category_button_clicked(widget):
            if self.gamepad_navigation:
                self.active_popover = self.submenu_category
            self.submenu_category.popup()

        self.menu_category.connect("clicked", on_category_button_clicked)

        self.menu_game_location = context_menu_button(_("Open game location"))
        self.menu_game_location.connect("clicked", self.on_context_menu_game_location)

        self.menu_prefix_location = context_menu_button(_("Open prefix location"))
        self.menu_prefix_location.connect("clicked", self.on_context_menu_prefix_location)

        self.menu_run = context_menu_button(_("Run file inside the prefix"))
        self.menu_run.connect("clicked", self.on_context_menu_run)

        self.menu_show_logs = context_menu_button(_("Show logs"))
        self.menu_show_logs.connect("clicked", self.on_context_show_logs)

        self.load_config()

        if self.interface_mode == "List":
            self.setup_interface()
        if self.interface_mode in ("Blocks", "Banners", "SteamGridDB"):
            if self.window_behavior == "Maximized":
                self.maximize()
            if self.window_behavior == "Fullscreen":
                self.fullscreen()
                self.fullscreen_activated = True
            self.setup_interface(True)
        if not self.interface_mode:
            self.interface_mode = "List"
            self.setup_interface()

        right_click = Gtk.GestureClick()
        right_click.set_button(Gdk.BUTTON_SECONDARY)

        def on_right_click(gesture, n_press, x, y):
            item = self.flowbox.get_child_at_pos(int(x), int(y))
            self.on_item_right_click(item, x, y)

        right_click.connect("pressed", on_right_click)
        self.flowbox.add_controller(right_click)
        def on_selected_children_changed(*_):
            GLib.idle_add(self.update_icon)
            GLib.idle_add(self.schedule_background_update)

        self.flowbox.connect("selected-children-changed", on_selected_children_changed)

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

        self.button_play.set_child(new_icon_image(f"{icon}.svg"))
        self.menu_play.get_child().set_text(text)

        if IS_FLATPAK:
            self.button_play.set_sensitive(not is_running)
            self.menu_play.set_sensitive(not is_running)

    def selected(self):
        selected_items = self.flowbox.get_selected_children()
        if not selected_items:
            return None
        return getattr(selected_items[0], 'game', None)

    def hero_overlay_enabled(self):
        return self.interface_mode == "SteamGridDB" and self.hero_enabled

    def get_named_rgb(self, name, fallback=(30, 30, 34)):
        found, rgba = Gtk.Box().get_style_context().lookup_color(name)
        if not found:
            return fallback
        return (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))

    def build_background_container(self, content_widget):
        base_mode = self.background_mode
        show_hero = self.hero_overlay_enabled()

        if not show_hero and base_mode != "dominant_color":
            if base_mode == "accent":
                content_widget.add_css_class("accent-background")
            return content_widget

        overlay = Gtk.Overlay()

        base_box = Gtk.Box()
        base_box.set_hexpand(True)
        base_box.set_vexpand(True)
        if base_mode == "accent":
            base_box.add_css_class("accent-background")
        overlay.set_child(base_box)

        self.hero_stack = Gtk.Stack()
        self.hero_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.hero_stack.set_transition_duration(150)
        self.hero_stack.set_hexpand(True)
        self.hero_stack.set_vexpand(True)

        self._hero_pages = []
        self._hero_color_providers = []
        self._hero_image_providers = []

        for i in range(2):
            page = Gtk.Overlay()

            color_box = Gtk.Box()
            color_box.set_hexpand(True)
            color_box.set_vexpand(True)
            color_box.add_css_class(f"hero-bg-color-{i}")
            page.set_child(color_box)

            hero_image_box = None
            if show_hero:
                hero_image_box = Gtk.Box()
                hero_image_box.set_hexpand(True)
                hero_image_box.set_vexpand(False)
                hero_image_box.set_halign(Gtk.Align.FILL)
                hero_image_box.set_valign(Gtk.Align.START)
                hero_image_box.add_css_class(f"hero-bg-image-{i}")
                page.add_overlay(hero_image_box)
                page.set_measure_overlay(hero_image_box, False)

            color_provider = Gtk.CssProvider()
            color_box.get_style_context().add_provider(color_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            image_provider = Gtk.CssProvider()
            if hero_image_box is not None:
                hero_image_box.get_style_context().add_provider(image_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

            page.color_box = color_box
            page.hero_image_box = hero_image_box

            self._hero_pages.append(page)
            self._hero_color_providers.append(color_provider)
            self._hero_image_providers.append(image_provider)

            self.hero_stack.add_named(page, f"hero-{i}")

        self._hero_page_index = 0
        self.hero_stack.set_visible_child(self._hero_pages[0])

        overlay.add_overlay(self.hero_stack)
        overlay.set_measure_overlay(self.hero_stack, False)

        overlay.add_overlay(content_widget)
        overlay.set_measure_overlay(content_widget, True)
        return overlay

    def schedule_background_update(self):
        if getattr(self, 'hero_stack', None) is None:
            return

        if getattr(self, '_hero_update_source', None):
            GLib.source_remove(self._hero_update_source)

        def fire():
            self._hero_update_source = None
            self.update_background()
            return False

        self._hero_update_source = GLib.timeout_add(120, fire)

    def update_background(self):
        hero_stack = getattr(self, 'hero_stack', None)
        base_mode = self.background_mode
        show_hero = self.hero_overlay_enabled()
        if hero_stack is None or (not show_hero and base_mode != "dominant_color"):
            return

        def apply():
            game = self.selected()
            color_css = ""
            hero_css = ""

            next_index = 1 - self._hero_page_index
            page = self._hero_pages[next_index]
            color_box = page.color_box
            hero_image_box = page.hero_image_box
            color_class = f"hero-bg-color-{next_index}"
            image_class = f"hero-bg-image-{next_index}"

            if game:
                if base_mode == "dominant_color":
                    if self.interface_mode in ("Banners", "SteamGridDB"):
                        color_source = f"{banners_dir}/{game.gameid}.png"
                    else:
                        color_source = f"{icons_dir}/{game.gameid}.png"
                    if os.path.isfile(color_source):
                        r, g, b = get_dominant_color(color_source)
                        color_css = f".{color_class} {{ background-color: rgba({r}, {g}, {b}, 0.2); }}"

                if show_hero and hero_image_box is not None:
                    candidate = f"{heroes_dir}/{game.gameid}.png"
                    if os.path.isfile(candidate):
                        hero_uri = Gio.File.new_for_path(candidate).get_uri()

                        window_r, window_g, window_b = self.get_named_rgb("window_bg_color")
                        if base_mode == "dominant_color" and color_css:
                            fade_r = int(window_r * 0.8 + r * 0.2)
                            fade_g = int(window_g * 0.8 + g * 0.2)
                            fade_b = int(window_b * 0.8 + b * 0.2)
                        elif base_mode == "accent":
                            ar, ag, ab = self.get_named_rgb("accent_bg_color")
                            fade_r = int(window_r * 0.8 + ar * 0.2)
                            fade_g = int(window_g * 0.8 + ag * 0.2)
                            fade_b = int(window_b * 0.8 + ab * 0.2)
                        else:
                            fade_r, fade_g, fade_b = window_r, window_g, window_b

                        container_width = hero_image_box.get_width() or self.get_width() or 800
                        hero_height = int(container_width * 620 / 1920)
                        hero_image_box.set_size_request(-1, hero_height)

                        hero_css = f"""
                        .{image_class} {{
                            background-image: linear-gradient(to bottom, rgba({fade_r}, {fade_g}, {fade_b}, 0) 0%, rgba({fade_r}, {fade_g}, {fade_b}, 1) 100%), url("{hero_uri}");
                            background-repeat: no-repeat, no-repeat;
                            background-position: center, center;
                            background-size: 100% 100%, 100% 100%;
                        }}
                        """
                    elif hero_image_box is not None:
                        hero_image_box.set_size_request(-1, -1)

            self._hero_color_providers[next_index].load_from_data(color_css.encode("utf-8"))
            self._hero_image_providers[next_index].load_from_data(hero_css.encode("utf-8"))

            hero_stack.set_visible_child(page)
            self._hero_page_index = next_index
            return False

        GLib.idle_add(apply)

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
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

        if not self.system_tray:
            return

        self.tray_icon = TrayIcon(
            mono_icon=self.mono_icon,
            on_present=self.restore_window,
            on_quit=self.on_quit,
            on_launch=self.on_tray_launch,
        )
        self.tray_icon.start()

    def on_tray_launch(self, gameid):
        game = next((g for g in self.games if g.gameid == gameid), None)
        if not game:
            return
        if game.gameid in self.running:
            self.running_dialog(game.title)
        else:
            self.on_button_play_clicked(None, game)

    def save_interface_settings(self):
        config = ConfigManager()

        if self.window_behavior == "Remember":
            config.set_value("width", self.get_width())
            config.set_value("height", self.get_height())

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
            self.set_visible(False)
            return True

        self.on_quit()
        return False

    def restore_window(self, *_):
        self.set_visible(True)
        self.present()

    def on_quit(self, *_):
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.get_application().quit()

    def _focus_flowbox_child_at(self, index):
        self.set_focus(None)
        for _ in range(index + 1):
            if not self.flowbox.child_focus(Gtk.DirectionType.TAB_FORWARD):
                break
        focused = self.flowbox.get_focus_child()
        if focused is not None:
            self.flowbox.select_child(focused)

    def select_first_child(self):
        visible_children = [c for c in widget_children(self.flowbox) if c.get_child_visible()]
        if visible_children:
            self._focus_flowbox_child_at(0)

    def select_game_by_title(self, title):
        def do_select():
            visible_children = [c for c in widget_children(self.flowbox) if c.get_child_visible()]
            for index, child in enumerate(visible_children):
                if hasattr(child, 'game') and child.game and child.game.title == title:
                    self._focus_flowbox_child_at(index)
                    break
            return False

        GLib.timeout_add(50, do_select)

    def on_flowbox_keynav_failed(self, flowbox, direction):
        flowbox.set_can_focus(False)
        result = self.child_focus(direction)
        flowbox.set_can_focus(True)
        return bool(result)

    def setup_interface(self, is_big=False):
        if is_big:
            self.set_default_size(1280, 720)
            self.set_resizable(True)
            if self.window_behavior == "Remember":
                self.set_default_size(self.window_width, self.window_height)
        else:
            self.set_default_size(-1, 610)
            self.set_resizable(False)

        self.box_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def create_button(icon_name, callback, tooltip=None):
            btn = Gtk.Button()
            btn.add_css_class("flash-btn")

            def trigger_flash(widget):
                widget.add_css_class("flashing")

                def remove_flash():
                    widget.remove_css_class("flashing")
                    return False

                GLib.timeout_add(50, remove_flash)

            btn.connect("clicked", trigger_flash)
            btn.connect("clicked", callback)

            btn.set_size_request(50, 50)
            btn.set_child(new_icon_image(f"{icon_name}.svg"))
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
        self.entry_search.connect("activate", self.on_search_activate)
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
                for idx, gid in enumerate(load_json_file(latest_games, default=[])):
                    self.latest_games_order[gid.strip()] = idx
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
            popover = Gtk.Popover()
            popover.set_parent(widget)
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
                btn.set_has_frame(False)
                vbox.append(btn)

            popover.set_child(vbox)
            popover.connect("closed", lambda p: p.unparent())
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
                for child in widget_children(self.flowbox):
                    if not hasattr(child, 'game') or not child.game:
                        continue
                    game = child.game

                    if self.interface_mode in ("Banners", "SteamGridDB") and hasattr(child, 'banner'):
                        zoom_width = int(230 * (zoom_pct / 100.0))
                        zoom_height = int(zoom_width * 1.5)
                        if os.path.isfile(game.banner):
                            surface = self.get_game_artwork(game.banner, game, zoom_width, zoom_height)
                        else:
                            surface = create_accent_placeholder_paintable(zoom_width, zoom_height)
                        child.banner.set_paintable(surface)

        self.zoom_slider.connect("value-changed", on_zoom_changed)

        scroll_box = Gtk.ScrolledWindow()
        scroll_box.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll_box.set_margin_top(10)
        scroll_box.set_margin_bottom(10)
        scroll_box.set_margin_start(10)
        scroll_box.set_margin_end(10)
        scroll_box.set_hexpand(True)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.connect("keynav-failed", self.on_flowbox_keynav_failed)
        click_release = Gtk.GestureClick()
        click_release.set_button(Gdk.BUTTON_PRIMARY)
        click_release.connect("released", self.on_item_release_event)
        self.flowbox.add_controller(click_release)

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

        def setup_dnd_for_widget(fb_child):
            if not isinstance(fb_child, Gtk.FlowBoxChild):
                return
            if getattr(fb_child, '_dnd_ready', False):
                return
            fb_child._dnd_ready = True

            def on_prepare(source, x, y):
                g = get_game(fb_child)
                if not g:
                    return None
                self._drag_source_id = g.gameid
                self.flowbox.select_child(fb_child)
                return Gdk.ContentProvider.new_for_value(g.gameid)

            def on_drag_begin(source, drag):
                g = get_game(fb_child)
                try:
                    if g and hasattr(g, 'icon') and g.icon:
                        if os.path.isfile(g.icon):
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(g.icon, 48, 48, True)
                            source.set_icon(Gdk.Texture.new_for_pixbuf(pixbuf), 24, 24)
                        else:
                            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                            icon_paintable = theme.lookup_icon(
                                g.icon, None, 48, fb_child.get_scale_factor(),
                                Gtk.TextDirection.NONE, 0)
                            source.set_icon(icon_paintable, 24, 24)
                except Exception:
                    pass

            def on_drag_end(source, drag, delete_data):
                self._drag_source_id = None
                if self.current_sort_id == "custom":
                    try:
                        with open(custom_order, "w") as f:
                            json.dump(self.custom_order_data, f)
                    except:
                        pass

            drag_source = Gtk.DragSource()
            drag_source.set_actions(Gdk.DragAction.MOVE)
            drag_source.connect("prepare", on_prepare)
            drag_source.connect("drag-begin", on_drag_begin)
            drag_source.connect("drag-end", on_drag_end)
            fb_child.add_controller(drag_source)

            def on_drop_motion(target, x, y):
                if self.current_sort_id != "custom" or not getattr(self, '_drag_source_id', None):
                    return 0

                target_g = get_game(fb_child)
                if not target_g:
                    return 0

                source_id = self._drag_source_id
                target_id = target_g.gameid

                if source_id == target_id:
                    return Gdk.DragAction.MOVE

                ordered = []
                for child in widget_children(self.flowbox):
                    g = get_game(child)
                    if g:
                        ordered.append(g.gameid)

                ordered.sort(key=lambda gid: self.custom_order_data.get(gid, 999999))

                try:
                    src = ordered.index(source_id)
                    dst = ordered.index(target_id)
                except ValueError:
                    return Gdk.DragAction.MOVE

                if src != dst:
                    ordered.pop(src)
                    ordered.insert(dst, source_id)

                    for idx, gid in enumerate(ordered):
                        self.custom_order_data[gid] = idx

                    self.flowbox.invalidate_sort()

                return Gdk.DragAction.MOVE

            drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
            drop_target.connect("motion", on_drop_motion)
            drop_target.connect("drop", lambda target, value, x, y: True)
            fb_child.add_controller(drop_target)

        self.setup_dnd_for_widget = setup_dnd_for_widget

        if is_big:
            self.flowbox.set_halign(Gtk.Align.CENTER)
            self.flowbox.set_valign(Gtk.Align.CENTER)
            self.flowbox.set_min_children_per_line(2)
            self.flowbox.set_max_children_per_line(20)
        else:
            self.flowbox.set_halign(Gtk.Align.FILL)
            self.flowbox.set_valign(Gtk.Align.START)
            self.flowbox.set_min_children_per_line(1)
            self.flowbox.set_max_children_per_line(1)

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
        scroll_box.set_child(self.flowbox)

        if is_big:
            self.main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.box_main.append(self.main_hbox)

            right_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.main_hbox.append(self.build_background_container(right_vbox))

            self.zoom_slider.set_visible(self.interface_mode in ("Banners", "SteamGridDB"))

            bottom_bar = Gtk.CenterBox(orientation=Gtk.Orientation.HORIZONTAL)
            bottom_bar.set_margin_top(5)
            bottom_bar.set_margin_bottom(10)
            bottom_bar.set_margin_start(10)
            bottom_bar.set_margin_end(10)

            bottom_bar.set_start_widget(self.zoom_slider)

            if getattr(self, 'show_categories', True):
                box_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                box_actions.set_margin_start(10)
                self.button_sort.set_size_request(50, 50)
                self.button_category.set_size_request(50, 50)
                box_actions.append(self.button_sort)
                box_actions.append(self.button_category)
                box_actions.set_halign(Gtk.Align.END)
                box_actions.set_valign(Gtk.Align.CENTER)
                box_actions.set_hexpand(True)
                box_actions.set_vexpand(False)
                bottom_bar.set_end_widget(box_actions)

            center_grid = Gtk.Grid()
            center_grid.set_column_spacing(10)
            center_grid.attach(self.button_add, 0, 0, 1, 1)
            center_grid.attach(self.button_settings, 1, 0, 1, 1)
            center_grid.attach(self.entry_search, 2, 0, 1, 1)
            center_grid.attach(self.button_kill, 3, 0, 1, 1)
            center_grid.attach(self.button_play, 4, 0, 1, 1)
            center_grid.set_valign(Gtk.Align.CENTER)
            center_grid.set_vexpand(False)

            bottom_bar.set_center_widget(center_grid)
            self.zoom_slider.set_valign(Gtk.Align.CENTER)
            self.zoom_slider.set_vexpand(False)

            right_vbox.append(scroll_box)
            right_vbox.append(bottom_bar)
            scroll_box.set_vexpand(True)

        else:
            self.box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.box_bottom = Gtk.Box()

            if getattr(self, 'show_categories', True):
                top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                top_bar.set_margin_top(10)
                top_bar.set_margin_start(10)
                top_bar.set_margin_end(10)
                self.button_sort.set_size_request(110, -1)
                self.button_category.set_size_request(110, -1)
                self.button_sort.set_hexpand(True)
                self.button_category.set_hexpand(True)
                top_bar.append(self.button_sort)
                top_bar.append(self.button_category)
                self.box_top.append(top_bar)

            self.box_top.append(scroll_box)
            scroll_box.set_vexpand(True)

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

            self.box_bottom.append(grid_controls)

            list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            list_container.append(self.box_top)
            list_container.append(self.box_bottom)

            self.box_main.append(self.build_background_container(list_container))

        update_sort_data()
        self.load_games()

        self.set_child(self.box_main)

        def on_first_map(*args):
            self.disconnect_by_func(on_first_map)
            surface = self.get_surface()

            attempts = {"n": 0}

            def grab_initial_focus():
                attempts["n"] += 1

                if isinstance(surface, Gdk.Toplevel):
                    surface.focus(Gdk.CURRENT_TIME)

                self.select_first_child()

                target = None
                for child in widget_children(self.flowbox):
                    if child.get_child_visible():
                        target = child
                        break

                matched = target is not None and self.get_focus() is target

                if matched and attempts["n"] >= 3:
                    return False
                if attempts["n"] >= 20:
                    return False
                return True

            GLib.timeout_add(100, grab_initial_focus)

        self.connect("map", on_first_map)
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_press_event)
        self.add_controller(key_controller)

    def on_category_button_clicked(self, button):
        popover = Gtk.Popover()
        popover.set_parent(button)
        popover.connect("closed", lambda p: p.unparent())
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
            btn.set_has_frame(False)

            def set_category(btn_widget, cat=cat_name):
                self.on_category_menu_item_selected(btn_widget, cat)
                popover.popdown()
            btn.connect("clicked", set_category)
            vbox.append(btn)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(5)
        separator.set_margin_bottom(5)
        vbox.append(separator)

        btn_manage = Gtk.Button(label=_("Manage categories..."))
        btn_manage.set_has_frame(False)

        def manage_categories(btn_widget):
            popover.popdown()
            GLib.idle_add(self.on_manage_categories_clicked, btn_widget)

        btn_manage.connect("clicked", manage_categories)
        vbox.append(btn_manage)

        popover.set_child(vbox)
        popover.popup()

        if focus_btn:
            focus_btn.grab_focus()

    def on_category_menu_item_selected(self, menu_item, category_name):
        self.button_category.set_label(category_name)
        self.current_category = category_name

        if hasattr(self, 'flowbox'):
            self.flowbox.invalidate_filter()

            self.flowbox.unselect_all()
            for child in widget_children(self.flowbox):
                if child.get_child_visible():
                    self.flowbox.select_child(child)
                    break

    def on_manage_categories_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Manage Categories"), transient_for=self)
        hide_dialog_action_area(dialog)
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
        listbox.add_css_class("category-list")
        scroll.set_child(listbox)
        frame.set_child(scroll)

        box.append(frame)

        def populate_dialog_list():
            for child in widget_children(listbox):
                listbox.remove(child)

            for c in self._get_current_categories():
                row = Gtk.ListBoxRow()
                row.set_size_request(-1, 40)
                lbl = Gtk.Label(label=c, xalign=0)
                lbl.set_margin_start(10)
                row.set_child(lbl)
                row.category_name = c
                listbox.append(row)

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

        btn_box.append(btn_add)
        btn_box.append(btn_edit)
        btn_box.append(btn_remove)

        box.append(btn_box)

        def on_add(b):
            row = Gtk.ListBoxRow()
            row.set_size_request(-1, 40)
            entry = Gtk.Entry()
            entry.set_margin_start(10)
            entry.set_margin_end(10)
            row.set_child(entry)
            row.category_name = None

            listbox.append(row)
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
            focus_controller = Gtk.EventControllerFocus()
            focus_controller.connect("leave", lambda c: GLib.idle_add(finish_add))
            entry.add_controller(focus_controller)

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

            entry = Gtk.Entry()
            entry.set_margin_start(10)
            entry.set_margin_end(10)
            entry.set_text(old_label)
            selected_row.set_child(entry)

            entry.grab_focus()
            entry.set_position(-1)

            finished = False

            def restore_label(text):
                lbl = Gtk.Label(label=text, xalign=0)
                lbl.set_margin_start(10)
                selected_row.set_child(lbl)
                selected_row.category_name = text

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
            focus_controller = Gtk.EventControllerFocus()
            focus_controller.connect("leave", lambda c: GLib.idle_add(finish_edit))
            entry.add_controller(focus_controller)

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

        dialog.connect("response", lambda d, r: destroy_and_release(d))
        dialog.present()

    def _save_categories(self, categories):
        save_json_file(list(categories), categories_file)

    def _get_current_categories(self):
        return [cat.strip() for cat in load_json_file(categories_file, default=[]) if cat.strip()]

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
                for flowbox_child in widget_children(self.flowbox):
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
                for child in widget_children(self.flowbox):
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
        dialog = Gtk.Dialog(title="Faugus", transient_for=self)
        hide_dialog_action_area(dialog)
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
        shutdown_btn.connect("clicked", lambda w: (self.on_shutdown(w), destroy_and_release(dialog)))

        reboot_btn = Gtk.Button(label=_("Reboot"))
        reboot_btn.connect("clicked", lambda w: (self.on_reboot(w), destroy_and_release(dialog)))

        close_btn = Gtk.Button(label=_("Close"))
        close_btn.connect("clicked", lambda w: (self.on_close_fullscreen(w), destroy_and_release(dialog)))

        box.append(shutdown_btn)
        box.append(reboot_btn)
        box.append(close_btn)

        content.append(box)

        dialog.connect("response", lambda d, r: destroy_and_release(d))
        dialog.present()

    def on_shutdown(self, widget):
        subprocess.run(["pkexec", "shutdown", "-h", "now"])

    def on_reboot(self, widget):
        subprocess.run(["pkexec", "reboot"])

    def on_close_fullscreen(self, widget):
        self.get_application().quit()

    def on_item_right_click(self, item=None, x=None, y=None):
        if item is None:
            selected = self.flowbox.get_selected_children()
            item = selected[0] if selected else None

        if not item:
            return

        self.flowbox.emit('child-activated', item)
        self.flowbox.select_child(item)

        game = self.selected()
        title = game.title

        self.menu_title.set_text(title)

        data = load_json_file(games_json, [])

        formatted = None
        for item_data in data:
            if isinstance(item_data, dict) and item_data.get("gameid") == game.gameid:
                game.playtime = item_data.get("playtime", 0)
                formatted = self.format_playtime(game.playtime)
                break

        self.menu_playtime.set_visible(bool(formatted))
        if formatted:
            self.menu_playtime.set_text(formatted)

        self.proton_log = f"{logs_dir}/{game.gameid}/proton.log"
        self.umu_log = f"{logs_dir}/{game.gameid}/umu.log"

        if os.path.exists(self.proton_log):
            self.menu_show_logs.set_sensitive(True)
            self.current_title = title
        else:
            self.menu_show_logs.set_sensitive(False)

        if game.hidden:
            self.menu_hide.set_label(_("Remove from hidden"))
        else:
            self.menu_hide.set_label(_("Hide"))

        child = self.submenu_category_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.submenu_category_box.remove(child)
            child = next_child

        categories = sorted(
            [cat.strip() for cat in load_json_file(categories_file, default=[]) if cat.strip()],
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

            cat_btn = Gtk.Button(label=label_text)
            cat_btn.set_has_frame(False)
            cat_btn.get_child().set_halign(Gtk.Align.START)
            cat_btn.connect("clicked", self.on_context_menu_category, cat, game.gameid)
            self.submenu_category_box.append(cat_btn)

        self.menu_show_logs.set_visible(self.enable_logging)

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

        if self.context_menu.get_parent():
            self.context_menu.unparent()
        self.context_menu.set_parent(item)
        if x is not None and y is not None:
            translated = self.flowbox.translate_coordinates(item, x, y)
            if translated is not None:
                ix, iy = translated
                rect = Gdk.Rectangle()
                rect.x, rect.y, rect.width, rect.height = int(ix), int(iy), 1, 1
                self.context_menu.set_pointing_to(rect)
        self.context_menu.popup()

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
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_button_play_clicked(None, game)

    def on_context_menu_edit(self, menu_item):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_button_edit_clicked(game)

    def on_context_menu_delete(self, menu_item):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_button_delete_clicked(game)

    def on_context_menu_duplicate(self, menu_item):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_duplicate_clicked()

    def on_context_menu_hide(self, menu_item):
        self.context_menu.popdown()
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
        self.submenu_category.popdown()
        self.context_menu.popdown()
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

                    for child in widget_children(self.flowbox):
                        if hasattr(child, "game") and child.game.gameid == selected_gameid:
                            child.game.category = current_cats if current_cats else None
                            break
                    break

            save_json_file(data, games_json)

        except Exception:
            return

        self.flowbox.invalidate_filter()

        self.flowbox.unselect_all()

        target_child = None
        first_visible = None
        for child in widget_children(self.flowbox):
            if not child.get_child_visible():
                continue
            if first_visible is None:
                first_visible = child
            if hasattr(child, "game") and child.game.gameid == selected_gameid:
                target_child = child
                break

        child_to_select = target_child if target_child is not None else first_visible
        if child_to_select is not None:
            self.flowbox.select_child(child_to_select)
            self.flowbox.set_focus_child(child_to_select)

    def on_context_menu_game_location(self, menu_item):
        self.context_menu.popdown()
        subprocess.run(["xdg-open", self.current_game], check=True)

    def on_context_menu_prefix_location(self, menu_item):
        self.context_menu.popdown()
        subprocess.run(["xdg-open", self.current_prefix], check=True)

    def on_context_menu_run(self, menu_item):
        self.context_menu.popdown()
        game = self.selected()
        if not game:
            return
        filechooser = new_file_chooser(
            self,
            _("Select a file to run inside the prefix"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "run_in_prefix")

        add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                prefix = game.prefix
                runner = game.runner
                title_formatted = format_title(game.title)
                file_run = dialog_fc.get_file().get_path()
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
                subprocess.Popen(cmd, cwd=cwd if cwd else None, env=subprocess_env())

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_context_show_logs(self, menu_item):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_show_logs_clicked()

    def on_show_logs_clicked(self):
        dialog = Gtk.Dialog(title=_("%s Logs") % self.current_title, transient_for=self)
        hide_dialog_action_area(dialog)
        dialog.set_modal(True)
        dialog.set_default_size(1280, 720)

        scrolled_window1 = Gtk.ScrolledWindow()
        scrolled_window1.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_view1 = Gtk.TextView()
        text_view1.set_editable(False)
        text_buffer1 = text_view1.get_buffer()
        with open(self.proton_log, "r") as log_file:
            text_buffer1.set_text(log_file.read())
        scrolled_window1.set_child(text_view1)

        scrolled_window2 = Gtk.ScrolledWindow()
        scrolled_window2.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        text_view2 = Gtk.TextView()
        text_view2.set_editable(False)
        text_buffer2 = text_view2.get_buffer()
        with open(self.umu_log, "r") as log_file:
            text_buffer2.set_text(log_file.read())
        scrolled_window2.set_child(text_view2)

        def copy_to_clipboard(button):
            current_page = notebook.get_current_page()
            if current_page == 0:
                start_iter, end_iter = text_buffer1.get_bounds()
                text_to_copy = text_buffer1.get_text(start_iter, end_iter, False)
            elif current_page == 1:
                start_iter, end_iter = text_buffer2.get_bounds()
                text_to_copy = text_buffer2.get_text(start_iter, end_iter, False)
            else:
                text_to_copy = ""

            dialog.get_clipboard().set(text_to_copy)

        def open_location(button):
            subprocess.run(["xdg-open", os.path.dirname(self.proton_log)], check=True)

        button_copy_clipboard = Gtk.Button(label=_("Copy to clipboard"))
        button_copy_clipboard.set_hexpand(True)
        button_copy_clipboard.connect("clicked", copy_to_clipboard)

        button_open_location = Gtk.Button(label=_("Open file location"))
        button_open_location.set_hexpand(True)
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
        tab_label1.set_hexpand(True)
        tab_box1.append(tab_label1)
        tab_box1.set_hexpand(True)

        tab_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label2 = Gtk.Label(label="UMU-Launcher")
        tab_label2.set_width_chars(15)
        tab_label2.set_xalign(0.5)
        tab_label2.set_hexpand(True)
        tab_box2.append(tab_label2)
        tab_box2.set_hexpand(True)

        notebook.append_page(scrolled_window1, tab_box1)
        notebook.append_page(scrolled_window2, tab_box2)

        content_area = dialog.get_content_area()
        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_homogeneous(True)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        box_bottom.append(button_copy_clipboard)
        box_bottom.append(button_open_location)

        content_area.append(notebook)
        content_area.append(box_bottom)

        dialog.connect("response", lambda d, r: destroy_and_release(d))
        dialog.present()

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
            destroy_and_release(dialog)
            return

        new_title = dialog.entry_title.get_text().strip()
        gameid = format_title(new_title)

        if not new_title:
            dialog.entry_title.add_css_class("entry")
            return

        if not gameid:
            dialog.entry_title.add_css_class("entry")
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
        new_icon = f"{icons_dir}/{title_formatted}.png"
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

        destroy_and_release(dialog)

    def on_item_release_event(self, gesture, n_press, x, y):
        current_item = self.flowbox.get_child_at_pos(int(x), int(y))
        if not current_item:
            return

        self.flowbox.select_child(current_item)
        if n_press == 2:
            self.on_item_double_click(current_item)

    def on_item_double_click(self, item):
        game = self.selected()
        gameid = game.gameid
        title = game.title

        if gameid in self.running:
            self.running_dialog(title)
        else:
            self.on_button_play_clicked()

    def on_key_press_event(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_h and state & Gdk.ModifierType.CONTROL_MASK:
            try:
                config = ConfigManager()
                current = config.config.get("show-hidden", "False")
                config.set_value("show-hidden", "False" if current == "True" else "True")
                config.save_config()

                self.load_config()
                self.update_list()
                self.select_first_child()
                return True
            except Exception:
                return False

        if keyval == Gdk.KEY_Return and state & Gdk.ModifierType.ALT_MASK:
            if self.interface_mode != "List":
                if self.fullscreen_activated:
                    self.fullscreen_activated = False
                    self.unfullscreen()
                else:
                    self.fullscreen_activated = True
                    self.fullscreen()
                return True

        if keyval == Gdk.KEY_Escape and getattr(self, 'fullscreen_activated', False):
            self.show_power_menu(self)
            return True

        game = self.selected()
        if not game:
            return False

        gameid = game.gameid
        title = game.title

        child = self.flowbox.get_selected_children()[0]
        current_focus = self.get_focus()

        if not child.is_focus():
            return False

        if keyval in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right):
            if current_focus not in widget_children(self.flowbox):
                child.grab_focus()

        if keyval == Gdk.KEY_Return:
            if gameid in self.running:
                self.running_dialog(title)
            else:
                self.on_button_play_clicked()

        if keyval == Gdk.KEY_Delete:
            self.on_button_delete_clicked()

        return False

    def running_dialog(self, title):
        show_message_dialog(_("%s is already running.") % title, parent=self)

    def load_config(self):
        cfg = ConfigManager()

        self.system_tray = cfg.config.get('system-tray', 'False') == 'True'
        self.mono_icon = cfg.config.get('mono-icon', 'False') == 'True'
        self.close_on_launch = cfg.config.get('close-onlaunch', 'False') == 'True'
        self.interface_mode = cfg.config.get('interface-mode', '').strip('"')
        self.background_mode = cfg.config.get('background-mode', 'default').strip('"')
        self.hero_enabled = cfg.config.get('hero-enabled', 'True') == 'True'
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

        self.menu_show_logs.set_visible(self.enable_logging)

    def load_games(self):
        games_data = load_json_file(games_json, [])

        self.games.clear()
        for game_data in games_data:
            game = Game(**prepare_game_kwargs(game_data))

            if not self.show_hidden and game.hidden:
                continue

            self.games.append(game)

        self.games = sorted(self.games, key=lambda x: x.title.lower())

        w = self.get_focus()
        while w is not None:
            if w is self.flowbox:
                self.set_focus(None)
                break
            w = w.get_parent()

        self.flowbox.remove_all()
        for game in self.games:
            self.add_item_list(game)

    def add_item_list(self, game):
        zoom_pct = self.banner_size

        if self.interface_mode == "List":
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        if self.interface_mode == "Blocks":
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            hbox.set_size_request(200, -1)
        if self.interface_mode in ("Banners", "SteamGridDB"):
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        hbox.add_css_class("game")

        game_icon = game.icon
        if not os.path.isfile(game_icon):
            game_icon = faugus_png

        game_label = Gtk.Label.new(game.title)

        if self.interface_mode in ("Blocks", "Banners", "SteamGridDB"):
            game_label.set_wrap(True)
            game_label.set_lines(2)
            game_label.set_ellipsize(Pango.EllipsizeMode.END)
            game_label.set_max_width_chars(1)
            game_label.set_justify(Gtk.Justification.CENTER)

        self.flowbox_child = Gtk.FlowBoxChild()
        self.flowbox_child.game = game
        self.flowbox_child.label = game_label
        self.flowbox_child.hbox = hbox

        anim_box = Gtk.Box()
        anim_box.add_css_class("launch-overlay")
        anim_box.set_hexpand(True)
        anim_box.set_vexpand(True)
        self.flowbox_child.anim_box = anim_box

        if self.interface_mode == "List":
            surface = self.get_game_artwork(game_icon, game, 40, 40)
            image = new_picture(surface)

            self.flowbox_child.image = image

            image.set_margin_start(10)
            image.set_margin_end(10)
            image.set_margin_top(10)
            image.set_margin_bottom(10)

            game_label.set_margin_start(10)
            game_label.set_margin_end(10)
            game_label.set_margin_top(10)
            game_label.set_margin_bottom(10)

            hbox.append(image)
            hbox.append(game_label)

            self.flowbox_child.set_size_request(300, -1)
            self.flowbox.set_homogeneous(True)
            self.flowbox_child.set_valign(Gtk.Align.START)
            self.flowbox_child.set_halign(Gtk.Align.FILL)

        if self.interface_mode == "Blocks":
            self.flowbox_child.set_hexpand(True)
            self.flowbox_child.set_vexpand(True)

            block_size = 100

            surface = self.get_game_artwork(game_icon, game, block_size, block_size)
            image = new_picture(surface)

            self.flowbox_child.image = image

            image.set_margin_top(10)
            game_label.set_margin_top(10)
            game_label.set_margin_start(10)
            game_label.set_margin_end(10)
            game_label.set_margin_bottom(10)

            hbox.append(image)
            game_label.set_vexpand(True)
            game_label.set_valign(Gtk.Align.CENTER)
            hbox.append(game_label)

            self.flowbox_child.set_valign(Gtk.Align.FILL)
            self.flowbox_child.set_halign(Gtk.Align.FILL)

        if self.interface_mode in ("Banners", "SteamGridDB"):
            self.flowbox_child.set_hexpand(True)
            self.flowbox_child.set_vexpand(True)

            image2 = new_picture()
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

            zoom_width = int(230 * (zoom_pct / 100.0))
            zoom_height = int(zoom_width * 1.5)

            if os.path.isfile(game.banner):
                surface = self.get_game_artwork(game.banner, game, zoom_width, zoom_height)
            else:
                surface = create_accent_placeholder_paintable(zoom_width, zoom_height)
            image2.set_paintable(surface)

            hbox.append(image2)

            self.flowbox_child.add_css_class("banner-container")
            self.flowbox_child.set_overflow(Gtk.Overflow.HIDDEN)

            game_label.set_visible(self.show_labels)
            game_label.set_vexpand(True)
            game_label.set_valign(Gtk.Align.CENTER)
            hbox.append(game_label)

        overlay = Gtk.Overlay()
        overlay.set_child(hbox)
        overlay.add_overlay(anim_box)
        anim_box.set_can_target(False)
        self.flowbox_child.set_child(overlay)

        self.flowbox.append(self.flowbox_child)
        self.setup_dnd_for_widget(self.flowbox_child)

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

            flowbox_child.image.set_paintable(surface)

        if hasattr(flowbox_child, "banner"):
            zoom_pct = getattr(self, "banner_size", 100)
            zoom_width = int(230 * (zoom_pct / 100.0))
            zoom_height = int(zoom_width * 1.5)

            if os.path.isfile(game.banner):
                surface = self.get_game_artwork(game.banner, game, zoom_width, zoom_height)
            else:
                surface = create_accent_placeholder_paintable(zoom_width, zoom_height)
            flowbox_child.banner.set_paintable(surface)

    def get_game_artwork(self, path, game, width=None, height=None):
        w = width * HIDPI_SCALE if width else None
        h = height * HIDPI_SCALE if height else None

        pixbuf = safe_load_pixbuf(path, w, h, False)

        if not self.is_game_installed(game):
            pixbuf.saturate_and_pixelate(pixbuf, 0.0, False)

        texture = Gdk.Texture.new_for_pixbuf(pixbuf)

        if width and height:
            return HiDpiPaintable(texture, width, height)
        return texture

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

        self.flowbox.unselect_all()
        for child in widget_children(self.flowbox):
            if child.get_child_visible():
                self.flowbox.select_child(child)
                break

    def on_search_activate(self, entry):
        game = self.selected()
        if not game:
            return

        if game.gameid in self.running:
            self.running_dialog(game.title)
        else:
            self.on_button_play_clicked()

    def on_button_settings_clicked(self, widget):

        settings_dialog = Settings(self)
        settings_dialog.connect("response", self.on_settings_dialog_response, settings_dialog)

        settings_dialog.show()

    def on_settings_dialog_response(self, dialog, response_id, settings_dialog):
        if faugus_backup:
            os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

        if response_id == Gtk.ResponseType.OK:
            default_prefix = settings_dialog.entry_default_prefix.get_text()
            validation_result = self.validate_settings_fields(settings_dialog, default_prefix)
            if not validation_result:
                return

            def finish_settings():
                apply_interface_customization(settings_dialog.interface_theme, settings_dialog.accent_color)

                self.save_interface_settings()
                settings_dialog.update_config_file()
                self.manage_autostart_file(settings_dialog.checkbox_start_boot.get_active(), settings_dialog.checkbox_start_minimized.get_active())

                new_system_tray = settings_dialog.checkbox_system_tray.get_active()
                new_mono_icon = settings_dialog.checkbox_mono_icon.get_active()
                tray_needs_reload = (
                    self.system_tray != new_system_tray or
                    self.mono_icon != new_mono_icon
                )

                self.system_tray = new_system_tray
                self.mono_icon = new_mono_icon

                if tray_needs_reload:
                    self.load_tray_icon()

                combobox_language = settings_dialog.combobox_language.get_active_text()

                if self.interface_mode != settings_dialog.combobox_interface.get_active_id():
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                if self.background_mode != settings_dialog.combobox_background.get_active_id():
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                if self.hero_enabled != settings_dialog.checkbox_hero_background.get_active():
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                if self.show_labels != settings_dialog.checkbox_show_labels.get_active():
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                if self.language != settings_dialog.lang_codes.get(combobox_language, "en_US"):
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                if self.gamepad_navigation != settings_dialog.checkbox_gamepad_navigation.get_active():
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                if self.show_categories != settings_dialog.checkbox_show_categories.get_active():
                    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

                settings_dialog.update_envar_file()

                if self.show_hidden != settings_dialog.checkbox_show_hidden.get_active():
                    self.load_config()
                    self.update_list()

                self.load_config()

                destroy_and_release(settings_dialog)

            def proceed():
                if not settings_dialog.logging_warning and settings_dialog.checkbox_enable_logging.get_active():
                    settings_dialog.logging_warning = True
                    self.show_warning_dialog_main(
                        self,
                        _("Proton may generate huge log files."),
                        _("Enable logging only when debugging a problem."),
                        callback=lambda confirmed: finish_settings()
                    )
                else:
                    finish_settings()

            proceed()

        else:
            apply_interface_customization(settings_dialog.original_interface_theme, settings_dialog.original_accent_color)
            destroy_and_release(settings_dialog)

    def validate_settings_fields(self, settings_dialog, default_prefix):
        settings_dialog.entry_default_prefix.remove_css_class("entry")
        settings_dialog.entry_steamgriddb_key.remove_css_class("entry")

        valid = True

        if not default_prefix:
            settings_dialog.entry_default_prefix.add_css_class("entry")
            valid = False

        if (settings_dialog.combobox_interface.get_active_id() == "SteamGridDB"
                and not settings_dialog.entry_steamgriddb_key.get_text().strip()):
            settings_dialog.entry_steamgriddb_key.add_css_class("entry")
            valid = False

        return valid

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
                        "Name=Faugus\n"
                        f"Exec=flatpak run io.github.Faugus.faugus-launcher{hide_arg}\n"
                        "Icon=io.github.Faugus.faugus-launcher\n"
                        "Categories=Game;\n"
                        "StartupWMClass=faugus-launcher\n"
                    )
                else:
                    f.write(
                        "[Desktop Entry]\n"
                        "Type=Application\n"
                        "Name=Faugus\n"
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
                child.anim_box.add_css_class("playing")

                def remove_anim():
                    child.anim_box.remove_css_class("playing")
                    return False
                GLib.timeout_add(150, remove_anim)

        gameid = game.gameid
        game_directory = os.path.dirname(game.path)
        cwd = game_directory if game_directory and os.path.isdir(game_directory) else None

        def update_latest_and_sort():
            self.update_latest_games_file(game.gameid)
            if hasattr(self, 'current_sort') and self.current_sort == self.opt_lastplayed:
                self.latest_games_order.clear()
                try:
                    for idx, gid in enumerate(load_json_file(latest_games, default=[])):
                        self.latest_games_order[gid.strip()] = idx
                except:
                    pass
                if hasattr(self, 'flowbox'):
                    self.flowbox.invalidate_sort()

        if game.runner == "Steam":
            update_latest_and_sort()
            subprocess.Popen(
                [sys.executable, "-m", "faugus.runner", "--game", gameid],
                cwd=cwd,
                env=subprocess_env(),
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
        proc = subprocess.Popen(cmd, cwd=cwd if cwd else None, env=subprocess_env())

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
        games = load_json_file(latest_games, default=[])

        valid_ids = {g.gameid for g in self.games}

        games = [g for g in games if g in valid_ids and g != gameid]
        games.insert(0, gameid)

        save_json_file(games, latest_games)

        if self.system_tray:
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

            for i, text in enumerate(edit_game_dialog.combobox_steam_title.get_texts()):
                if text == title:
                    edit_game_dialog.combobox_steam_title.set_active(i)
                    break

            game_runner = convert_runner(game.runner)

            if game_runner == "Linux-Native":
                edit_game_dialog.combobox_launcher.set_active_id("linux")
            if game_runner == "Steam":
                edit_game_dialog.combobox_launcher.set_active_id("steam")

            index_runner = 0

            for i, text in enumerate(edit_game_dialog.combobox_runner.get_texts()):
                if text == game_runner:
                    index_runner = i
                    break
            if not game_runner:
                index_runner = 1

            edit_game_dialog.combobox_runner.set_active(index_runner)
            edit_game_dialog._suggestion_programmatic = True
            edit_game_dialog.entry_title.set_text(game.title)
            edit_game_dialog._suggestion_programmatic = False
            edit_game_dialog._steamgriddb_suggestion_id = getattr(game, "steamgriddb_id", "") or None
            edit_game_dialog._steamgriddb_steam_appid = game.path if game_runner == "Steam" else None
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

            if os.path.isfile(game.banner):
                shutil.copyfile(game.banner, edit_game_dialog.banner_path_temp)
            elif os.path.isfile(edit_game_dialog.banner_path_temp):
                os.remove(edit_game_dialog.banner_path_temp)
            edit_game_dialog.update_image_banner()

            hero_path = f"{heroes_dir}/{game.gameid}.png"
            if os.path.isfile(hero_path):
                shutil.copyfile(hero_path, edit_game_dialog.hero_path_temp)
                edit_game_dialog.update_hero_preview(edit_game_dialog.hero_path_temp)

            icon_path = game.icon
            if not os.path.isfile(icon_path):
                icon_path = faugus_png

            shutil.copyfile(icon_path, edit_game_dialog.icon_temp)
            surface = self.new_texture_from_image(icon_path, 50, 50)
            image = new_picture(surface)
            edit_game_dialog.button_shortcut_icon.set_child(image)

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

            if get_all_shortcut_paths():
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
        for path in get_all_shortcut_paths():
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        shortcuts = vdf.binary_load(f)
                    if "shortcuts" in shortcuts:
                        for game in shortcuts["shortcuts"].values():
                            if isinstance(game, dict) and "AppName" in game and game["AppName"] == title:
                                return True
                except SyntaxError:
                    continue
        return False

    def on_button_delete_clicked(self, *_):
        self.reload_playtimes()
        game = self.selected()
        title = game.title

        if game:
            delete_dialog = DeleteDialog(self, title, game.prefix, game.runner)
            delete_dialog.connect("response", self._on_confirm_delete_response, game)

    def _on_confirm_delete_response(self, dialog, response, game):
        remove_prefix = dialog.checkbox.get_active()
        destroy_and_release(dialog)

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

            if remove_prefix:
                prefix_path = os.path.expanduser(game.prefix)

                try:
                    shutil.rmtree(prefix_path)
                except PermissionError:
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

            self.remove_shortcut(game, "both")
            self.remove_steam_shortcut(title)
            self.remove_banner_icon(game)

            if os.path.exists(game.addapp_bat):
                os.remove(game.addapp_bat)

            self._deleted_gameid = gameid
            self.save_games()
            self.update_list()

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
        for path in get_all_shortcut_paths():
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        shortcuts = vdf.binary_load(f)

                    if "shortcuts" not in shortcuts:
                        continue

                    to_remove = [app_id for app_id, game in shortcuts["shortcuts"].items() if
                                 isinstance(game, dict) and "AppName" in game and game["AppName"] == title]

                    if to_remove:
                        for app_id in to_remove:
                            del shortcuts["shortcuts"][app_id]

                        with open(path, 'wb') as f:
                            vdf.binary_dump(shortcuts, f)
                except SyntaxError:
                    pass

    def remove_latest_and_order(self, gameid):
        try:
            recent_games = load_json_file(latest_games, default=[])

            if gameid in recent_games:
                recent_games.remove(gameid)

                save_json_file(recent_games, latest_games)

                if self.system_tray:
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

    def show_warning_dialog_main(self, parent, text1, text2, callback=None):
        show_message_dialog(text1, text2, parent=parent, callback=callback)

    def on_dialog_response(self, dialog, response_id, add_game_dialog):
        banner_path_temp = add_game_dialog.banner_path_temp
        dialog_destroyed = False

        def destroy_add_game_dialog():
            add_game_dialog.closed_event.set()
            destroy_and_release(add_game_dialog)

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

            if self.interface_mode in ("Banners", "SteamGridDB"):
                temp_banner_path = add_game_dialog.banner_path_temp
                if os.path.isfile(temp_banner_path):
                    banner = os.path.join(banners_dir, f"{title_formatted}.png")
                    try:
                        command_magick = shutil.which("magick") or shutil.which("convert")
                        subprocess.run([command_magick, temp_banner_path, "-resize", "460x690!", banner], check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error resizing banner: {e}")
                else:
                    banner = ""

                temp_hero_path = add_game_dialog.hero_path_temp
                if os.path.isfile(temp_hero_path):
                    hero = os.path.join(heroes_dir, f"{title_formatted}.png")
                    try:
                        command_magick = shutil.which("magick") or shutil.which("convert")
                        subprocess.run([command_magick, temp_hero_path, "-resize", "1920x620!", hero], check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error resizing hero: {e}")
            else:
                banner = ""

            icon_temp = os.path.expanduser(add_game_dialog.icon_temp)
            icon_final = f'{add_game_dialog.icons_path}/{title_formatted}.png'
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
                steamgriddb_id=add_game_dialog._steamgriddb_suggestion_id or "",
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
                    destroy_add_game_dialog()
                    dialog_destroyed = True
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
            destroy_add_game_dialog()
            dialog_destroyed = True
        if os.path.isfile(banner_path_temp):
            os.remove(banner_path_temp)
        if not dialog_destroyed:
            destroy_add_game_dialog()

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

        sizer_labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sizer_labels.set_size_request(-1, 128)

        grid_labels = Gtk.Grid()
        grid_labels.set_vexpand(True)
        grid_labels.set_valign(Gtk.Align.CENTER)

        self.box_launcher.append(grid_launcher)

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

        grid_launcher.attach(sizer_labels, 0, 1, 1, 1)
        sizer_labels.append(grid_labels)
        grid_labels.attach(self.label_download, 0, 0, 1, 1)
        grid_labels.attach(self.bar_download, 0, 1, 1, 1)
        grid_labels.attach(self.label_download2, 0, 2, 1, 1)

        if self.interface_mode != "List":
            self.box_main.remove(self.main_hbox)
        else:
            self.box_main.remove(self.box_top)
            self.box_main.remove(self.box_bottom)
        self.box_main.append(self.box_launcher)

    def monitor_process(self, processo, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, title):
        retcode = processo.poll()

        if retcode is not None:
            if os.path.exists(faugus_temp):
                shutil.rmtree(faugus_temp)
            self.box_main.remove(self.box_launcher)
            if self.interface_mode != "List":
                self.box_main.append(self.main_hbox)
            else:
                self.box_main.append(self.box_top)
                self.box_main.append(self.box_bottom)

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
        os.makedirs(icons_dir, exist_ok=True)
        final = os.path.join(icons_dir, f"{gameid}.png")
        status = extract_ico(exe_path, final, best_frame=True)
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
                processo = subprocess.Popen([sys.executable, "-m", "faugus.runner", command], env=subprocess_env())
                GLib.timeout_add(100, self.monitor_process, processo, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, title)

            run_in_background(start_download)

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
            game.steamgriddb_id = edit_game_dialog._steamgriddb_suggestion_id or ""

            title_formatted = format_title(game.title)

            game.gameid = title_formatted
            game.addapp_bat = f"{os.path.dirname(game.path)}/faugus-{title_formatted}.bat"

            if self.interface_mode in ("Banners", "SteamGridDB"):
                temp_banner_path = edit_game_dialog.banner_path_temp
                if os.path.isfile(temp_banner_path):
                    banner = os.path.join(banners_dir, f"{title_formatted}.png")
                    try:
                        command_magick = shutil.which("magick") or shutil.which("convert")
                        subprocess.run([command_magick, temp_banner_path, "-resize", "460x690!", banner], check=True)
                        game.banner = banner
                    except subprocess.CalledProcessError as e:
                        print(f"Error resizing banner: {e}")
                else:
                    game.banner = ""

                temp_hero_path = edit_game_dialog.hero_path_temp
                if os.path.isfile(temp_hero_path):
                    hero = os.path.join(heroes_dir, f"{title_formatted}.png")
                    try:
                        command_magick = shutil.which("magick") or shutil.which("convert")
                        subprocess.run([command_magick, temp_hero_path, "-resize", "1920x620!", hero], check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error resizing hero: {e}")

            icon_temp = os.path.expanduser(edit_game_dialog.icon_temp)
            icon_final = f'{edit_game_dialog.icons_path}/{title_formatted}.png'
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
        if os.path.isfile(edit_game_dialog.banner_path_temp):
            os.remove(edit_game_dialog.banner_path_temp)
        edit_game_dialog.closed_event.set()
        destroy_and_release(edit_game_dialog)

    def add_shortcut(self, game, shortcut_state, shortcut, icon_temp, icon_final):
        applications_shortcut_path = f"{app_dir}/{game.gameid}.desktop"
        desktop_shortcut_path = f"{desktop_dir}/{game.gameid}.desktop"

        if shortcut == "desktop" and not shortcut_state:

            self.remove_shortcut(game, shortcut)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return
        if shortcut == "appmenu" and not shortcut_state:

            self.remove_shortcut(game, shortcut)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return

        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        new_icon_path = f"{icons_dir}/{game.gameid}.png"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        game_directory = os.path.dirname(game.path)

        if IS_FLATPAK:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={game.title}\n'
                f'Exec=flatpak run --command={launcher_path} io.github.Faugus.faugus-launcher {launcher_module_args}--game {game.gameid}\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )
        else:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={game.title}\n'
                f'Exec={launcher_path} {launcher_module_args}--game {game.gameid}\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )

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
            for path in get_all_shortcut_paths():
                shortcuts = load_shortcuts(path)

                if "shortcuts" not in shortcuts:
                    shortcuts["shortcuts"] = {}

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
                        launch_options = f'--host {launcher_path} {launcher_module_args}--game {game.gameid}'
                    else:
                        exe = f'"{launcher_path}"'
                        launch_options = f'{launcher_module_args}--game {game.gameid}'

                asset_id = generate_steam_shortcut_id(exe, title)

                if existing_app_id:
                    game_info = shortcuts["shortcuts"][existing_app_id]
                    game_info.update({
                        "appid": to_signed_int32(asset_id),
                        "Exe": exe,
                        "StartDir": game_directory,
                        "icon": icon,
                        "LaunchOptions": launch_options
                    })
                else:
                    new_app_id = max([int(k) for k in shortcuts["shortcuts"].keys() if k.isdigit()] or [0]) + 1

                    shortcuts["shortcuts"][str(new_app_id)] = {
                        "appid": to_signed_int32(asset_id),
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
                save_shortcuts(shortcuts, path)

                grid_dir = os.path.join(os.path.dirname(path), "grid")
                os.makedirs(grid_dir, exist_ok=True)

                grid_src = f"{banners_dir}/{game.gameid}.png"
                hero_src = f"{heroes_dir}/{game.gameid}.png"

                if os.path.isfile(grid_src):
                    shutil.copy2(grid_src, os.path.join(grid_dir, f"{asset_id}p.png"))

                if os.path.isfile(hero_src):
                    shutil.copy2(hero_src, os.path.join(grid_dir, f"{asset_id}_hero.png"))

        def remove_shortcuts(title):
            for path in get_all_shortcut_paths():
                if os.path.exists(path):
                    try:
                        with open(path, 'rb') as f:
                            shortcuts = vdf.binary_load(f)

                        if "shortcuts" in shortcuts:
                            to_remove = [app_id for app_id, game_info in shortcuts["shortcuts"].items() if
                                         isinstance(game_info, dict) and "AppName" in game_info and game_info["AppName"] == title]
                            if to_remove:
                                for app_id in to_remove:
                                    del shortcuts["shortcuts"][app_id]
                                save_shortcuts(shortcuts, path)
                    except SyntaxError:
                        pass

        def load_shortcuts(path):
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        return vdf.binary_load(f)
                except SyntaxError:
                    return {"shortcuts": {}}
            return {"shortcuts": {}}

        def save_shortcuts(shortcuts, path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                vdf.binary_dump(shortcuts, f)

        if not steam_shortcut_state:
            remove_shortcuts(game.title)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return

        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        new_icon_path = f"{icons_dir}/{game.gameid}.png"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        game_directory = os.path.dirname(game.path)

        add_game_to_steam(game.title, game_directory, new_icon_path)

    def remove_banner_icon(self, game):
        banner_file_path = f"{banners_dir}/{game.gameid}.png"
        icon_file_path = f"{icons_dir}/{game.gameid}.png"
        hero_file_path = f"{heroes_dir}/{game.gameid}.png"
        if os.path.exists(banner_file_path):
            os.remove(banner_file_path)
        if os.path.exists(icon_file_path):
            os.remove(icon_file_path)
        if os.path.exists(hero_file_path):
            os.remove(hero_file_path)

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
        super().__init__(title=_("Settings"), transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        self.parent = parent
        self.logging_warning = False
        self.modified = False

        add_css_once("settings_dialog", """
        .entry {
            border: 1px solid red;
        }
        .paypal {
            color: white;
            background: #001C64;
        }
        .kofi {
            color: white;
            background: #1AC0FF;
        }
        """, Gtk.STYLE_PROVIDER_PRIORITY_USER)

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
        self.combobox_language = IdComboBox()

        self.label_interface = Gtk.Label(label=_("Mode"))
        self.label_interface.set_halign(Gtk.Align.START)
        self.combobox_interface = IdComboBox()
        self.combobox_interface.connect("changed", self.on_combobox_interface_changed)
        self.combobox_interface.append("List", _("List"))
        self.combobox_interface.append("Blocks", _("Blocks"))
        self.combobox_interface.append("Banners", _("Banners"))
        self.combobox_interface.append("SteamGridDB", _("SteamGridDB"))

        self.label_background = Gtk.Label(label=_("Background"))
        self.label_background.set_halign(Gtk.Align.START)
        self.combobox_background = IdComboBox()
        self.combobox_background.append("default", _("Default"))
        self.combobox_background.append("accent", _("Accent color"))
        self.combobox_background.append("dominant_color", _("Dominant color"))

        self.checkbox_hero_background = Gtk.CheckButton(label=_("Show hero"))

        self.label_ui_customization = Gtk.Label(label=_("UI Customization"))
        self.label_ui_customization.set_halign(Gtk.Align.START)

        self.label_theme = Gtk.Label(label=_("Theme"))
        self.label_theme.set_halign(Gtk.Align.START)
        self.combobox_theme = IdComboBox()
        self.combobox_theme.append("system", _("Auto"))
        self.combobox_theme.append("light", _("Light"))
        self.combobox_theme.append("dark", _("Dark"))
        self.combobox_theme.connect("changed", self.on_theme_accent_changed)

        self.label_accent = Gtk.Label(label=_("Accent Color"))
        self.label_accent.set_halign(Gtk.Align.START)
        self.combobox_accent = IdComboBox()
        self.combobox_accent.append("system", _("Auto"))
        self.combobox_accent.append("custom", _("Custom"))
        self.combobox_accent.connect("changed", self.on_theme_accent_changed)

        self.color_button = Gtk.ColorButton()
        self.color_button.set_sensitive(False)
        self.color_button.connect("color-set", self.on_theme_accent_changed)

        self.box_accent = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.box_accent.append(self.combobox_accent)
        self.box_accent.append(self.color_button)

        self.label_window_behavior = Gtk.Label(label=_("Window Behavior"))
        self.label_window_behavior.set_halign(Gtk.Align.START)

        self.combobox_window_behavior = IdComboBox()
        self.combobox_window_behavior.append("None", _("Default window size"))
        self.combobox_window_behavior.append("Remember", _("Remember window size"))
        self.combobox_window_behavior.append("Maximized", _("Start maximized"))
        self.combobox_window_behavior.append("Fullscreen", _("Start in fullscreen"))
        self.combobox_window_behavior.set_tooltip_text(_("Alt+Enter toggles fullscreen"))

        self.checkbox_show_labels = Gtk.CheckButton(label=_("Show labels"))
        self.checkbox_show_labels.set_active(False)

        self.label_steamgriddb_key = Gtk.Label()
        self.label_steamgriddb_key.set_markup(
            f'<a href="https://www.steamgriddb.com/profile/preferences/api">{_("SteamGridDB API Key")}</a>'
        )
        self.label_steamgriddb_key.set_use_markup(True)
        self.label_steamgriddb_key.set_halign(Gtk.Align.START)

        self.entry_steamgriddb_key = Gtk.Entry()

        self.label_default_prefix = Gtk.Label(label=_("Default Prefixes Location"))
        self.label_default_prefix.set_halign(Gtk.Align.START)

        self.entry_default_prefix = Gtk.Entry()
        self.entry_default_prefix.set_tooltip_text(_("/path/to/the/prefix"))
        self.entry_default_prefix.set_has_tooltip(True)
        self.entry_default_prefix.connect("query-tooltip", on_entry_query_tooltip)
        self.entry_default_prefix.connect("changed", on_entry_changed)

        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        self.label_lossless = Gtk.Label(label=_("Lossless Scaling Location"))
        self.label_lossless.set_halign(Gtk.Align.START)

        self.entry_lossless = Gtk.Entry()
        self.entry_lossless.set_tooltip_text(_("/path/to/Lossless.dll"))
        self.entry_lossless.set_has_tooltip(True)
        self.entry_lossless.connect("query-tooltip", on_entry_query_tooltip)

        self.button_search_lossless = Gtk.Button()
        self.button_search_lossless.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_lossless.connect("clicked", self.on_button_search_lossless_clicked)
        self.button_search_lossless.set_size_request(50, -1)

        self.label_default_prefix_tools = Gtk.Label(label=_("Default Prefix Tools"))
        self.label_default_prefix_tools.set_halign(Gtk.Align.START)
        self.label_default_prefix_tools.set_margin_start(10)
        self.label_default_prefix_tools.set_margin_end(10)
        self.label_default_prefix_tools.set_margin_top(10)

        self.label_runner = Gtk.Label(label=_("Default Proton"))
        self.label_runner.set_halign(Gtk.Align.START)
        self.combobox_runner = IdComboBox()

        self.button_proton_manager = Gtk.Button(label=_("Proton Manager"))
        self.button_proton_manager.connect("clicked", self.on_button_proton_manager_clicked)

        self.label_miscellaneous = Gtk.Label(label=_("Miscellaneous"))
        self.label_miscellaneous.set_halign(Gtk.Align.START)

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
        self.label_support.set_margin_end(10)

        button_kofi, button_paypal = make_donate_buttons()

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        self.button_cancel.set_hexpand(True)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        self.button_ok.set_hexpand(True)

        self.label_settings = Gtk.Label(label=_("Backup/Restore Settings"))
        self.label_settings.set_halign(Gtk.Align.START)
        self.label_settings.set_margin_end(10)

        button_backup = Gtk.Button(label=_("Backup"))
        button_backup.connect("clicked", self.on_button_backup_clicked)

        button_restore = Gtk.Button(label=_("Restore"))
        button_restore.connect("clicked", self.on_button_restore_clicked)

        self.button_clearlogs = Gtk.Button()
        self.update_button_label()
        self.button_clearlogs.connect("clicked", self.on_clear_logs_clicked)

        self.label_envar = Gtk.Label(label=_("Global Environment Variables"))
        self.label_envar.set_halign(Gtk.Align.START)
        self.label_envar.set_margin_top(10)

        self.liststore = Gtk.ListStore(str)
        self.liststore.append([""])

        treeview = Gtk.TreeView(model=self.liststore)
        treeview.add_css_class("envar-list")
        treeview.set_has_tooltip(True)
        treeview.connect("query-tooltip", self.on_query_tooltip)
        envar_key_controller = Gtk.EventControllerKey()
        envar_key_controller.connect("key-pressed", self.on_envar_key_press)
        treeview.add_controller(envar_key_controller)

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
        scrolled_window.set_child(treeview)

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

        frame.set_margin_top(10)
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
        box_buttons.set_valign(Gtk.Align.CENTER)

        grid_language = Gtk.Grid()
        grid_language.set_row_spacing(10)
        grid_language.set_column_spacing(10)
        grid_language.set_margin_start(10)
        grid_language.set_margin_end(10)
        grid_language.set_margin_top(10)
        grid_language.set_margin_bottom(10)
        grid_language.set_vexpand(True)
        grid_language.set_valign(Gtk.Align.END)

        grid_prefix = Gtk.Grid()
        grid_prefix.set_row_spacing(10)
        grid_prefix.set_column_spacing(10)
        grid_prefix.set_margin_start(10)
        grid_prefix.set_margin_end(10)
        grid_prefix.set_margin_top(10)
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

        grid_theme_accent = Gtk.Grid()
        grid_theme_accent.set_row_spacing(10)
        grid_theme_accent.set_column_spacing(10)
        grid_theme_accent.set_margin_start(10)
        grid_theme_accent.set_margin_end(10)
        grid_theme_accent.set_margin_top(10)
        grid_theme_accent.set_margin_bottom(10)

        grid_theme_rest = Gtk.Grid()
        grid_theme_rest.set_row_spacing(10)
        grid_theme_rest.set_column_spacing(10)
        grid_theme_rest.set_margin_start(10)
        grid_theme_rest.set_margin_end(10)
        grid_theme_rest.set_margin_bottom(10)

        grid_support = Gtk.Grid()
        grid_support.set_column_homogeneous(True)
        grid_support.set_row_spacing(10)
        grid_support.set_column_spacing(10)
        grid_support.set_margin_start(10)
        grid_support.set_margin_end(10)
        grid_support.set_margin_top(10)
        grid_support.set_margin_bottom(10)
        grid_support.set_vexpand(True)
        grid_support.set_valign(Gtk.Align.END)

        grid_backup = Gtk.Grid()
        grid_backup.set_column_homogeneous(True)
        grid_backup.set_row_spacing(10)
        grid_backup.set_column_spacing(10)
        grid_backup.set_margin_start(10)
        grid_backup.set_margin_end(10)
        grid_backup.set_margin_top(10)
        grid_backup.set_margin_bottom(10)
        grid_backup.set_vexpand(True)
        grid_backup.set_valign(Gtk.Align.END)

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

        box_buttons.append(self.button_winetricks_default)
        box_buttons.append(self.button_winecfg_default)
        box_buttons.append(self.button_run_default)

        grid_tools.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        grid_tools.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        grid_tools.attach(self.checkbox_prevent_sleep, 0, 2, 1, 1)
        grid_tools.attach(self.checkbox_disable_hidraw, 0, 3, 1, 1)
        grid_tools.attach(box_buttons, 2, 0, 1, 4)

        grid_logs.attach(self.checkbox_enable_logging, 0, 0, 1, 1)
        grid_logs.attach(self.button_clearlogs, 0, 1, 1, 1)
        self.button_clearlogs.set_hexpand(True)

        grid_miscellaneous.attach(self.label_miscellaneous, 0, 0, 1, 1)
        grid_miscellaneous.attach(self.checkbox_discrete_gpu, 0, 1, 1, 1)
        grid_miscellaneous.attach(self.checkbox_splash_disable, 0, 2, 1, 1)
        grid_miscellaneous.attach(self.checkbox_disable_updates, 0, 3, 1, 1)
        grid_miscellaneous.attach(self.checkbox_close_after_launch, 0, 4, 1, 1)
        grid_miscellaneous.attach(self.checkbox_gamepad_navigation, 0, 5, 1, 1)
        grid_miscellaneous.attach(self.checkbox_start_boot, 0, 6, 1, 1)
        grid_miscellaneous.attach(self.checkbox_system_tray, 0, 7, 1, 1)
        grid_miscellaneous.attach(self.checkbox_start_minimized, 0, 8, 1, 1)
        grid_miscellaneous.attach(self.checkbox_mono_icon, 0, 9, 1, 1)
        grid_miscellaneous.attach(self.checkbox_wayland_driver, 0, 10, 1, 1)
        grid_miscellaneous.attach(self.checkbox_enable_wow64, 0, 11, 1, 1)

        grid_theme_accent.attach(self.label_ui_customization, 0, 0, 1, 1)

        grid_theme_accent.attach(self.label_interface, 0, 1, 1, 1)
        grid_theme_accent.attach(self.combobox_interface, 0, 2, 1, 1)
        self.combobox_interface.set_hexpand(True)

        grid_theme_rest.attach(self.label_theme, 0, 0, 1, 1)
        grid_theme_rest.attach(self.combobox_theme, 0, 1, 1, 1)
        self.combobox_theme.set_hexpand(True)
        grid_theme_rest.attach(self.label_accent, 0, 2, 1, 1)
        grid_theme_rest.attach(self.box_accent, 0, 3, 1, 1)
        self.combobox_accent.set_hexpand(True)

        grid_theme_rest.attach(self.label_background, 0, 4, 1, 1)
        grid_theme_rest.attach(self.combobox_background, 0, 5, 1, 1)
        self.combobox_background.set_hexpand(True)

        grid_theme_rest.attach(self.checkbox_show_categories, 0, 6, 1, 1)
        grid_theme_rest.attach(self.checkbox_show_hidden, 0, 7, 1, 1)

        grid_envar.attach(self.label_envar, 0, 0, 1, 1)
        grid_envar.attach(scrolled_window, 0, 1, 1, 1)
        scrolled_window.set_hexpand(True)

        grid_backup.attach(self.label_settings, 0, 0, 2, 1)
        grid_backup.attach(button_backup, 0, 1, 1, 1)
        grid_backup.attach(button_restore, 1, 1, 1, 1)

        self.grid_big_interface.attach(self.label_steamgriddb_key, 0, 0, 1, 1)
        self.grid_big_interface.attach(self.entry_steamgriddb_key, 0, 1, 1, 1)
        self.grid_big_interface.attach(self.label_window_behavior, 0, 2, 1, 1)
        self.grid_big_interface.attach(self.combobox_window_behavior, 0, 3, 1, 1)
        self.grid_big_interface.attach(self.checkbox_show_labels, 0, 4, 1, 1)
        self.grid_big_interface.attach(self.checkbox_hero_background, 0, 5, 1, 1)
        self.combobox_window_behavior.set_hexpand(True)
        self.entry_steamgriddb_key.set_hexpand(True)

        grid_support.attach(self.label_support, 0, 0, 2, 1)
        grid_support.attach(button_kofi, 0, 1, 1, 1)
        grid_support.attach(button_paypal, 1, 1, 1, 1)

        box_left.append(grid_prefix)
        box_left.append(grid_runner)
        box_left.append(self.label_default_prefix_tools)
        box_left.append(grid_tools)
        box_left.append(grid_lossless)
        box_left.append(grid_logs)
        box_left.append(grid_language)

        box_mid.append(grid_envar)
        box_mid.append(grid_miscellaneous)
        box_mid.append(grid_backup)

        box_right.append(grid_theme_accent)
        box_right.append(self.grid_big_interface)
        box_right.append(grid_theme_rest)
        box_right.append(grid_support)

        box_main.attach(box_left, 0, 0, 1, 1)
        box_main.attach(box_right, 1, 0, 1, 1)
        box_main.attach(box_mid, 2, 0, 1, 1)
        box_left.set_hexpand(True)
        box_mid.set_hexpand(True)
        frame.set_child(box_main)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_homogeneous(True)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        box_bottom.append(self.button_cancel)
        box_bottom.append(self.button_ok)

        self.box.append(frame)
        self.box.append(box_bottom)

        self.populate_combobox_with_runners()
        self.populate_languages()
        self.load_config()

        self.on_combobox_interface_changed(self.combobox_interface)

        disable_mangohud_gamemode_if_missing(self)
        self.track_modifications(self.box)

    def on_envar_key_press(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Delete:
            widget = controller.get_widget()
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
                if find_mo_file(LOCALE_DIR, lang, "faugus-launcher"):
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
            self.label_steamgriddb_key.set_visible(False)
            self.entry_steamgriddb_key.set_visible(False)
            self.checkbox_hero_background.set_visible(False)
        if active_id == "Banners":
            self.grid_big_interface.set_visible(True)
            self.checkbox_show_labels.set_visible(True)
            self.label_steamgriddb_key.set_visible(False)
            self.entry_steamgriddb_key.set_visible(False)
            self.checkbox_hero_background.set_visible(False)
        if active_id == "SteamGridDB":
            self.grid_big_interface.set_visible(True)
            self.checkbox_show_labels.set_visible(True)
            self.label_steamgriddb_key.set_visible(True)
            self.entry_steamgriddb_key.set_visible(True)
            self.checkbox_hero_background.set_visible(True)

    def on_theme_accent_changed(self, widget):
        self.color_button.set_sensitive(self.combobox_accent.get_active_id() == "custom")

        self.interface_theme = self.combobox_theme.get_active_id() or "system"
        if self.combobox_accent.get_active_id() == "custom":
            self.accent_color = self.color_button.get_rgba().to_string()
        else:
            self.accent_color = "system"

        apply_interface_customization(self.interface_theme, self.accent_color)

        if hasattr(self.parent, 'schedule_background_update'):
            self.parent.schedule_background_update()

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
        config.set_value("background-mode", self.combobox_background.get_active_id())
        config.set_value("hero-enabled", self.checkbox_hero_background.get_active())
        config.set_value("show-labels", self.checkbox_show_labels.get_active())
        config.set_value("steamgriddb-api-key", self.entry_steamgriddb_key.get_text().strip())
        config.set_value("logging-warning", logging_warning)
        config.set_value("gamepad-navigation", self.checkbox_gamepad_navigation.get_active())
        config.set_value("start-minimized", self.checkbox_start_minimized.get_active())
        config.set_value("show-categories", self.checkbox_show_categories.get_active())
        config.set_value("window-behavior", self.combobox_window_behavior.get_active_id())
        config.set_value("interface-theme", self.interface_theme)
        config.set_value("accent-color", self.accent_color)
        config.save_config()

        self.set_sensitive(False)

    def get_default_runner(self):
        default_runner = self.combobox_runner.get_active_text()
        default_runner = convert_runner(default_runner)
        return default_runner

    def update_envar_file(self):
        if hasattr(self, "liststore"):
            values = [row[0] for row in self.liststore if row[0].strip() != ""]
            save_json_file(values, envar_dir)

    def on_button_proton_manager_clicked(self, widget):
        current_runner = self.combobox_runner.get_active_text()

        from faugus.proton_manager import ProtonDownloader
        dialog = ProtonDownloader()
        dialog.set_transient_for(self)

        def on_response(dialog, response_id):
            dialog.closed_event.set()
            destroy_and_release(dialog)

            self.combobox_runner.remove_all()
            self.populate_combobox_with_runners()

            if current_runner:
                for i, text in enumerate(self.combobox_runner.get_texts()):
                    if text == current_runner:
                        self.combobox_runner.set_active(i)
                        break

        dialog.connect("response", on_response)
        dialog.present()

    def track_modifications(self, container):
        for child in widget_children(container):
            if isinstance(child, Gtk.Entry):
                child.connect("changed", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.CheckButton):
                child.connect("toggled", lambda w: setattr(self, "modified", True))
            elif isinstance(child, IdComboBox):
                child.connect("changed", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.TreeView):
                selection = child.get_selection()
                selection.connect("changed", lambda sel: setattr(self, "modified", True))
            else:
                self.track_modifications(child)

    def check_modified(self, callback=None):
        self.track_modifications(self.box)
        if not self.modified:
            if callback:
                callback()
            return

        def on_proceed(proceed):
            if proceed:
                if self.entry_default_prefix.get_text() == "":
                    self.entry_default_prefix.add_css_class("entry")
                    return
                apply_interface_customization(self.interface_theme, self.accent_color)
                self.update_envar_file()
                self.update_config_file()
                self.parent.manage_autostart_file(self.checkbox_start_boot.get_active(), self.checkbox_start_minimized.get_active())
                new_system_tray = self.checkbox_system_tray.get_active()
                new_mono_icon = self.checkbox_mono_icon.get_active()
                tray_needs_reload = (
                    self.parent.system_tray != new_system_tray or
                    self.parent.mono_icon != new_mono_icon
                )
                self.parent.system_tray = new_system_tray
                self.parent.mono_icon = new_mono_icon
                if tray_needs_reload:
                    self.parent.load_tray_icon()
            else:
                self.load_config()

            self.modified = False
            if callback:
                callback()

        self.show_warning_dialog_settings(self.parent, _("Do you want to save the changes?"), True, on_proceed)

    def on_button_winetricks_default_clicked(self, widget):
        def proceed():
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
                process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command, "winetricks"], env=subprocess_env())
                process.wait()
                GLib.idle_add(self.set_sensitive, True)

            run_in_background(run_command)

        self.check_modified(proceed)

    def on_button_winecfg_default_clicked(self, widget):
        def proceed():
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
                process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command], env=subprocess_env())
                process.wait()
                GLib.idle_add(self.set_sensitive, True)

            run_in_background(run_command)

        self.check_modified(proceed)

    def on_button_run_default_clicked(self, widget):
        def proceed():
            default_runner = self.get_default_runner()

            filechooser = new_file_chooser(
                self,
                _("Select a file to run inside the prefix"),
                Gtk.FileChooserAction.OPEN,
            )
            set_file_chooser_start_folder(filechooser, "run_in_prefix")

            add_windows_file_filters(filechooser)

            def on_response(dialog_fc, response):
                if response == Gtk.ResponseType.ACCEPT:
                    file_run = dialog_fc.get_file().get_path()
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
                        process = subprocess.Popen(cmd, cwd=cwd if cwd else None, env=subprocess_env())
                        process.wait()

                    run_in_background(run_command)
                else:
                    self.set_sensitive(True)

                destroy_and_release(dialog_fc)

            filechooser.connect("response", on_response)
            filechooser.present()

        self.check_modified(proceed)

    def on_button_backup_clicked(self, widget):
        def proceed():
            from faugus.backup import BackupWindow

            backup_win = BackupWindow(self.parent)
            backup_win.present()

        self.check_modified(proceed)

    def on_button_restore_clicked(self, widget):
        filechooser = new_file_chooser(
            self,
            _("Select a backup file to restore"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "restore_backup")

        zip_filter = Gtk.FileFilter()
        zip_filter.set_name(_("ZIP files"))
        zip_filter.add_pattern("*.zip")
        filechooser.add_filter(zip_filter)
        filechooser.set_filter(zip_filter)

        def on_fc_response(dialog_fc, response):
            if response != Gtk.ResponseType.ACCEPT:
                destroy_and_release(dialog_fc)
                return

            zip_file = dialog_fc.get_file().get_path()
            destroy_and_release(dialog_fc)

            if not os.path.isfile(zip_file):
                self.show_warning_dialog_settings(
                    self, _("This is not a valid Faugus backup file."), False, lambda ok: None)
                return

            temp_dir = os.path.join(faugus_temp, "temp-restore")
            shutil.unpack_archive(zip_file, temp_dir, "zip")

            marker_path = os.path.join(temp_dir, ".faugus_marker")
            if not os.path.exists(marker_path):
                shutil.rmtree(temp_dir)
                self.show_warning_dialog_settings(
                    self, _("This is not a valid Faugus backup file."), False, lambda ok: None)
                return

            def on_confirm(ok):
                if not ok:
                    return

                for item in os.listdir(temp_dir):
                    if item == ".faugus_marker":
                        continue
                    src = os.path.join(temp_dir, item)

                    dst = BACKUP_ITEMS.get(item)
                    if dst is None:
                        legacy = LEGACY_FORMAT_ITEMS.get(item)
                        if legacy is None:
                            continue
                        dst, kind = legacy
                        convert_legacy_format_file(src, dst, kind)
                        continue

                    os.makedirs(os.path.dirname(dst), exist_ok=True)

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

            self.show_warning_dialog_settings(
                self, _("Are you sure you want to overwrite the settings?"), True, on_confirm)

        filechooser.connect("response", on_fc_response)
        filechooser.present()

    def show_warning_dialog_settings(self, parent, title, buttons, callback):
        show_message_dialog(
            title,
            parent=parent,
            confirm_label=_("Yes") if buttons else _("Ok"),
            cancel_label=_("No") if buttons else None,
            callback=callback,
        )

    def on_button_search_prefix_clicked(self, widget):
        filechooser = new_file_chooser(
            self,
            _("Select a prefix location"),
            Gtk.FileChooserAction.SELECT_FOLDER,
        )
        entry_value = self.entry_default_prefix.get_text()
        preferred_path = os.path.expanduser(entry_value) if entry_value else None
        set_file_chooser_start_folder(filechooser, "settings_default_prefix", preferred_path)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                folder = dialog_fc.get_file().get_path()
                if folder:
                    self.entry_default_prefix.set_text(folder)
            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_button_search_lossless_clicked(self, widget):
        filechooser = new_file_chooser(
            self,
            _("Select the Lossless.dll file"),
            Gtk.FileChooserAction.OPEN,
        )
        entry_value = self.entry_lossless.get_text()
        preferred_path = os.path.expanduser(entry_value) if entry_value else None
        set_file_chooser_start_folder(filechooser, "settings_lossless", preferred_path)

        filter_dll = Gtk.FileFilter()
        filter_dll.set_name("Lossless.dll")
        filter_dll.add_pattern("Lossless.dll")
        filechooser.add_filter(filter_dll)
        filechooser.set_filter(filter_dll)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                selected_file = dialog_fc.get_file().get_path()
                if selected_file and os.path.basename(selected_file) == "Lossless.dll":
                    self.entry_lossless.set_text(selected_file)
            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

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
        background_mode = cfg.config.get('background-mode', 'default').strip('"')
        hero_enabled = cfg.config.get('hero-enabled', 'True') == 'True'
        show_labels = cfg.config.get('show-labels', 'False') == 'True'
        steamgriddb_api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
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
        self.interface_theme = cfg.config.get('interface-theme', 'system')
        self.accent_color = cfg.config.get('accent-color', 'system')
        self.original_interface_theme = self.interface_theme
        self.original_accent_color = self.accent_color

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
        index_runner = 0
        for i, text in enumerate(self.combobox_runner.get_texts()):
            if text == self.default_runner:
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
        self.entry_steamgriddb_key.set_text(steamgriddb_api_key)
        self.checkbox_enable_logging.set_active(enable_logging)
        self.checkbox_show_hidden.set_active(show_hidden)
        self.checkbox_gamepad_navigation.set_active(gamepad_navigation)
        self.checkbox_wayland_driver.set_active(wayland_driver)
        self.checkbox_enable_wow64.set_active(enable_wow64)
        self.combobox_interface.set_active_id(self.interface_mode)
        self.combobox_background.set_active_id(background_mode)
        self.checkbox_hero_background.set_active(hero_enabled)

        loaded_theme = self.interface_theme
        loaded_accent = self.accent_color

        is_custom_accent = loaded_accent not in (None, "", "system")
        rgba = Gdk.RGBA()
        rgba.parse(loaded_accent if is_custom_accent else "#3daee9")
        self.color_button.set_rgba(rgba)
        self.color_button.set_sensitive(is_custom_accent)

        self.combobox_theme.set_active_id(loaded_theme)
        self.combobox_accent.set_active_id("custom" if is_custom_accent else "system")

        self.interface_theme = loaded_theme
        self.accent_color = loaded_accent

        self.checkbox_start_minimized.set_active(start_minimized)
        self.checkbox_show_categories.set_active(show_categories)
        self.combobox_window_behavior.set_active_id(window_behavior)

        index_language = 0

        if self.language == "":
            self.combobox_language.set_active(index_language)
        else:
            language_primary = self.language.split("_")[0].split("-")[0].lower()
            for i, lang_name in enumerate(self.combobox_language.get_texts()):
                lang_code = self.lang_codes.get(lang_name, "")
                if lang_code == self.language or lang_code.lower() == language_primary:
                    index_language = i
                    break

            self.combobox_language.set_active(index_language)
        self.load_liststore_from_file(envar_dir)

    def load_liststore_from_file(self, filename=envar_dir):
        self.liststore.clear()

        lines = [line.strip() for line in load_json_file(filename, default=[]) if line.strip()]

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
        steamgriddb_id="",
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
        self.steamgriddb_id = steamgriddb_id


class DuplicateDialog(Gtk.Dialog):
    def __init__(self, parent, title):
        super().__init__(title=_("Duplicate %s") % title, transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        label_title = Gtk.Label(label=_("Title"))
        label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.set_tooltip_text(_("Game Title"))

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        button_cancel.set_hexpand(True)

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        button_ok.set_hexpand(True)

        content_area = self.get_content_area()
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
        box_bottom.set_homogeneous(True)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.append(label_title)
        box_top.append(self.entry_title)

        box_bottom.append(button_cancel)
        box_bottom.append(button_ok)

        content_area.append(box_top)
        content_area.append(box_bottom)

        self.present()


class DeleteDialog(Gtk.Dialog):
    def __init__(self, parent, title, prefix, runner):
        super().__init__(title=_("Delete %s") % title, transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)
        play_notification_sound()

        label = Gtk.Label()
        label.set_label(_("Are you sure you want to delete %s?") % title)
        label.set_halign(Gtk.Align.CENTER)

        prefix_label = Gtk.Label()
        prefix_label.set_label(prefix)
        prefix_label.set_halign(Gtk.Align.CENTER)

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
        button_no.set_hexpand(True)
        button_no.connect("clicked", lambda x: self.response(Gtk.ResponseType.NO))

        button_yes = Gtk.Button(label=_("Yes"))
        button_yes.set_hexpand(True)
        button_yes.connect("clicked", lambda x: self.response(Gtk.ResponseType.YES))

        self.checkbox = Gtk.CheckButton(label=_("Also remove the prefix:"))
        self.checkbox.set_halign(Gtk.Align.CENTER)

        content_area = self.get_content_area()
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
        box_bottom.set_homogeneous(True)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.append(label)
        if os.path.basename(prefix) != "default" and runner != "Linux-Native" and runner != "Steam":
            box_top.append(self.checkbox)
            box_top.append(prefix_label)
            if pfx_count > 0:
                box_top.append(warn_label)

        box_bottom.append(button_no)
        box_bottom.append(button_yes)

        content_area.append(box_top)
        content_area.append(box_bottom)

        self.present()


class AddGame(Gtk.Dialog, HiDpiMixin):
    def __init__(self, parent, interface_mode):
        super().__init__(title=_("New Game/App"), transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        self.closed_event = threading.Event()

        self.parent_window = parent
        self.interface_mode = interface_mode

        init_addon_defaults(self)

        if not os.path.exists(banners_dir):
            os.makedirs(banners_dir)

        if not os.path.exists(heroes_dir):
            os.makedirs(heroes_dir)

        self.banner_path_temp = os.path.join(banners_dir, "banner_temp.png")
        if os.path.isfile(self.banner_path_temp):
            os.remove(self.banner_path_temp)
        self.hero_path_temp = os.path.join(banners_dir, "hero_temp.png")
        if os.path.isfile(self.hero_path_temp):
            os.remove(self.hero_path_temp)
        self.icon_directory = f"{icons_dir}/icon_temp/"

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        self.icons_path = icons_dir
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.png'

        self.box = self.get_content_area()
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)
        self.content_area = self.get_content_area()
        self.content_area.set_halign(Gtk.Align.CENTER)
        self.content_area.set_valign(Gtk.Align.CENTER)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)

        box_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_buttons.set_valign(Gtk.Align.CENTER)

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

        self.grid_shortcut = Gtk.Grid()
        self.grid_shortcut.set_row_spacing(10)
        self.grid_shortcut.set_column_spacing(10)
        self.grid_shortcut.set_margin_start(10)
        self.grid_shortcut.set_margin_end(10)
        self.grid_shortcut.set_margin_top(10)
        self.grid_shortcut.set_margin_bottom(10)

        self.grid_shortcut_icon = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)

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

        add_css_once("addgame_dialog", """
        .entry {
            border: 1px solid red;
        }
        .combobox {
            border: 1px solid red;
        }
        .add-game-banner {
            border-radius: 12px;
        }
        .suggestion-popover list,
        .suggestion-popover row {
            background: transparent;
        }
        .suggestion-popover row:hover {
            background-color: alpha(@accent_bg_color, 0.15);
        }
        .suggestion-popover row:active {
            background-color: alpha(@accent_bg_color, 0.25);
        }
        """, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.combobox_launcher = IdComboBox()

        self.label_steam_title = Gtk.Label(label=_("Title"))
        self.label_steam_title.set_halign(Gtk.Align.START)
        self.combobox_steam_title = IdComboBox()
        self.combobox_steam_title.append(None, "")

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
        self.entry_title.connect("changed", on_entry_changed)
        if interface_mode in ("Banners", "SteamGridDB"):
            title_focus_controller = Gtk.EventControllerFocus()
            title_focus_controller.connect("leave", lambda c: self.on_entry_focus_out())
            self.entry_title.add_controller(title_focus_controller)
        self.entry_title.set_tooltip_text(_("Game Title"))
        self.entry_title.set_has_tooltip(True)
        self.entry_title.connect("query-tooltip", on_entry_query_tooltip)

        self._steamgriddb_suggestion_id = None
        self._steamgriddb_steam_appid = None
        self._suggestion_source = None
        self._suggestion_programmatic = False

        if interface_mode == "SteamGridDB":
            self.suggestion_popover = Gtk.Popover()
            self.suggestion_popover.set_has_arrow(False)
            self.suggestion_popover.set_autohide(False)
            self.suggestion_popover.add_css_class("suggestion-popover")
            self.suggestion_popover.set_parent(self.entry_title)

            self.suggestion_listbox = Gtk.ListBox()
            self.suggestion_listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            self.suggestion_listbox.connect("row-activated", self.on_suggestion_row_activated)

            suggestion_scroll = Gtk.ScrolledWindow()
            suggestion_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            suggestion_scroll.set_max_content_height(250)
            suggestion_scroll.set_propagate_natural_height(True)
            suggestion_scroll.set_size_request(300, -1)
            suggestion_scroll.set_child(self.suggestion_listbox)

            self.suggestion_popover.set_child(suggestion_scroll)

            self.entry_title.connect("changed", self.on_title_changed_for_suggestions)

            title_key_controller = Gtk.EventControllerKey()
            title_key_controller.connect("key-pressed", self.on_title_key_pressed)
            self.entry_title.add_controller(title_key_controller)

            title_suggestion_focus_controller = Gtk.EventControllerFocus()
            title_suggestion_focus_controller.connect("leave", lambda c: self.on_title_focus_leave_for_suggestions())
            self.entry_title.add_controller(title_suggestion_focus_controller)

            suggestion_click_outside_controller = Gtk.GestureClick()
            suggestion_click_outside_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            suggestion_click_outside_controller.connect("pressed", self.on_dialog_click_for_suggestions)
            self.add_controller(suggestion_click_outside_controller)

        self.label_path = Gtk.Label(label=_("Path"))
        self.label_path.set_halign(Gtk.Align.START)
        self.entry_path = Gtk.Entry()
        self.entry_path.connect("changed", on_entry_changed)
        self.entry_path.set_tooltip_text(_("/path/to/the/exe"))
        self.entry_path.set_has_tooltip(True)
        self.entry_path.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search = Gtk.Button()
        self.button_search.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search.connect("clicked", self.on_button_search_clicked)
        self.button_search.set_size_request(50, -1)

        self.label_prefix = Gtk.Label(label=_("Prefix"))
        self.label_prefix.set_halign(Gtk.Align.START)
        self.entry_prefix = Gtk.Entry()
        self.entry_prefix.connect("changed", on_entry_changed)
        self.entry_prefix.set_tooltip_text(_("/path/to/the/prefix"))
        self.entry_prefix.set_has_tooltip(True)
        self.entry_prefix.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        self.label_runner = Gtk.Label(label=_("Proton"))
        self.label_runner.set_halign(Gtk.Align.START)
        self.combobox_runner = IdComboBox()

        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.entry_protonfix.set_has_tooltip(True)
        self.entry_protonfix.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_child(
            Gtk.Image.new_from_icon_name("system-search-symbolic"))
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
        self.button_shortcut_icon.connect(
            "clicked",
            lambda w: self.on_button_shortcut_icon_clicked(w)
            if self.interface_mode != "SteamGridDB"
            else show_steamgriddb_picker(self, "icon")
        )
        self.button_shortcut_icon.set_tooltip_text(_("Select an icon for the shortcut"))
        self.button_shortcut_icon_overlay, self.spinner_icon = wrap_with_spinner(self.button_shortcut_icon, dim_shape="icon")

        icon_click_secondary = Gtk.GestureClick()
        icon_click_secondary.set_button(Gdk.BUTTON_SECONDARY)
        if interface_mode == "SteamGridDB":
            icon_click_secondary.connect("pressed", lambda g, n, x, y: self.on_image_clicked(g, n, x, y, "icon"))
        else:
            icon_click_secondary.connect("pressed", lambda g, n, x, y: self.on_button_shortcut_icon_clicked(self.button_shortcut_icon))
        self.button_shortcut_icon.add_controller(icon_click_secondary)

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        self.button_cancel.set_hexpand(True)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        self.button_ok.set_hexpand(True)

        self.load_config()

        self.entry_title.connect("changed", self.update_prefix_entry)

        self.notebook = Gtk.Notebook()
        self.notebook.set_margin_start(10)
        self.notebook.set_margin_end(10)
        self.notebook.set_margin_top(10)
        self.notebook.set_margin_bottom(10)

        self.box.append(self.notebook)

        self.image_banner = new_picture()
        self.image_banner.set_margin_top(10)
        self.image_banner.set_margin_bottom(10)
        self.image_banner.set_margin_start(10)
        self.image_banner.set_margin_end(10)
        self.image_banner.set_vexpand(True)
        self.image_banner.set_valign(Gtk.Align.CENTER)
        self.image_banner.add_css_class("add-game-banner")
        self.image_banner.set_overflow(Gtk.Overflow.HIDDEN)

        self.image_banner2 = new_picture()
        self.image_banner2.set_margin_top(10)
        self.image_banner2.set_margin_bottom(10)
        self.image_banner2.set_margin_start(10)
        self.image_banner2.set_margin_end(10)
        self.image_banner2.set_vexpand(True)
        self.image_banner2.set_valign(Gtk.Align.CENTER)
        self.image_banner2.add_css_class("add-game-banner")
        self.image_banner2.set_overflow(Gtk.Overflow.HIDDEN)

        self.hero_picture1 = Gtk.Picture()
        self.hero_picture1.set_can_shrink(True)
        self.hero_picture1.set_content_fit(Gtk.ContentFit.COVER)
        self.hero_picture1.set_hexpand(True)
        self.hero_picture1.set_vexpand(True)

        hero_placeholder1 = Gtk.Box()
        hero_placeholder1.add_css_class("hero-placeholder")
        hero_placeholder1.set_hexpand(True)
        hero_placeholder1.set_vexpand(True)

        self.hero_preview_stack1 = Gtk.Stack()
        self.hero_preview_stack1.set_hhomogeneous(False)
        self.hero_preview_stack1.set_vhomogeneous(False)
        self.hero_preview_stack1.set_transition_type(Gtk.StackTransitionType.NONE)
        self.hero_preview_stack1.set_hexpand(True)
        self.hero_preview_stack1.set_vexpand(True)
        self.hero_preview_stack1.add_named(hero_placeholder1, "placeholder")
        self.hero_preview_stack1.add_named(self.hero_picture1, "picture")
        self.hero_preview_stack1.set_visible_child_name("placeholder")

        self.hero_preview1 = Gtk.AspectFrame.new(0.5, 0.5, 1920 / 620, False)
        self.hero_preview1.set_child(self.hero_preview_stack1)
        self.hero_preview1.set_hexpand(True)

        self.hero_picture2 = Gtk.Picture()
        self.hero_picture2.set_can_shrink(True)
        self.hero_picture2.set_content_fit(Gtk.ContentFit.COVER)
        self.hero_picture2.set_hexpand(True)
        self.hero_picture2.set_vexpand(True)

        hero_placeholder2 = Gtk.Box()
        hero_placeholder2.add_css_class("hero-placeholder")
        hero_placeholder2.set_hexpand(True)
        hero_placeholder2.set_vexpand(True)

        self.hero_preview_stack2 = Gtk.Stack()
        self.hero_preview_stack2.set_hhomogeneous(False)
        self.hero_preview_stack2.set_vhomogeneous(False)
        self.hero_preview_stack2.set_transition_type(Gtk.StackTransitionType.NONE)
        self.hero_preview_stack2.set_hexpand(True)
        self.hero_preview_stack2.set_vexpand(True)
        self.hero_preview_stack2.add_named(hero_placeholder2, "placeholder")
        self.hero_preview_stack2.add_named(self.hero_picture2, "picture")
        self.hero_preview_stack2.set_visible_child_name("placeholder")

        self.hero_preview2 = Gtk.AspectFrame.new(0.5, 0.5, 1920 / 620, False)
        self.hero_preview2.set_child(self.hero_preview_stack2)
        self.hero_preview2.set_hexpand(True)

        self.image_banner.set_hexpand(True)
        self.image_banner_stack = wrap_with_replaceable_placeholder(self.image_banner, 260, 390)

        self.image_banner2.set_hexpand(True)
        self.image_banner2_stack = wrap_with_replaceable_placeholder(self.image_banner2, 260, 390)

        image_click1 = Gtk.GestureClick()
        image_click1.set_button(Gdk.BUTTON_SECONDARY)
        image_click1.connect("pressed", self.on_image_clicked)
        self.image_banner_stack.add_controller(image_click1)

        image_click2 = Gtk.GestureClick()
        image_click2.set_button(Gdk.BUTTON_SECONDARY)
        image_click2.connect("pressed", self.on_image_clicked)
        self.image_banner2_stack.add_controller(image_click2)

        def on_grid_primary_click(gesture, n_press, x, y):
            if self.interface_mode == "SteamGridDB":
                show_steamgriddb_picker(self, "grid")

        image_click1_primary = Gtk.GestureClick()
        image_click1_primary.set_button(Gdk.BUTTON_PRIMARY)
        image_click1_primary.connect("pressed", on_grid_primary_click)
        self.image_banner_stack.add_controller(image_click1_primary)

        image_click2_primary = Gtk.GestureClick()
        image_click2_primary.set_button(Gdk.BUTTON_PRIMARY)
        image_click2_primary.connect("pressed", on_grid_primary_click)
        self.image_banner2_stack.add_controller(image_click2_primary)

        self.image_banner_overlay, self.spinner_grid1 = wrap_with_spinner(self.image_banner_stack, dim_shape="banner")
        self.image_banner2_overlay, self.spinner_grid2 = wrap_with_spinner(self.image_banner2_stack, dim_shape="banner")

        self.hero_preview1_overlay, self.spinner_hero1 = wrap_with_spinner(self.hero_preview1)
        self.hero_preview2_overlay, self.spinner_hero2 = wrap_with_spinner(self.hero_preview2)

        hero_click1 = Gtk.GestureClick()
        hero_click1.set_button(Gdk.BUTTON_PRIMARY)
        hero_click1.connect("pressed", lambda g, n, x, y: show_steamgriddb_picker(self, "hero"))
        self.hero_preview1.add_controller(hero_click1)

        hero_click2 = Gtk.GestureClick()
        hero_click2.set_button(Gdk.BUTTON_PRIMARY)
        hero_click2.connect("pressed", lambda g, n, x, y: show_steamgriddb_picker(self, "hero"))
        self.hero_preview2.add_controller(hero_click2)

        hero_click_secondary1 = Gtk.GestureClick()
        hero_click_secondary1.set_button(Gdk.BUTTON_SECONDARY)
        hero_click_secondary1.connect("pressed", lambda g, n, x, y: self.on_image_clicked(g, n, x, y, "hero"))
        self.hero_preview1.add_controller(hero_click_secondary1)

        hero_click_secondary2 = Gtk.GestureClick()
        hero_click_secondary2.set_button(Gdk.BUTTON_SECONDARY)
        hero_click_secondary2.connect("pressed", lambda g, n, x, y: self.on_image_clicked(g, n, x, y, "hero"))
        self.hero_preview2.add_controller(hero_click_secondary2)

        self.menu = Gtk.Popover()
        self.menu.set_has_arrow(False)
        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        menu_box.set_margin_start(6)
        menu_box.set_margin_end(6)
        menu_box.set_margin_top(6)
        menu_box.set_margin_bottom(6)
        self.menu.set_child(menu_box)

        def menu_button(label):
            btn = Gtk.Button(label=label)
            btn.set_has_frame(False)
            btn.get_child().set_halign(Gtk.Align.START)
            menu_box.append(btn)
            return btn

        refresh_item = menu_button(_("Refresh"))
        refresh_item.connect("clicked", self.on_refresh)

        load_item = menu_button(_("Load from file"))
        load_item.connect("clicked", self.on_load_file)

        load_url = menu_button(_("Load from URL"))
        load_url.connect("clicked", self.on_load_url)

        page1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.tab_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label1 = Gtk.Label(label=_("Game/App"))
        tab_label1.set_width_chars(8)
        tab_label1.set_xalign(0.5)
        tab_label1.set_hexpand(True)
        self.tab_box1.append(tab_label1)
        self.tab_box1.set_hexpand(True)

        if interface_mode == "SteamGridDB":
            self.grid_page1.attach(self.hero_preview1_overlay, 0, 0, 2, 1)
        self.grid_page1.attach(page1, 0, 1, 1, 1)
        if interface_mode in ("Banners", "SteamGridDB"):
            self.grid_page1.attach(self.image_banner_overlay, 1, 1, 1, 1)
        page1.set_hexpand(True)
        self.image_banner.set_hexpand(True)

        self.notebook.append_page(self.grid_page1, self.tab_box1)

        page2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.tab_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label2 = Gtk.Label(label=_("Tools"))
        tab_label2.set_width_chars(8)
        tab_label2.set_xalign(0.5)
        tab_label2.set_hexpand(True)
        self.tab_box2.append(tab_label2)
        self.tab_box2.set_hexpand(True)

        if interface_mode == "SteamGridDB":
            self.grid_page2.attach(self.hero_preview2_overlay, 0, 0, 2, 1)
        self.grid_page2.attach(page2, 0, 1, 1, 1)
        if interface_mode in ("Banners", "SteamGridDB"):
            self.grid_page2.attach(self.image_banner2_overlay, 1, 1, 1, 1)
        page2.set_hexpand(True)
        self.image_banner2.set_hexpand(True)

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
        self.grid_shortcut.attach(self.checkbox_shortcut_desktop, 0, 0, 1, 1)
        self.checkbox_shortcut_desktop.set_hexpand(True)
        self.grid_shortcut.attach(self.checkbox_shortcut_appmenu, 0, 1, 1, 1)
        self.checkbox_shortcut_appmenu.set_hexpand(True)
        self.grid_shortcut.attach(self.checkbox_shortcut_steam, 0, 2, 1, 1)
        self.checkbox_shortcut_steam.set_hexpand(True)
        self.grid_shortcut_icon.append(self.button_shortcut_icon_overlay)
        self.grid_shortcut.attach(self.grid_shortcut_icon, 2, 0, 1, 3)

        page1.append(self.grid_launcher)
        page1.append(self.grid_steam_title)
        page1.append(self.grid_title)
        page1.append(self.grid_path)
        page1.append(self.grid_prefix)
        page1.append(self.grid_runner)
        page1.append(self.label_shortcut)
        page1.append(self.grid_shortcut)

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

        box_buttons.append(self.button_winetricks)
        box_buttons.append(self.button_winecfg)
        box_buttons.append(self.button_run)

        self.grid_tools.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        self.checkbox_gamemode.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_prevent_sleep, 0, 2, 1, 1)
        self.checkbox_prevent_sleep.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_disable_hidraw, 0, 3, 1, 1)
        self.checkbox_disable_hidraw.set_hexpand(True)
        self.grid_tools.attach(box_buttons, 2, 0, 1, 4)

        page2.append(self.grid_protonfix)
        page2.append(self.grid_game_arguments)
        page2.append(self.grid_launch_arguments)
        page2.append(self.grid_addapp)
        page2.append(self.grid_lossless)
        page2.append(self.grid_tools)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_homogeneous(True)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)
        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        bottom_box.append(self.button_cancel)
        bottom_box.append(self.button_ok)

        self.box.append(bottom_box)

        self.populate_combobox_with_launchers()
        self.combobox_launcher.set_active_id("windows")
        self.combobox_launcher.connect("changed", self.on_combobox_changed)

        self.populate_combobox_with_runners()

        index_to_activate = 0

        self.default_runner = convert_runner(self.default_runner)

        for i, text in enumerate(self.combobox_runner.get_texts()):
            if text == self.default_runner:
                index_to_activate = i
                break
        self.combobox_runner.set_active(index_to_activate)

        self.checkbox_mangohud.set_active(self.default_mangohud)
        self.checkbox_gamemode.set_active(self.default_gamemode)
        self.checkbox_prevent_sleep.set_active(self.default_prevent_sleep)
        self.checkbox_disable_hidraw.set_active(self.default_disable_hidraw)

        disable_mangohud_gamemode_if_missing(self)

        if not get_all_shortcut_paths():
            self.checkbox_shortcut_steam.set_sensitive(False)
            self.checkbox_shortcut_steam.set_tooltip_text(
                _("Add or remove a shortcut from Steam. Steam needs to be restarted. NO STEAM USERS FOUND."))

        self.lossless_location = ConfigManager().config.get('lossless-location', '')
        if os.path.exists(lsfgvk_path):
            if lossless_dll or os.path.exists(self.lossless_location):
                self.button_lossless.set_sensitive(True)
            else:
                self.button_lossless.set_sensitive(False)
                self.button_lossless.set_tooltip_text(_("Lossless.dll NOT FOUND. If it's installed, go to Faugus's settings and set the location."))
        else:
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Lossless Scaling Vulkan Layer NOT INSTALLED."))

        self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

        self.grid_steam_title.set_visible(False)
        self.update_image_banner()
        if interface_mode not in ("Banners", "SteamGridDB"):
            self.image_banner.set_visible(False)
            self.image_banner2.set_visible(False)

        self.present()

    def on_combobox_steam_changed(self, combobox):
        self.combobox_steam_title.remove_css_class("combobox")

        title = self.combobox_steam_title.get_active_text()
        steamid = self.combobox_steam_title.get_active_id()

        if not title or not steamid:
            return

        self._suggestion_programmatic = True
        self.entry_title.set_text(title)
        self._suggestion_programmatic = False
        self._steamgriddb_suggestion_id = None
        self._steamgriddb_steam_appid = steamid
        if getattr(self, 'suggestion_popover', None) is not None:
            self.suggestion_popover.popdown()

        self.entry_path.set_text(steamid)

        icon_path = get_steam_icon_path(steamid)
        if not icon_path:
            icon_path = faugus_png

        self.get_banner()

        shutil.copyfile(icon_path, os.path.expanduser(self.icon_temp))
        surface = self.new_texture_from_image(self.icon_temp, 50, 50)
        image = new_picture(surface)
        self.button_shortcut_icon.set_child(image)

    def on_button_launch_arguments_clicked(self, widget):
        def on_result(result):
            self.launch_arguments = result
        show_launch_arguments_dialog(self, self.launch_arguments, on_result)

    def on_button_addapp_clicked(self, widget):
        def on_result(result):
            (self.addapp_enabled, self.addapp,
             self.addapp_delay, self.addapp_first) = result
        show_addapp_dialog(
            self, self.addapp_enabled, self.addapp,
            self.addapp_delay, self.addapp_first, on_result)

    def on_button_lossless_clicked(self, widget):
        def on_result(result):
            (self.lossless_enabled, self.lossless_multiplier,
             self.lossless_flow, self.lossless_performance,
             self.lossless_hdr, self.lossless_present) = result
        show_lossless_dialog(
            self, self.lossless_enabled, self.lossless_multiplier,
            self.lossless_flow, self.lossless_performance,
            self.lossless_hdr, self.lossless_present, on_result)

    def on_image_clicked(self, gesture, n_press, x, y, category="grid"):
        self._menu_category = category
        image = gesture.get_widget()
        if self.menu.get_parent():
            self.menu.unparent()
        self.menu.set_parent(image)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        self.menu.set_pointing_to(rect)
        self.menu.popup()

    def artwork_target(self, category):
        if category == "hero":
            return self.hero_path_temp, lambda: self.update_hero_preview(self.hero_path_temp)
        if category == "icon":
            return self.icon_temp, self.refresh_icon_preview
        return self.banner_path_temp, self.update_image_banner

    def on_refresh(self, widget):
        self.menu.popdown()
        category = getattr(self, '_menu_category', 'grid')
        dest_path, refresh = self.artwork_target(category)

        if self.entry_title.get_text() == "":
            if os.path.isfile(dest_path):
                os.remove(dest_path)
            refresh()
            return

        if self.interface_mode == "SteamGridDB":
            self.refresh_single_artwork(category)
        else:
            self.get_banner()

    def refresh_single_artwork(self, category):
        import requests

        game_name = self.entry_title.get_text().strip()
        if not game_name:
            return

        cfg = ConfigManager()
        api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
        if not api_key:
            return

        suggestion_id = self._steamgriddb_suggestion_id
        steam_appid = self._steamgriddb_steam_appid
        closed_event = self.closed_event

        loading_setter = {
            "icon": self.set_icon_loading,
            "grid": self.set_grid_loading,
            "hero": self.set_hero_loading,
        }[category]
        key = {"icon": "icons", "grid": "grids", "hero": "heroes"}[category]

        loading_setter(True)

        def worker():
            try:
                candidates = fetch_steamgriddb_candidates(
                    api_key, game_name, limit=1, game_id=suggestion_id, steam_appid=steam_appid
                )
                url = candidates[key][0]["url"] if candidates[key] else None
                if not url:
                    print(f"SteamGridDB: no {category} found for '{game_name}'")
                    return
                session = get_steamgriddb_session()
                content = session.get(url, timeout=15).content
                if not closed_event.is_set():
                    GLib.idle_add(self.apply_downloaded_artwork, category, content)
            except requests.RequestException as e:
                print(f"Error refreshing SteamGridDB {category}: {e}")
            finally:
                if not closed_event.is_set():
                    GLib.idle_add(loading_setter, False)

        run_in_background(worker)

    def on_load_file(self, widget):
        self.menu.popdown()
        category = getattr(self, '_menu_category', 'grid')
        dest_path, refresh = self.artwork_target(category)

        titles = {
            "grid": _("Select an image for the banner"),
            "hero": _("Select an image for the hero"),
            "icon": _("Select an image for the icon"),
        }

        filechooser = new_file_chooser(
            self,
            titles.get(category, titles["grid"]),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, f"artwork_{category}")

        add_image_file_filters(filechooser, include_ico=False)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                file_path = dialog_fc.get_file().get_path()
                if not file_path or not is_valid_image(file_path):
                    show_invalid_image_dialog()
                else:
                    shutil.copyfile(file_path, dest_path)
                    refresh()

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_load_url(self, widget):
        self.menu.popdown()
        category = getattr(self, '_menu_category', 'grid')
        dest_path, refresh = self.artwork_target(category)
        dialog = Gtk.Dialog(title=_("Enter the image URL"), transient_for=self)
        hide_dialog_action_area(dialog)
        dialog.set_modal(True)
        dialog.set_resizable(False)

        entry = Gtk.Entry()
        entry.set_tooltip_text("https://example.com/banner.png")

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_hexpand(True)
        button_ok.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.OK))

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.set_hexpand(True)
        button_cancel.connect("clicked", lambda x: dialog.response(Gtk.ResponseType.CANCEL))

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(10)
        box_top.set_margin_end(10)
        box_top.set_margin_top(10)
        box_top.set_margin_bottom(10)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_homogeneous(True)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)

        box_top.append(entry)

        box_bottom.append(button_cancel)
        box_bottom.append(button_ok)

        dialog.get_content_area().append(box_top)
        dialog.get_content_area().append(box_bottom)

        def on_response(dialog, response_id):
            if response_id != Gtk.ResponseType.OK:
                destroy_and_release(dialog)
                return

            url = entry.get_text().strip().replace(" ", "%20")
            valid_exts = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".svg")

            if not url.lower().endswith(valid_exts):
                show_invalid_image_dialog()
                return

            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as r, open(dest_path, "wb") as f:
                    f.write(r.read())

                refresh()
                destroy_and_release(dialog)

            except Exception:
                show_invalid_image_dialog()

        dialog.connect("response", on_response)
        dialog.present()

    def set_grid_loading(self, loading):
        spinner1 = getattr(self, 'spinner_grid1', None)
        spinner2 = getattr(self, 'spinner_grid2', None)
        if spinner1 and spinner2:
            set_spinner_loading((spinner1, spinner2), loading)
        return False

    def set_hero_loading(self, loading):
        spinner1 = getattr(self, 'spinner_hero1', None)
        spinner2 = getattr(self, 'spinner_hero2', None)
        if spinner1 and spinner2:
            set_spinner_loading((spinner1, spinner2), loading)
        return False

    def set_icon_loading(self, loading):
        spinner = getattr(self, 'spinner_icon', None)
        if spinner:
            set_spinner_loading((spinner,), loading)
        return False

    def refresh_grid_preview(self):
        self.update_image_banner()
        return False

    def refresh_icon_preview(self):
        surface = self.new_texture_from_image(self.icon_temp, 50, 50)
        self.button_shortcut_icon.set_child(new_picture(surface))
        return False

    def refresh_hero_preview(self):
        self.update_hero_preview(self.hero_path_temp)
        return False

    def apply_downloaded_artwork(self, category, content):
        if category == "grid":
            with open(self.banner_path_temp, "wb") as f:
                f.write(content)
            self.refresh_grid_preview()
        elif category == "hero":
            with open(self.hero_path_temp, "wb") as f:
                f.write(content)
            self.refresh_hero_preview()
        elif category == "icon":
            with open(self.icon_temp, "wb") as f:
                f.write(content)
            self.refresh_icon_preview()
        return False

    def update_hero_preview(self, hero_path):
        if hero_path and os.path.isfile(hero_path):
            surface = self.new_texture_from_image(hero_path, 480, 155, True)
            self.hero_picture1.set_paintable(surface)
            self.hero_picture2.set_paintable(surface)
            self.hero_preview_stack1.set_visible_child_name("picture")
            self.hero_preview_stack2.set_visible_child_name("picture")
        else:
            self.hero_preview_stack1.set_visible_child_name("placeholder")
            self.hero_preview_stack2.set_visible_child_name("placeholder")

    def get_banner(self):
        import requests

        closed_event = self.closed_event
        banner_path_temp = self.banner_path_temp
        hero_path_temp = self.hero_path_temp
        interface_mode = self.interface_mode

        game_name = self.entry_title.get_text().strip()
        if not game_name:
            return

        suggestion_id = self._steamgriddb_suggestion_id
        steam_appid = self._steamgriddb_steam_appid

        cfg = ConfigManager()
        api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')

        fetch_icon = bool(api_key) and interface_mode == "SteamGridDB"
        fetch_grid = interface_mode in ("Banners", "SteamGridDB")
        fetch_hero = interface_mode == "SteamGridDB" and bool(api_key)

        if fetch_icon:
            self.set_icon_loading(True)
        if fetch_grid:
            self.set_grid_loading(True)
        if fetch_hero:
            self.set_hero_loading(True)

        def fetch_banner():
            try:
                fetch_sgdb_icon = bool(api_key) and interface_mode == "SteamGridDB"
                fetch_sgdb_grid_hero = interface_mode == "SteamGridDB" and bool(api_key)

                icon_url = grid_url = hero_url = None
                if fetch_sgdb_icon or fetch_sgdb_grid_hero:
                    session = get_steamgriddb_session()
                    candidates = fetch_steamgriddb_candidates(
                        api_key, game_name, limit=1, game_id=suggestion_id, steam_appid=steam_appid
                    )

                    if fetch_sgdb_icon:
                        icon_url = candidates["icons"][0]["url"] if candidates["icons"] else None
                        if not icon_url:
                            print(f"SteamGridDB: no icon found for '{game_name}'")

                    if fetch_sgdb_grid_hero:
                        grid_url = candidates["grids"][0]["url"] if candidates["grids"] else None
                        hero_url = candidates["heroes"][0]["url"] if candidates["heroes"] else None
                        if not grid_url:
                            print(f"SteamGridDB: no grid found for '{game_name}'")
                        if not hero_url:
                            print(f"SteamGridDB: no hero found for '{game_name}'")

                    downloads = {}
                    if icon_url:
                        downloads["icon"] = icon_url
                    if grid_url:
                        downloads["grid"] = grid_url
                    if hero_url:
                        downloads["hero"] = hero_url

                    def download_one(category):
                        try:
                            content = session.get(downloads[category], timeout=15).content
                            if not closed_event.is_set():
                                GLib.idle_add(self.apply_downloaded_artwork, category, content)
                        except requests.RequestException as e:
                            print(f"Error fetching SteamGridDB {category}: {e}")

                    if downloads:
                        with ThreadPoolExecutor(max_workers=len(downloads)) as pool:
                            list(pool.map(download_one, downloads.keys()))

                if fetch_sgdb_grid_hero:
                    if not grid_url and os.path.isfile(banner_path_temp):
                        os.remove(banner_path_temp)
                        if not closed_event.is_set():
                            GLib.idle_add(self.refresh_grid_preview)
                    if not hero_url and os.path.isfile(hero_path_temp):
                        os.remove(hero_path_temp)
                        if not closed_event.is_set():
                            GLib.idle_add(self.refresh_hero_preview)
                    return

                if interface_mode not in ("Banners", "SteamGridDB"):
                    return

                api_url = f"https://steamgrid.usebottles.com/api/search/{game_name}"
                try:
                    response = requests.get(api_url)
                    response.raise_for_status()
                    image_url = response.text.strip('"')
                    content = requests.get(image_url).content

                    if not closed_event.is_set():
                        GLib.idle_add(self.apply_downloaded_artwork, "grid", content)

                except requests.RequestException as e:
                    print(f"Error fetching the banner: {e}")

            finally:
                if fetch_icon:
                    GLib.idle_add(self.set_icon_loading, False)
                if fetch_grid:
                    GLib.idle_add(self.set_grid_loading, False)
                if fetch_hero:
                    GLib.idle_add(self.set_hero_loading, False)

        run_in_background(fetch_banner)

    def update_image_banner(self):
        if os.path.isfile(self.banner_path_temp):
            surface = self.new_texture_from_image(self.banner_path_temp, 260, 390, True)
            self.image_banner.set_paintable(surface)
            self.image_banner2.set_paintable(surface)
            self.image_banner_stack.set_visible_child_name("picture")
            self.image_banner2_stack.set_visible_child_name("picture")
        else:
            self.image_banner_stack.set_visible_child_name("placeholder")
            self.image_banner2_stack.set_visible_child_name("placeholder")

    def on_entry_focus_out(self):
        if self._steamgriddb_suggestion_id is not None:
            return
        if self.entry_title.get_text() != "":
            self.get_banner()
        else:
            if os.path.isfile(self.banner_path_temp):
                os.remove(self.banner_path_temp)
            self.update_image_banner()

    def on_title_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape and self.suggestion_popover.get_visible():
            self.suggestion_popover.popdown()
            return True
        return False

    def on_title_focus_leave_for_suggestions(self):
        closed_event = self.closed_event
        entry_title = self.entry_title
        suggestion_popover = self.suggestion_popover

        def check():
            if closed_event.is_set():
                return False
            root = entry_title.get_root()
            focus_widget = root.get_focus() if root else None
            w = focus_widget
            while w is not None:
                if w is suggestion_popover:
                    return False
                w = w.get_parent()
            suggestion_popover.popdown()
            return False

        GLib.idle_add(check)

    def on_dialog_click_for_suggestions(self, gesture, n_press, x, y):
        if not self.suggestion_popover.get_visible():
            return

        picked = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        w = picked
        while w is not None:
            if w is self.suggestion_popover or w is self.entry_title:
                return
            w = w.get_parent()

        self.suggestion_popover.popdown()

    def on_title_changed_for_suggestions(self, entry):
        if self._suggestion_programmatic:
            return

        self._steamgriddb_suggestion_id = None
        self._steamgriddb_steam_appid = None

        if self._suggestion_source:
            GLib.source_remove(self._suggestion_source)
            self._suggestion_source = None

        text = entry.get_text().strip()
        if not text:
            self.suggestion_popover.popdown()
            return

        cfg = ConfigManager()
        api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
        if not api_key:
            return

        closed_event = self.closed_event
        entry_title = self.entry_title
        suggestion_listbox = self.suggestion_listbox
        suggestion_popover = self.suggestion_popover

        def fire():
            self._suggestion_source = None
            if closed_event.is_set():
                return False
            self.fetch_title_suggestions(
                text, api_key, closed_event, entry_title, suggestion_listbox, suggestion_popover
            )
            return False

        self._suggestion_source = GLib.timeout_add(350, fire)

    def fetch_title_suggestions(self, term, api_key, closed_event, entry_title, suggestion_listbox, suggestion_popover):
        def worker():
            suggestions = fetch_steamgriddb_autocomplete(api_key, term, limit=10)
            if not closed_event.is_set():
                GLib.idle_add(
                    self.populate_suggestions, term, suggestions,
                    closed_event, entry_title, suggestion_listbox, suggestion_popover
                )

        run_in_background(worker)

    def populate_suggestions(self, term, suggestions, closed_event, entry_title, suggestion_listbox, suggestion_popover):
        if closed_event.is_set():
            return False
        if entry_title.get_text().strip() != term:
            return False

        child = suggestion_listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            suggestion_listbox.remove(child)
            child = nxt

        if not suggestions:
            suggestion_popover.popdown()
            return False

        for item in suggestions:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=item["name"])
            label.set_halign(Gtk.Align.START)
            label.set_margin_start(8)
            label.set_margin_end(8)
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            row.set_child(label)
            row.steamgriddb_id = item["id"]
            row.steamgriddb_name = item["name"]
            suggestion_listbox.append(row)

        suggestion_popover.popup()
        return False

    def on_suggestion_row_activated(self, listbox, row):
        clean_name = re.sub(r'\s*\(\d{4}\)\s*$', '', row.steamgriddb_name).strip()
        self._suggestion_programmatic = True
        self.entry_title.set_text(clean_name)
        self._suggestion_programmatic = False
        self._steamgriddb_suggestion_id = row.steamgriddb_id
        self.suggestion_popover.popdown()
        self.entry_title.grab_focus_without_selecting()
        self.get_banner()

    def on_combobox_changed(self, combobox):
        active_id = combobox.get_active_id()

        cfg = ConfigManager()
        steamgriddb_enabled = bool(cfg.config.get('steamgriddb-api-key', '').strip('"'))

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
            self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())
            if os.path.isfile(self.banner_path_temp):
                os.remove(self.banner_path_temp)
            if os.path.isfile(self.hero_path_temp):
                os.remove(self.hero_path_temp)
            self.update_image_banner()
            self.update_hero_preview(self.hero_path_temp)

            for w in (self.combobox_steam_title, self.entry_title,
                      self.entry_prefix, self.entry_path):
                w.remove_css_class("entry")

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
            self.button_shortcut_icon.set_visible(steamgriddb_enabled and self.interface_mode != "Banners")

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

        if self.interface_mode in ("Banners", "SteamGridDB"):
            if self.entry_title.get_text():
                self.get_banner()

    def populate_combobox_with_launchers(self):
        self.combobox_launcher.append("windows", _("Windows Game"))
        self.combobox_launcher.append("linux", _("Linux Game"))
        self.combobox_launcher.append("steam", _("Steam Game"))
        self.combobox_launcher.append("battle", "Battle.net")
        self.combobox_launcher.append("ea", "EA App")

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

        filechooser = new_file_chooser(
            self,
            _("Select a file to run inside the prefix"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "run_in_prefix")

        add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                file_run = dialog_fc.get_file().get_path()
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
                    process = subprocess.Popen(cmd, cwd=cwd if cwd else None, env=subprocess_env())
                    process.wait()

                run_in_background(run_command)

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def set_image_shortcut_icon(self):
        shutil.copyfile(faugus_png_raster, self.icon_temp)

        surface = self.new_texture_from_image(self.icon_temp, 50, 50)
        image = new_picture(surface)

        return image

    def on_button_shortcut_icon_clicked(self, widget):
        validation_result = self.validate_fields(entry="path")
        if not validation_result:
            return

        path = self.entry_path.get_text()

        if os.path.isfile(path):
            os.makedirs(self.icon_directory, exist_ok=True)
            status = extract_ico(path, self.icon_converted, best_frame=False)
            if status == "no_icons":
                self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

        choose_shortcut_icon(self)

    def check_existing_shortcut(self):

        title = self.entry_title.get_text().strip()
        if not title:
            return

        title_formatted = format_title(title)
        desktop_file_path = f"{desktop_dir}/{title_formatted}.desktop"
        applications_shortcut_path = f"{app_dir}/{title_formatted}.desktop"

        self.checkbox_shortcut_desktop.set_active(os.path.exists(desktop_file_path))
        self.checkbox_shortcut_appmenu.set_active(os.path.exists(applications_shortcut_path))

    def update_prefix_entry(self, entry):

        title_formatted = format_title(entry.get_text())
        prefix = os.path.expanduser(self.default_prefix) + "/" + title_formatted
        self.entry_prefix.set_text(prefix)

    def on_button_winecfg_clicked(self, widget):
        self.set_sensitive(False)

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

        if title_formatted:
            command_parts.append(f"LOG_DIR='{title_formatted}'")
        if prefix:
            command_parts.append(f"WINEPREFIX='{prefix}'")
        if runner:
            if runner == "Proton-CachyOS (System)":
                command_parts.append(f"PROTONPATH='{proton_cachyos}'")
            else:
                command_parts.append(f"PROTONPATH='{runner}'")

        command_parts.append(f"'{umu_run}'")
        command_parts.append("'winecfg'")

        command = ' '.join(command_parts)

        print(command)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command], env=subprocess_env())
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent_window.set_sensitive, True)

        run_in_background(run_command)

    def on_button_winetricks_clicked(self, widget):
        self.set_sensitive(False)

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

        command_parts.append(f"'{umu_run}'")
        command_parts.append("''")

        command = ' '.join(command_parts)

        print(command)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command, "winetricks"], env=subprocess_env())
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent_window.set_sensitive, True)

        run_in_background(run_command)

    def on_button_search_clicked(self, widget):
        entry_value = self.entry_path.get_text()
        preferred_path = os.path.dirname(entry_value) if entry_value else None

        filechooser = new_file_chooser(
            self,
            _("Select the game's .exe"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "game_exe", preferred_path)

        if self.combobox_launcher.get_active_id() != "linux":
            add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = dialog_fc.get_file().get_path()

                if self.interface_mode == "Banners":
                    os.makedirs(self.icon_directory, exist_ok=True)
                    status = extract_ico(path, self.icon_temp, best_frame=True)
                    if status == "ok":
                        surface = self.new_texture_from_image(self.icon_temp, 50, 50)
                        self.button_shortcut_icon.set_child(new_picture(surface))
                    elif status == "no_icons":
                        self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

                self.entry_path.set_text(path)

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_button_search_prefix_clicked(self, widget):
        filechooser = new_file_chooser(
            self,
            _("Select a prefix location"),
            Gtk.FileChooserAction.SELECT_FOLDER,
        )

        if not self.entry_prefix.get_text():
            filechooser.set_current_folder(Gio.File.new_for_path(os.path.expanduser(self.default_prefix)))
        else:
            filechooser.set_current_folder(Gio.File.new_for_path(self.entry_prefix.get_text()))

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                new_prefix = dialog_fc.get_file().get_path()
                self.default_prefix = new_prefix
                self.entry_prefix.set_text(self.default_prefix)

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def validate_fields(self, entry):

        title = self.entry_title.get_text()
        gameid = format_title(title)
        prefix = self.entry_prefix.get_text()
        path = self.entry_path.get_text()
        combobox_steam = self.combobox_steam_title.get_active_text()

        self.combobox_steam_title.remove_css_class("combobox")
        self.entry_title.remove_css_class("entry")
        self.entry_prefix.remove_css_class("entry")
        self.entry_path.remove_css_class("entry")

        if self.grid_steam_title.get_visible():
            if not combobox_steam:
                self.combobox_steam_title.add_css_class("combobox")
                self.notebook.set_current_page(0)

        if entry == "prefix":
            if not title or not prefix:
                if not title:
                    self.entry_title.add_css_class("entry")
                    self.notebook.set_current_page(0)

                if not prefix:
                    self.entry_prefix.add_css_class("entry")
                    self.notebook.set_current_page(0)

                return False

        if entry == "path":
            if not title or not path:
                if not title:
                    self.entry_title.add_css_class("entry")
                    self.notebook.set_current_page(0)

                if not path:
                    self.entry_path.add_css_class("entry")
                    self.notebook.set_current_page(0)

                return False

        if entry == "path+prefix":
            if not title or not path or not prefix or not gameid:
                if not title:
                    self.entry_title.add_css_class("entry")
                    self.notebook.set_current_page(0)

                if not path:
                    self.entry_path.add_css_class("entry")
                    self.notebook.set_current_page(0)

                if not prefix:
                    self.entry_prefix.add_css_class("entry")
                    self.notebook.set_current_page(0)

                if not gameid:
                    self.entry_title.add_css_class("entry")
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
    subprocess.Popen([sys.executable, "-m", "faugus.runner", command], cwd=file_dir, env=subprocess_env())


def main():
    suppress_adwaita_theme_warning()

    start_hidden = "--hide" in sys.argv
    sys.argv = [arg for arg in sys.argv if arg != "--hide"]

    if len(sys.argv) == 2:
        run_file(sys.argv[1])
        sys.exit(0)

    app = FaugusApp(start_hidden)
    app.run(sys.argv)


def prefixes_count(prefix):
    games = load_json_file(games_json, None)
    if games is None:
        return
    return sum(1 for x in games if x.get("prefix") == prefix) - 1


if __name__ == "__main__":
    update_games_json()
    main()
