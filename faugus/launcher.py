#!/usr/bin/python3

import shutil
import subprocess
import sys
import threading
import warnings
import gi
import vdf
import signal
from datetime import datetime

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version('Gtk', '4.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, GObject, Pango
from faugus.config_manager import *
from faugus.utils import *
from faugus.steam_setup import *
from faugus.ea_fix import *
from faugus.migration import fix_legacy_shortcut_icons
from faugus.main_screen_nav import adjust_widget_value, carrousel_move_coalesced, focus_bottom_bar_by_column, focus_flowbox_child, focus_top_bar, navigate_focus
from faugus.tray_only import spawn as tray_only_spawn

VERSION = "2.4.2"

GLib.set_prgname(APP_ID if IS_FLATPAK else "faugus-launcher")


os.makedirs(COMPATIBILITY_DIR, exist_ok=True)

faugus_backup = False

LAUNCHER_EXE_PATHS = {
    "amazon": "drive_c/users/steamuser/AppData/Local/Amazon Games/App/Amazon Games.exe",
    "battle": "drive_c/Program Files (x86)/Battle.net/Battle.net.exe",
    "ea": "drive_c/Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe",
    "epic": "drive_c/Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe",
    "gog": "drive_c/Program Files/GOG Galaxy/GalaxyClient.exe",
    "rockstar": "drive_c/Program Files/Rockstar Games/Launcher/Launcher.exe",
    "ubisoft": "drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/UbisoftConnect.exe",
    "wargaming": "drive_c/ProgramData/Wargaming.net/GameCenter/wgc.exe",
}

os.makedirs(FAUGUS_LAUNCHER_SHARE_DIR, exist_ok=True)
os.makedirs(FAUGUS_LAUNCHER_DIR, exist_ok=True)
os.makedirs(FAUGUS_LAUNCHER_STATE_DIR, exist_ok=True)
if fix_legacy_shortcut_icons():
    os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

_ = setup_gettext('faugus-launcher')


class FaugusApp(Gtk.Application):
    def __init__(self, start_hidden=False, console_mode=False):
        super().__init__(application_id=APP_ID)
        self.window = None
        self.start_hidden = start_hidden
        self.console_mode = console_mode

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.on_quit_action)
        self.add_action(quit_action)

    def on_quit_action(self, action, param):
        if self.window:
            self.window.on_quit()
        else:
            self.quit()

    def do_startup(self):
        Gtk.Application.do_startup(self)

        app_icon_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "assets"
        )
        app_icon_dir = os.path.normpath(app_icon_dir)
        if os.path.isdir(app_icon_dir):
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(app_icon_dir)

        cfg = ConfigManager()
        theme_engine = cfg.config.get('theme-engine', 'adwaita').strip('"')
        apply_theme_engine(theme_engine)
        apply_interface_customization(
            cfg.config.get('interface-theme', 'system'),
            cfg.get_accent_color(),
            theme_engine,
        )

        if cfg.config.get('backup-auto-enabled', 'False') == 'True':
            from faugus.backup_daemon import start_daemon_now
            start_daemon_now()

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
        apply_titlebar_preference(self)
        self.add_css_class("main-window")
        self.connect("close-request", self.on_close)
        print(f"Faugus {VERSION}")

        self.fullscreen_activated = False
        self.system_tray = False
        self.mono_icon = False

        self.current_prefix = None
        self.games = []

        self.processes = {}
        self.play_sessions = {}

        if not os.path.exists(RUNNING_GAMES):
            save_json_file({}, RUNNING_GAMES)

        self.running = load_json_file(RUNNING_GAMES, {})
        if not isinstance(self.running, dict):
            self.running = {}

        add_css_once("main_window", """
            .list-row-entry {
                padding: 0;
                min-height: 0;
            }
            .category-list row:selected {
                background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color;
            }
            .envar-list:selected {
                background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color;
            }
            entry.flowbox-entry {
                border: none;
                background: none;
                background-color: transparent;
                background-image: none;
                outline: none;
                box-shadow: none;
                padding: 0px;
            }
            entry.flowbox-entry:selected:not(.cover-container) .game {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.5);
                color: @theme_selected_fg_color;
            }
            entry.flowbox-entry:selected:not(.cover-container) .game-label {
                color: @theme_selected_fg_color;
            }
            entry.flowbox-entry:selected:focus:not(.cover-container) .game {
                background-color: @theme_selected_bg_color;
            }
            entry.flowbox-entry:selected:backdrop:not(.cover-container) .game {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.25);
            }
            entry.flowbox-entry.cover-container {
                box-shadow: 0 6px 14px alpha(black, 0.65);
                transition: transform 200ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
            }
            entry.flowbox-entry.cover-container .game {
                border: none;
            }
            entry.flowbox-entry.cover-container:selected {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.5);
                box-shadow: 0 6px 14px alpha(black, 0.65),
                            0 0 8px 2px alpha(@theme_selected_bg_color, 0.5),
                            0 0 30px 10px alpha(@theme_selected_bg_color, 0.25);
            }
            entry.flowbox-entry.cover-container:selected .game,
            entry.flowbox-entry.carrousel-current .game {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.5);
                color: @theme_selected_fg_color;
            }
            entry.flowbox-entry.cover-container:selected .game-label,
            entry.flowbox-entry.carrousel-current .game-label {
                color: @theme_selected_fg_color;
            }
            entry.flowbox-entry.cover-container:selected:focus {
                background-color: @theme_selected_bg_color;
                transform: scale(1.05);
                box-shadow: 0 6px 14px alpha(black, 0.65),
                            0 0 8px 2px alpha(@theme_selected_bg_color, 1),
                            0 0 30px 10px alpha(@theme_selected_bg_color, 0.5);
            }
            entry.flowbox-entry.cover-container:selected:focus .game,
            entry.flowbox-entry.carrousel-current.carrousel-focused .game {
                background-color: @theme_selected_bg_color;
            }
            entry.flowbox-entry.cover-container:selected:backdrop {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.25);
                box-shadow: 0 6px 14px alpha(black, 0.65);
            }
            entry.flowbox-entry.cover-container:selected:backdrop .game,
            entry.flowbox-entry.carrousel-current:backdrop .game {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.25);
            }
            entry.flowbox-entry.carrousel-current {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.5);
            }
            entry.flowbox-entry.carrousel-current.carrousel-focused {
                background-color: @theme_selected_bg_color;
            }
            entry.flowbox-entry.carrousel-current:backdrop {
                background-color: mix(@theme_bg_color, @theme_selected_bg_color, 0.25);
            }
            .spinner-dim-overlay {
                background-color: alpha(black, 0.3);
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
            popover.popover-accent-background contents,
            popover.popover-accent-background arrow {
                background-color: @window_bg_color;
                background-image: linear-gradient(alpha(@accent_bg_color, 0.2), alpha(@accent_bg_color, 0.2));
            }
            popover.menu label.title,
            modelbutton.title {
                font-size: inherit;
                font-weight: inherit;
            }
            dropdown popover.menu listview,
            dropdown popover.menu scrolledwindow {
                background: none;
                background-color: transparent;
                background-image: none;
            }
            dropdown popover.menu row:not(:hover):not(:focus) {
                background: none;
                background-color: transparent;
                background-image: none;
                box-shadow: none;
            }
            dropdown button.toggle row:hover {
                background: none;
                background-color: transparent;
                background-image: none;
                box-shadow: none;
            }
        """, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        load_frame_css()

        self.context_menu = None

        self.action_context_play = Gio.SimpleAction.new("context-play", None)
        self.action_context_play.connect("activate", self.on_context_menu_play)
        self.add_action(self.action_context_play)

        self.action_context_edit = Gio.SimpleAction.new("context-edit", None)
        self.action_context_edit.connect("activate", self.on_context_menu_edit)
        self.add_action(self.action_context_edit)

        self.action_context_delete = Gio.SimpleAction.new("context-delete", None)
        self.action_context_delete.connect("activate", self.on_context_menu_delete)
        self.add_action(self.action_context_delete)

        self.action_context_duplicate = Gio.SimpleAction.new("context-duplicate", None)
        self.action_context_duplicate.connect("activate", self.on_context_menu_duplicate)
        self.add_action(self.action_context_duplicate)

        self.action_context_hide = Gio.SimpleAction.new("context-hide", None)
        self.action_context_hide.connect("activate", self.on_context_menu_hide)
        self.add_action(self.action_context_hide)

        self.action_context_category = Gio.SimpleAction.new("context-category", GLib.VariantType.new("s"))
        self.action_context_category.connect("activate", self.on_context_menu_category)
        self.add_action(self.action_context_category)

        self.action_context_game_location = Gio.SimpleAction.new("context-game-location", None)
        self.action_context_game_location.connect("activate", self.on_context_menu_game_location)
        self.add_action(self.action_context_game_location)

        self.action_context_prefix_location = Gio.SimpleAction.new("context-prefix-location", None)
        self.action_context_prefix_location.connect("activate", self.on_context_menu_prefix_location)
        self.add_action(self.action_context_prefix_location)

        self.action_context_run = Gio.SimpleAction.new("context-run", None)
        self.action_context_run.connect("activate", self.on_context_menu_run)
        self.add_action(self.action_context_run)

        self.action_context_recent_run = Gio.SimpleAction.new("context-recent-run", GLib.VariantType.new("s"))
        self.action_context_recent_run.connect("activate", self.on_context_menu_recent_run)
        self.add_action(self.action_context_recent_run)

        self.action_context_clear_recent = Gio.SimpleAction.new("context-clear-recent", None)
        self.action_context_clear_recent.connect("activate", self.on_context_menu_clear_recent)
        self.add_action(self.action_context_clear_recent)

        self.action_context_show_logs = Gio.SimpleAction.new("context-show-logs", None)
        self.action_context_show_logs.connect("activate", self.on_context_show_logs)
        self.add_action(self.action_context_show_logs)

        self.load_config()

        if app.console_mode:
            self.interface_mode = "Carrousel"
            self.gamepad_navigation = True
            self.startup_window_size = "Fullscreen"

        placeholder_r, placeholder_g, placeholder_b = self.get_accent_rgb()
        self.update_placeholder_accent_css()
        self.update_widget_color_css()

        if self.theme_engine != "adwaita":
            add_css_once(
                "focus_ring_fallback",
                f"""
                button:focus-visible,
                entry:focus-visible:not(.flowbox-entry),
                dropdown > button:focus-visible,
                check:focus-visible,
                radio:focus-visible,
                scale:focus-visible {{
                    outline: 2px solid rgba({placeholder_r}, {placeholder_g}, {placeholder_b}, 0.8);
                    outline-offset: 1px;
                }}
                row:focus-visible,
                modelbutton:focus-visible {{
                    outline: 2px solid rgba({placeholder_r}, {placeholder_g}, {placeholder_b}, 0.8);
                    outline-offset: -2px;
                }}
                """,
                Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
            )

        if self.interface_mode not in ("List", "Grid", "Covers", "Carrousel"):
            self.interface_mode = "List"

        if self.interface_mode == "List":
            self.setup_interface()
        else:
            if self.startup_window_size == "Maximized":
                self.maximize()
            if self.startup_window_size == "Fullscreen":
                self.fullscreen()
                self.fullscreen_activated = True
            self.setup_interface(True)

        right_click = Gtk.GestureClick()
        right_click.set_button(Gdk.BUTTON_SECONDARY)

        def on_right_click(gesture, n_press, x, y):
            item = self.flowbox.get_child_at_pos(int(x), int(y))
            self.on_item_right_click(item, x, y)

        right_click.connect("pressed", on_right_click)
        self.flowbox.add_controller(right_click)

        file_drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        file_drop_target.connect("drop", self.on_window_file_drop)
        self.add_controller(file_drop_target)

        def on_selected_children_changed(*_):
            GLib.idle_add(self.update_icon)
            GLib.idle_add(self.schedule_background_update)

        self.flowbox.connect("selected-children-changed", on_selected_children_changed)

        GLib.idle_add(self.ensure_tray_daemon)

        if self.gamepad_navigation:
            import faugus.gamepad as gamepad
            gamepad.init_gamepad(self)

        GLib.timeout_add(1000, self.check_running)

    def update_icon(self):
        game = self.selected()
        gameid = game.gameid if game else None

        is_running = gameid in self.running if gameid else False
        icon = "faugus-stop-symbolic" if is_running else "faugus-play-symbolic"

        self.button_play.set_child(new_icon_image(f"{icon}.svg"))

    def selected(self):
        if self.carrousel_active():
            games = self.carrousel_visible_games()
            if not games:
                return None
            return games[self.carrousel_index % len(games)]

        selected_items = self.flowbox.get_selected_children()
        if not selected_items:
            return None
        return getattr(selected_items[0], 'game', None)

    def banner_overlay_enabled(self):
        return self.interface_mode in ("Covers", "Carrousel") and self.banner_enabled

    def carrousel_active(self):
        return self.interface_mode == "Carrousel"

    def grid_position_valign(self):
        position = self.grid_position
        if position.startswith("Top"):
            return Gtk.Align.START
        if position.startswith("Bottom"):
            return Gtk.Align.END
        return Gtk.Align.CENTER

    def grid_position_halign(self):
        position = self.grid_position
        if position.endswith("Left"):
            return Gtk.Align.START
        if position.endswith("Right"):
            return Gtk.Align.END
        return Gtk.Align.CENTER

    def wrap_content_with_position(self, content_widget, overview_panel):
        grid_valign = self.grid_position_valign()

        content_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_group.set_hexpand(True)
        if overview_panel is not None:
            content_group.append(overview_panel)
        content_group.append(content_widget)

        position_wrapper = Gtk.CenterBox(orientation=Gtk.Orientation.VERTICAL)
        position_wrapper.set_hexpand(True)
        position_wrapper.set_vexpand(True)
        if grid_valign == Gtk.Align.START:
            position_wrapper.set_start_widget(content_group)
        elif grid_valign == Gtk.Align.END:
            position_wrapper.set_end_widget(content_group)
        else:
            position_wrapper.set_center_widget(content_group)

        return position_wrapper

    def get_named_rgb(self, name, fallback=(30, 30, 34)):
        found, rgba = Gtk.Box().get_style_context().lookup_color(name)
        if not found:
            return fallback
        return (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))

    def parse_rgb(self, color):
        rgba = Gdk.RGBA()
        rgba.parse(color)
        return (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255))

    def fade_rgb(self, rgb):
        window_rgb = self.get_named_rgb("theme_bg_color")
        return tuple(int(w * 0.8 + c * 0.2) for w, c in zip(window_rgb, rgb))

    def dominant_color_source(self, game):
        if self.interface_mode in ("Covers", "Carrousel"):
            return f"{COVERS_DIR}/{game.gameid}.png"
        return f"{ICONS_DIR}/{game.gameid}.png"

    def get_background_rgb(self):
        if self.background_mode == "custom":
            return self.parse_rgb(self.background_color)
        return self.get_accent_rgb()

    def get_accent_rgb(self):
        if self.theme_engine == "adwaita":
            if self.accent_color and self.accent_color != "system":
                return self.parse_rgb(self.accent_color)
            return self.get_named_rgb("accent_bg_color")

        if self.theme_engine == "system":
            system_accent = get_system_accent_rgb()
            if system_accent:
                return system_accent

        return self.get_named_rgb("theme_selected_bg_color")

    def get_overview_rgb(self):
        mode = self.overview_color_mode

        if mode == 'default':
            return self.get_named_rgb("theme_text_color", fallback=(255, 255, 255))

        if mode == 'custom':
            return self.parse_rgb(self.overview_color)

        if mode != 'dominant_color':
            return self.get_accent_rgb()

        game = self.selected()
        if not game:
            return self.get_accent_rgb()

        color_source = self.dominant_color_source(game)
        if not os.path.isfile(color_source):
            return self.get_accent_rgb()

        if getattr(self, '_overview_panel_dominant_gameid', None) != game.gameid:
            self._overview_panel_dominant_gameid = game.gameid
            self._overview_panel_dominant_rgb = get_dominant_color(color_source)

        return self._overview_panel_dominant_rgb

    def update_widget_color_css(self):
        if self.widget_color_mode == "accent":
            r, g, b = self.get_accent_rgb()
            color = f"mix(@theme_bg_color, rgb({r}, {g}, {b}), 0.4)"
        elif self.widget_color_mode == "solid":
            color = "@theme_bg_color"
        else:
            return
        add_css_once(
            "widget_color",
            f"""
            entry.flowbox-entry:not(:selected):not(.carrousel-current) .game,
            window.main-window .main-control:not(.flashing),
            window.main-window > headerbar,
            window.main-window scale slider,
            popover.widget-color-popover > contents,
            popover.widget-color-popover > arrow {{
                background: {color};
            }}
            window.main-window .main-control:hover:not(.flashing) {{
                background-image: linear-gradient(alpha(currentColor, 0.07), alpha(currentColor, 0.07));
            }}
            window.main-window .main-control:active:not(.flashing) {{
                background-image: linear-gradient(alpha(currentColor, 0.15), alpha(currentColor, 0.15));
            }}
            """,
            Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
        )

    def update_accent_background_css(self):
        fade_r, fade_g, fade_b = self.fade_rgb(self.get_background_rgb())

        if getattr(self, "_accent_background_provider", None) is None:
            self._accent_background_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self._accent_background_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
            )

        css = f".accent-background {{ background-color: rgb({fade_r}, {fade_g}, {fade_b}); }}"
        self._accent_background_provider.load_from_data(css.encode("utf-8"))

    def update_placeholder_accent_css(self):
        r, g, b = self.get_accent_rgb()

        if getattr(self, "_placeholder_accent_provider", None) is None:
            self._placeholder_accent_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self._placeholder_accent_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
            )

        css = f"""
        .cover-placeholder,
        .banner-placeholder,
        .cover-empty {{
            background-color: rgba({r}, {g}, {b}, 0.4);
        }}
        """
        self._placeholder_accent_provider.load_from_data(css.encode("utf-8"))

    def refresh_placeholder_covers(self):
        if hasattr(self, 'flowbox'):
            for child in widget_children(self.flowbox):
                game = getattr(child, 'game', None)
                if game and not os.path.isfile(game.cover):
                    self.update_game_visual(child)

        for slot in getattr(self, 'carrousel_slots', []):
            game = getattr(slot['box'], 'game', None)
            if game and not os.path.isfile(game.cover):
                self.set_carrousel_slot_content(slot, game)

    def apply_popover_background_mode(self, popover, game=None):
        if self.widget_color_mode != "default":
            popover.add_css_class("widget-color-popover")
            return

        if self.theme_engine != "adwaita":
            return

        if self.background_mode == "accent":
            popover.add_css_class("popover-accent-background")
            return

        if self.background_mode == "custom":
            rgb = self.get_background_rgb()
        elif self.background_mode == "dominant_color":
            game = game or self.selected()
            if not game:
                return

            color_source = self.dominant_color_source(game)
            if not os.path.isfile(color_source):
                return

            rgb = get_dominant_color(color_source)
        else:
            return

        fade_r, fade_g, fade_b = self.fade_rgb(rgb)

        if getattr(self, "_popover_dominant_provider", None) is None:
            self._popover_dominant_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self._popover_dominant_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1
            )

        self._popover_dominant_provider.load_from_data(f"""
        popover.popover-dominant-background contents,
        popover.popover-dominant-background arrow {{
            background-color: rgb({fade_r}, {fade_g}, {fade_b});
        }}
        """.encode("utf-8"))
        popover.add_css_class("popover-dominant-background")

    def build_background_container(self, content_widget):
        base_mode = self.background_mode
        show_banner = self.banner_overlay_enabled()

        self._bg_content_widget = content_widget
        self._bg_no_overlay_widget = None
        self._bg_base_box = None
        content_widget.remove_css_class("accent-background")

        if not show_banner and base_mode != "dominant_color":
            if base_mode in ("accent", "custom"):
                content_widget.add_css_class("accent-background")
                self.update_accent_background_css()
            self._bg_no_overlay_widget = content_widget
            return content_widget

        overlay = Gtk.Overlay()

        base_box = Gtk.Box()
        base_box.add_css_class("background")
        base_box.set_hexpand(True)
        base_box.set_vexpand(True)
        if base_mode in ("accent", "custom"):
            base_box.add_css_class("accent-background")
            self.update_accent_background_css()
        overlay.set_child(base_box)
        self._bg_base_box = base_box

        self.stack_banner = Gtk.Stack()
        self.stack_banner.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack_banner.set_transition_duration(150)
        self.stack_banner.set_hexpand(True)
        self.stack_banner.set_vexpand(True)

        self._banner_pages = []
        self._banner_color_providers = []
        self._banner_image_providers = []
        self._banner_fade_providers = []

        for i in range(2):
            page = Gtk.Overlay()

            color_box = Gtk.Box()
            color_box.set_hexpand(True)
            color_box.set_vexpand(True)
            color_box.add_css_class(f"banner-bg-color-{i}")
            page.set_child(color_box)

            banner_image_box = None
            banner_fade_box = None
            if show_banner:
                banner_image_box, banner_fade_box = self.add_banner_layers(page, f"banner-bg-image-{i}", f"banner-bg-fade-{i}")

            color_provider = Gtk.CssProvider()
            color_box.get_style_context().add_provider(color_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            image_provider = Gtk.CssProvider()
            if banner_image_box is not None:
                banner_image_box.get_style_context().add_provider(image_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
            fade_provider = Gtk.CssProvider()
            if banner_fade_box is not None:
                banner_fade_box.get_style_context().add_provider(fade_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

            page.banner_image_box = banner_image_box

            self._banner_pages.append(page)
            self._banner_color_providers.append(color_provider)
            self._banner_image_providers.append(image_provider)
            self._banner_fade_providers.append(fade_provider)

            self.stack_banner.add_named(page, f"banner-{i}")

        self._banner_page_index = 0
        self.stack_banner.set_visible_child(self._banner_pages[0])

        overlay.add_overlay(self.stack_banner)
        overlay.set_measure_overlay(self.stack_banner, False)

        overlay.add_overlay(content_widget)
        overlay.set_measure_overlay(content_widget, True)
        return overlay

    def add_banner_layers(self, overlay, image_class, fade_class):
        image_box = Gtk.Box()
        image_box.set_hexpand(True)
        image_box.set_vexpand(False)
        image_box.set_halign(Gtk.Align.FILL)
        image_box.set_valign(Gtk.Align.START)
        image_box.add_css_class(image_class)
        overlay.add_overlay(image_box)
        overlay.set_measure_overlay(image_box, False)

        fade_box = Gtk.Box()
        fade_box.set_hexpand(True)
        fade_box.set_vexpand(False)
        fade_box.set_halign(Gtk.Align.FILL)
        fade_box.set_valign(Gtk.Align.START)
        fade_box.set_can_target(False)
        fade_box.add_css_class(fade_class)
        overlay.add_overlay(fade_box)
        overlay.set_measure_overlay(fade_box, False)

        banner_ratio = 1920 / 620
        state = {"width": -1}

        def on_banner_tick(widget, frame_clock):
            width = widget.get_width()
            if width > 0 and width != state["width"]:
                state["width"] = width
                height = int(width / banner_ratio)
                image_box.set_size_request(-1, height)
                fade_box.set_size_request(-1, height)
            return True

        overlay.add_tick_callback(on_banner_tick)
        return image_box, fade_box

    def wrap_with_static_banner(self, content_widget, banner_path):
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)

        base_box = self.setup_launcher_base_box()
        overlay.set_child(base_box)

        banner_image_box, banner_fade_box = self.add_banner_layers(overlay, "launcher-screen-banner-image", "launcher-screen-banner-fade")

        overlay.add_overlay(content_widget)
        overlay.set_measure_overlay(content_widget, True)

        provider = Gtk.CssProvider()
        banner_image_box.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        fade_provider = Gtk.CssProvider()
        banner_fade_box.get_style_context().add_provider(fade_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

        self.launcher_banner_provider = provider
        self.launcher_banner_fade_provider = fade_provider
        self.launcher_banner_path = banner_path
        self.update_launcher_banner_css()

        return overlay

    def wrap_launcher_no_banner(self, content_widget):
        base_box = self.setup_launcher_base_box(content_widget)

        self.launcher_banner_provider = None
        self.launcher_banner_fade_provider = None
        self.launcher_banner_path = None
        self.update_launcher_banner_css()

        return base_box

    def setup_launcher_base_box(self, existing_box=None):
        base_box = existing_box if existing_box is not None else Gtk.Box()
        base_box.set_hexpand(True)
        base_box.set_vexpand(True)
        base_box.add_css_class("launcher-screen-base")

        base_provider = Gtk.CssProvider()
        base_box.get_style_context().add_provider(base_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

        self.launcher_banner_base_provider = base_provider
        return base_box

    def cache_busted_uri(self, source_path, cache_key):
        counter_attr = f"_{cache_key}_counter"
        path_attr = f"_{cache_key}_path"

        cache_path = source_path
        if os.path.getsize(source_path) > 0:
            counter = getattr(self, counter_attr, 0) + 1
            setattr(self, counter_attr, counter)
            candidate_path = f"{source_path}.cache{counter}"
            try:
                shutil.copyfile(source_path, candidate_path)
                cache_path = candidate_path
            except OSError:
                pass

        old_cache_path = getattr(self, path_attr, None)
        setattr(self, path_attr, cache_path if cache_path != source_path else None)
        if old_cache_path and old_cache_path != cache_path and os.path.isfile(old_cache_path):
            try:
                os.remove(old_cache_path)
            except OSError:
                pass

        return Gio.File.new_for_path(cache_path).get_uri()

    def update_launcher_banner_css(self):
        base_provider = getattr(self, 'launcher_banner_base_provider', None)
        if base_provider is None:
            return

        provider = self.launcher_banner_provider

        base_mode = self.background_mode
        fade_rgb = self.get_named_rgb("theme_bg_color")

        if base_mode == "dominant_color":
            dominant = getattr(self, 'launcher_banner_dominant_rgb', None)
            if dominant is None and self.interface_mode in ("Covers", "Carrousel"):
                color_source = f"{COVERS_DIR}/cover_temp.png"
                if os.path.isfile(color_source):
                    dominant = get_dominant_color(color_source)
                    self.launcher_banner_dominant_rgb = dominant

            if dominant:
                fade_rgb = self.fade_rgb(dominant)
        elif base_mode in ("accent", "custom"):
            fade_rgb = self.fade_rgb(self.get_background_rgb())

        fade_r, fade_g, fade_b = fade_rgb

        base_css = f"""
        .launcher-screen-base {{
            background-color: rgb({fade_r}, {fade_g}, {fade_b});
        }}
        """
        base_provider.load_from_data(base_css.encode("utf-8"))

        if provider is not None and os.path.isfile(self.launcher_banner_path):
            banner_uri = self.cache_busted_uri(self.launcher_banner_path, 'launcher_banner_css_cache')
            provider.load_from_data(self.banner_image_css("launcher-screen-banner-image", banner_uri).encode("utf-8"))
            self.launcher_banner_fade_provider.load_from_data(self.banner_fade_css("launcher-screen-banner-fade", fade_rgb).encode("utf-8"))

    def banner_image_css(self, css_class, uri):
        return f"""
        .{css_class} {{
            background-image: url("{uri}");
            background-repeat: no-repeat;
            background-position: center;
            background-size: 100% 100%;
        }}
        """

    def banner_fade_css(self, css_class, rgb):
        r, g, b = rgb
        return f"""
        .{css_class} {{
            background-image: linear-gradient(to bottom, rgba({r}, {g}, {b}, 0) 0%, rgba({r}, {g}, {b}, 1) 100%);
            background-repeat: no-repeat;
            background-position: center;
            background-size: 100% 100%;
            transform: scaleY(1.015);
        }}
        """

    def apply_background_mode_live(self, new_mode):
        show_banner = self.banner_overlay_enabled()
        old_had_overlay = self.background_mode == "dominant_color" or show_banner
        new_had_overlay = new_mode == "dominant_color" or show_banner

        old_mode = self.background_mode
        self.background_mode = new_mode

        if old_had_overlay != new_had_overlay:
            return self.rebuild_background_container()

        widget = self._bg_no_overlay_widget if not old_had_overlay else self._bg_base_box
        if widget is not None:
            if old_mode in ("accent", "custom"):
                widget.remove_css_class("accent-background")
            if new_mode in ("accent", "custom"):
                widget.add_css_class("accent-background")
                self.update_accent_background_css()

        self.update_launcher_banner_css()

        if old_had_overlay:
            self.update_background()

        return True

    def rebuild_background_container(self):
        content_widget = getattr(self, '_bg_content_widget', None)
        wrapper = self.main_hbox if self.interface_mode != "List" else getattr(self, 'list_hbox', None)
        if content_widget is None or wrapper is None:
            return False

        for child in widget_children(wrapper):
            wrapper.remove(child)

        content_parent = content_widget.get_parent()
        if content_parent is not None:
            if isinstance(content_parent, Gtk.Overlay):
                content_parent.remove_overlay(content_widget)
            else:
                content_parent.remove(content_widget)

        wrapper.append(self.build_background_container(content_widget))

        if self.banner_overlay_enabled() or self.background_mode == "dominant_color":
            self.apply_background_update_now()

        return True

    def apply_background_update_now(self):
        self.update_launcher_banner_css()
        self.update_background()
        self.update_overview_panel()

    def schedule_background_update(self):
        self.update_launcher_banner_css()
        self.update_overview_panel()

        if getattr(self, 'stack_banner', None) is None:
            return

        if getattr(self, '_banner_update_source', None):
            GLib.source_remove(self._banner_update_source)

        def fire():
            self._banner_update_source = None
            self.update_background()
            return False

        self._banner_update_source = GLib.timeout_add(120, fire)

    def update_background(self):
        stack_banner = getattr(self, 'stack_banner', None)
        base_mode = self.background_mode
        show_banner = self.banner_overlay_enabled()
        if stack_banner is None or (not show_banner and base_mode != "dominant_color"):
            return

        def apply():
            game = self.selected()
            color_css = ""
            banner_css = ""
            fade_css = ""

            next_index = 1 - self._banner_page_index
            page = self._banner_pages[next_index]
            banner_image_box = page.banner_image_box
            color_class = f"banner-bg-color-{next_index}"
            image_class = f"banner-bg-image-{next_index}"
            fade_class = f"banner-bg-fade-{next_index}"

            if game:
                if base_mode == "dominant_color":
                    color_source = self.dominant_color_source(game)
                    if os.path.isfile(color_source):
                        dominant = get_dominant_color(color_source)
                        r, g, b = dominant
                        color_css = f".{color_class} {{ background-color: rgba({r}, {g}, {b}, 0.2); }}"

                if show_banner and banner_image_box is not None:
                    candidate = f"{BANNERS_DIR}/{game.gameid}.png"
                    if os.path.isfile(candidate):
                        banner_uri = self.cache_busted_uri(candidate, 'background_banner_cache')

                        if base_mode == "dominant_color" and color_css:
                            fade_rgb = self.fade_rgb(dominant)
                        elif base_mode in ("accent", "custom"):
                            fade_rgb = self.fade_rgb(self.get_background_rgb())
                        else:
                            fade_rgb = self.get_named_rgb("theme_bg_color")

                        banner_css = self.banner_image_css(image_class, banner_uri)
                        fade_css = self.banner_fade_css(fade_class, fade_rgb)

            self._banner_color_providers[next_index].load_from_data(color_css.encode("utf-8"))
            self._banner_image_providers[next_index].load_from_data(banner_css.encode("utf-8"))
            self._banner_fade_providers[next_index].load_from_data(fade_css.encode("utf-8"))

            stack_banner.set_visible_child(page)
            self._banner_page_index = next_index
            return False

        GLib.idle_add(apply)

    def check_running(self):
        changed = False

        for gameid, pid in load_json_file(RUNNING_GAMES, {}).items():
            if gameid not in self.running:
                self.running[gameid] = pid
                changed = True

        for gameid, pid in list(self.running.items()):
            proc = self.processes.get(gameid)
            if proc is not None:
                if proc.poll() is not None:
                    self.on_exit(proc.pid, proc.returncode, gameid)
                    changed = True
                continue

            try:
                if isinstance(pid, dict):
                    pid = next(iter(pid.values()))
                os.kill(pid, 0)
            except OSError:
                if not IS_FLATPAK:
                    self.on_exit(pid, None, gameid)
                    changed = True

        if changed:
            self.save_running()

        if self.running or changed:
            self.update_icon()

        if self.selected():
            self.update_overview_panel()

        return True

    def save_running(self):
        save_json_file(self.running, RUNNING_GAMES)

    def tray_daemon_running(self):
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", GLib.Variant("(s)", (TRAY_BUS_NAME,)),
            GLib.VariantType.new("(b)"), Gio.DBusCallFlags.NONE, -1, None,
        )
        return connection, result.unpack()[0]

    def call_tray_daemon(self, method, params=None, connection=None):
        try:
            connection = connection or Gio.bus_get_sync(Gio.BusType.SESSION, None)
            connection.call_sync(
                TRAY_BUS_NAME, TRAY_OBJECT_PATH, TRAY_INTERFACE, method,
                params, None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass

    def notify_tray_menu_changed(self):
        if self.system_tray:
            self.call_tray_daemon("RefreshMenu")

    def ensure_tray_daemon(self, force_restart=False):
        connection, running = self.tray_daemon_running()

        if not self.system_tray:
            if running:
                self.call_tray_daemon("Shutdown", connection=connection)
                self.on_quit()
                return True
            return False

        if running and force_restart:
            self.call_tray_daemon("Restart", GLib.Variant("(b)", (True,)), connection)
            self.on_quit()
            return True

        if not running:
            tray_only_spawn(["faugus.tray_only", "--hide"])

    def save_interface_settings(self):
        config = ConfigManager()

        if self.startup_window_size == "Remember":
            config.set_value("width", self.get_width())
            config.set_value("height", self.get_height())

        if self.cover_size:
            config.set_value("cover-size", self.cover_size)

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
            self.on_quit()
            return True

        self.on_quit()
        return False

    def on_quit(self, *_):
        app = self.get_application()
        if app:
            app.quit()
        timer = threading.Timer(2.0, lambda: os._exit(0))
        timer.daemon = True
        timer.start()

    def _focus_flowbox_child(self, child):
        focus_flowbox_child(self.flowbox, child)

    def first_visible_child(self):
        return next((c for c in widget_children(self.flowbox) if c.get_child_visible()), None)

    def select_first_visible_child(self):
        self.flowbox.unselect_all()
        child = self.first_visible_child()
        if child is not None:
            self.flowbox.select_child(child)

    def select_first_child(self):
        if self.carrousel_active():
            self.carrousel_index = 0
            self.render_carrousel()
            if hasattr(self, 'carrousel_fixed'):
                self.carrousel_fixed.grab_focus()
            return

        child = self.first_visible_child()
        if child is not None:
            self._focus_flowbox_child(child)

    def select_first_child_when_ready(self):
        if self.carrousel_active():
            self.carrousel_index = 0
            self.render_carrousel()
            return

        attempts = {"n": 0}

        def try_select():
            attempts["n"] += 1

            child = self.first_visible_child()
            if child is not None:
                self._focus_flowbox_child(child)
                return False

            return attempts["n"] < 100

        GLib.timeout_add(50, try_select)

    def select_game_by_title(self, title):
        if self.carrousel_active():
            games = self.carrousel_visible_games()
            for i, g in enumerate(games):
                if g.title == title:
                    self.carrousel_index = i
                    self.render_carrousel()

                    def grab_carrousel_focus():
                        if hasattr(self, 'carrousel_fixed'):
                            self.carrousel_fixed.grab_focus()
                        return False

                    GLib.idle_add(grab_carrousel_focus)
                    return
            return

        attempts = {"n": 0}

        def do_select():
            attempts["n"] += 1

            for child in widget_children(self.flowbox):
                if child.get_child_visible() and child.game.title == title:
                    self._focus_flowbox_child(child)
                    return False

            return attempts["n"] < 100

        GLib.timeout_add(50, do_select)

    def find_flowbox_child_for_game(self, game):
        for child in widget_children(self.flowbox):
            if child.game is game:
                return child
        return None

    def on_flowbox_keyval_tracker(self, controller, keyval, keycode, state):
        self._last_flowbox_keyval = keyval
        if self.interface_mode == "List" and keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
            return True
        return False

    def on_flowbox_keynav_failed(self, flowbox, direction):
        if self._last_flowbox_keyval == Gdk.KEY_Up:
            focus_top_bar(self)
            return True
        if self._last_flowbox_keyval != Gdk.KEY_Down:
            return True
        selected = flowbox.get_selected_children()
        focus_bottom_bar_by_column(self, selected[0] if selected else None)
        return True

    def setup_interface(self, is_big=False):
        if is_big:
            self.set_default_size(1280, 720)
            self.set_resizable(True)
            if self.startup_window_size == "Remember":
                self.set_default_size(self.window_width, self.window_height)
        else:
            self.set_default_size(-1, 610)
            self.set_resizable(False)

        self.box_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def create_button(icon_name, callback, tooltip=None):
            btn = Gtk.Button()
            btn.add_css_class("flash-btn")
            btn.add_css_class("main-control")

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
        self.button_kill = create_button("faugus-kill-symbolic", self.on_button_kill_clicked, _("Kill all running games"))
        self.button_play = create_button("faugus-play-symbolic", self.on_button_play_clicked)

        self.entry_search = Gtk.Entry()
        self.entry_search.add_css_class("main-control")
        self.entry_search.set_placeholder_text(_("Search..."))
        self.entry_search.connect("changed", self.on_search_changed)
        self.entry_search.connect("activate", self.on_search_activate)
        self.entry_search.set_size_request(170, 50)

        search_key_controller = Gtk.EventControllerKey()
        search_key_controller.connect("key-pressed", self.on_search_entry_key)
        self.entry_search.get_delegate().add_controller(search_key_controller)

        self.sort_map = {
            "alpha": _("Alphabetical"),
            "playtime": _("Playtime"),
            "lastplayed": _("Last played"),
            "custom": _("Custom")
        }

        self.current_sort_id = self.sort

        if self.current_sort_id not in self.sort_map:
            self.current_sort_id = "alpha"

        saved_category = self.category
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
        self.button_category.add_css_class("main-control")
        self.button_category.set_size_request(110, -1)
        self.button_category.connect("clicked", self.on_category_button_clicked)

        self.button_sort = Gtk.Button(label=self.sort_map[self.current_sort_id])
        self.button_sort.add_css_class("main-control")
        self.button_sort.set_size_request(110, -1)

        def update_sort_data():
            self.playtime_data.clear()
            self.latest_games_order.clear()
            try:
                data = load_json_file(GAMES_JSON, [])
                for item in data:
                    if isinstance(item, dict) and "gameid" in item:
                        self.playtime_data[item["gameid"]] = item.get("playtime", 0)
                        last_played = item.get("last_played")
                        if last_played:
                            try:
                                self.latest_games_order[item["gameid"]] = -datetime.fromisoformat(last_played).timestamp()
                            except ValueError:
                                pass
            except:
                pass

            self.custom_order_data.clear()
            self.custom_order_data.update(load_json_file(CUSTOM_ORDER, default={}))

        def on_sort_button_clicked(widget):
            popover = Gtk.Popover()
            popover.set_parent(widget)
            self.apply_popover_background_mode(popover)
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
                    self.button_sort.set_label(target_label)
                    update_sort_data()
                    if self.carrousel_active():
                        self.render_carrousel()
                    else:
                        self.flowbox.invalidate_sort()
                    popover.popdown()

                btn.connect("clicked", set_sort)
                btn.set_has_frame(False)
                vbox.append(btn)

            popover.set_child(vbox)
            popover.connect("closed", lambda p: p.unparent())
            if self.gamepad_navigation:
                self.active_popover = popover
            popover.popup()

            if focus_btn:
                focus_btn.grab_focus()

        self.button_sort.connect("clicked", on_sort_button_clicked)

        adjustment = Gtk.Adjustment(value=self.cover_size, lower=50, upper=100, step_increment=10, page_increment=10, page_size=0)
        self.scale_zoom = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        self.scale_zoom.set_size_request(150, -1)
        self.scale_zoom.set_draw_value(True)
        self.scale_zoom.set_value_pos(Gtk.PositionType.LEFT)
        self.scale_zoom.set_digits(0)
        self.scale_zoom.set_margin_end(10)

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
            self.cover_size = zoom_pct

            self.schedule_zoom_apply(zoom_pct)

        self.scale_zoom.connect("value-changed", on_zoom_changed)

        zoom_key_controller = Gtk.EventControllerKey()
        zoom_key_controller.connect("key-pressed", self.on_zoom_scale_key)
        self.scale_zoom.add_controller(zoom_key_controller)

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
        self._last_flowbox_keyval = None
        flowbox_keyval_tracker = Gtk.EventControllerKey()
        flowbox_keyval_tracker.connect("key-pressed", self.on_flowbox_keyval_tracker)
        self.flowbox.add_controller(flowbox_keyval_tracker)
        click_release = Gtk.GestureClick()
        click_release.set_button(Gdk.BUTTON_PRIMARY)
        click_release.connect("released", self.on_item_release_event)
        self.flowbox.add_controller(click_release)

        def setup_dnd_for_widget(fb_child):
            if not isinstance(fb_child, Gtk.FlowBoxChild):
                return
            if getattr(fb_child, '_dnd_ready', False):
                return
            fb_child._dnd_ready = True

            def on_prepare(source, x, y):
                self._drag_source_id = fb_child.game.gameid
                self.flowbox.select_child(fb_child)
                return Gdk.ContentProvider.new_for_value(fb_child.game.gameid)

            def on_drag_begin(source, drag):
                self.set_drag_icon(source, fb_child.game, fb_child)

            def on_drag_end(source, drag, delete_data):
                self._drag_source_id = None
                if self.current_sort_id == "custom":
                    save_json_file(self.custom_order_data, CUSTOM_ORDER)

            drag_source = Gtk.DragSource()
            drag_source.set_actions(Gdk.DragAction.MOVE)
            drag_source.connect("prepare", on_prepare)
            drag_source.connect("drag-begin", on_drag_begin)
            drag_source.connect("drag-end", on_drag_end)
            fb_child.add_controller(drag_source)

            def on_drop_motion(target, x, y):
                if self.current_sort_id != "custom" or not getattr(self, '_drag_source_id', None):
                    return 0

                source_id = self._drag_source_id
                target_id = fb_child.game.gameid

                if source_id == target_id:
                    return Gdk.DragAction.MOVE

                ordered = sorted(
                    (child.game.gameid for child in widget_children(self.flowbox)),
                    key=lambda gid: self.custom_order_data.get(gid, 999999)
                )

                if self.move_custom_order(ordered, source_id, target_id):
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
            if self.interface_mode in ("Grid", "Covers"):
                max_children = self.grid_max_children_per_line
                self.flowbox.set_min_children_per_line(min(2, max_children))
                self.flowbox.set_max_children_per_line(max_children)
            else:
                self.flowbox.set_min_children_per_line(2)
                self.flowbox.set_max_children_per_line(20)

            horizontal_mode = (
                self.interface_mode in ("Grid", "Covers")
                and self.grid_orientation == 'Horizontal'
            )
            if horizontal_mode:
                self.flowbox.set_orientation(Gtk.Orientation.VERTICAL)
                scroll_box.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            else:
                self.flowbox.set_orientation(Gtk.Orientation.HORIZONTAL)
                scroll_box.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        else:
            self.flowbox.set_halign(Gtk.Align.FILL)
            self.flowbox.set_valign(Gtk.Align.START)
            self.flowbox.set_min_children_per_line(1)
            self.flowbox.set_max_children_per_line(1)

        if self.interface_mode == "List":
            self.flowbox.set_row_spacing(5)
        elif self.interface_mode == "Grid":
            self.flowbox.set_row_spacing(5)
            self.flowbox.set_column_spacing(5)

        def sort_games(child1, child2, user_data):
            g1 = child1.game
            g2 = child2.game

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

            t1, t2 = g1.title.lower(), g2.title.lower()
            return (t1 > t2) - (t1 < t2)

        def filter_games(child, user_data):
            return self.game_matches_filter(child.game, self.entry_search.get_text().lower())

        self.flowbox.set_sort_func(sort_games, None)
        self.flowbox.set_filter_func(filter_games, None)
        scroll_box.set_child(self.flowbox)

        bottom_bar_key_controller = Gtk.EventControllerKey()
        bottom_bar_key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        bottom_bar_key_controller.connect("key-pressed", self.on_bottom_bar_key)

        if is_big:
            self.main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.box_main.append(self.main_hbox)

            right_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.main_hbox.append(self.build_background_container(right_vbox))

            self.scale_zoom.set_visible(self.interface_mode in ("Covers", "Carrousel") and self.zoom_enabled)

            bottom_bar = Gtk.CenterBox(orientation=Gtk.Orientation.HORIZONTAL)
            self.bottom_bar = bottom_bar
            bottom_bar.set_margin_top(5)
            bottom_bar.set_margin_bottom(10)
            bottom_bar.set_margin_start(10)
            bottom_bar.set_margin_end(10)

            bottom_bar.add_controller(bottom_bar_key_controller)

            bottom_bar.set_start_widget(self.scale_zoom)

            if self.sort_enabled or self.categories_enabled:
                box_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                box_actions.set_margin_start(10)
                if self.sort_enabled:
                    self.button_sort.set_size_request(50, 50)
                    box_actions.append(self.button_sort)
                if self.categories_enabled:
                    self.button_category.set_size_request(50, 50)
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
            self.scale_zoom.set_valign(Gtk.Align.CENTER)
            self.scale_zoom.set_vexpand(False)

            overview_panel = None
            if self.overview_enabled and self.interface_mode in ("Grid", "Covers", "Carrousel"):
                overview_panel = self.build_overview_panel()

            if self.carrousel_active():
                carrousel_box = self.build_carrousel_widget()
                carrousel_box.set_vexpand(False)
                right_vbox.append(self.wrap_content_with_position(carrousel_box, overview_panel))
            elif self.interface_mode in ("Covers", "Grid"):
                scroll_box.set_vexpand(False)
                scroll_box.set_propagate_natural_height(True)

                position_halign = self.grid_position_halign()
                self.flowbox.set_halign(Gtk.Align.CENTER)
                if horizontal_mode or position_halign != Gtk.Align.CENTER:
                    self.flowbox.set_hexpand(False)
                    scroll_box.set_hexpand(False)
                    scroll_box.set_halign(position_halign)
                    scroll_box.set_propagate_natural_width(True)
                else:
                    self.flowbox.set_hexpand(True)
                    scroll_box.set_hexpand(True)
                    scroll_box.set_halign(Gtk.Align.FILL)
                    scroll_box.set_propagate_natural_width(False)
                if self.interface_mode == "Covers":
                    self.flowbox.set_margin_top(40)
                    self.flowbox.set_margin_bottom(40)
                    self.flowbox.set_margin_start(40)
                    self.flowbox.set_margin_end(40)

                right_vbox.append(self.wrap_content_with_position(scroll_box, overview_panel))
            else:
                right_vbox.append(scroll_box)
                scroll_box.set_vexpand(True)
            right_vbox.append(bottom_bar)

        else:
            box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.box_bottom = Gtk.Box()

            self.box_bottom.add_controller(bottom_bar_key_controller)

            if self.sort_enabled or self.categories_enabled:
                top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                self.top_bar = top_bar
                top_bar.set_margin_top(10)
                top_bar.set_margin_start(10)
                top_bar.set_margin_end(10)
                if self.sort_enabled:
                    self.button_sort.set_size_request(110, -1)
                    self.button_sort.set_hexpand(True)
                    top_bar.append(self.button_sort)
                if self.categories_enabled:
                    self.button_category.set_size_request(110, -1)
                    self.button_category.set_hexpand(True)
                    top_bar.append(self.button_category)
                box_top.append(top_bar)

            box_top.append(scroll_box)
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
            list_container.append(box_top)
            list_container.append(self.box_bottom)

            self.list_hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.box_main.append(self.list_hbox)
            self.list_hbox.append(self.build_background_container(list_container))

        update_sort_data()

        warmup_child = Gtk.FlowBoxChild()
        warmup_child.set_css_name("entry")
        del warmup_child

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

                if self.carrousel_active():
                    return False

                target = self.first_visible_child()
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

    def carrousel_visible_games(self):
        search_text = self.entry_search.get_text().lower() if hasattr(self, 'entry_search') else ''

        def sort_key(g):
            if self.current_sort_id == "playtime":
                return -self.playtime_data.get(g.gameid, 0)
            if self.current_sort_id == "lastplayed":
                return self.latest_games_order.get(g.gameid, float('inf'))
            if self.current_sort_id == "custom":
                return self.custom_order_data.get(g.gameid, 999999)
            return g.title.lower()

        ordered = sorted(self.games, key=sort_key)
        return [g for g in ordered if self.game_matches_filter(g, search_text)]

    def game_in_category(self, game, category):
        raw_cat = game.category
        if isinstance(raw_cat, str):
            cats = [raw_cat]
        elif isinstance(raw_cat, list):
            cats = raw_cat
        else:
            cats = []

        if category == _("Uncategorized"):
            return not cats or cats == [_("None")]
        return category in (cats or [_("None")])

    def game_matches_filter(self, game, search_text):
        if search_text and search_text not in game.title.lower():
            return False
        if self.categories_enabled and self.current_category and self.current_category != _("All"):
            return self.game_in_category(game, self.current_category)
        return True

    def build_carrousel_slot(self, offset):
        picture = new_picture()
        picture.set_can_shrink(True)

        label = Gtk.Label()
        label.add_css_class("game-label")
        label.set_wrap(True)
        label.set_lines(2)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(1)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_size_request(-1, 50)
        label.set_margin_start(10)
        label.set_margin_end(10)
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.CENTER)

        hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.append(picture)
        hbox.append(label)

        deco_entry = Gtk.Entry()
        deco_entry.set_can_target(False)
        deco_entry.set_focusable(False)
        deco_entry.get_delegate().set_focusable(False)
        deco_entry.set_hexpand(True)
        deco_entry.set_vexpand(True)
        deco_entry.set_width_chars(0)
        deco_entry.set_max_width_chars(0)
        deco_entry.set_size_request(1, 1)
        deco_entry.add_css_class("game")
        deco_entry.add_css_class("list-row-entry")

        anim_box = Gtk.Box()
        anim_box.add_css_class("launch-overlay")
        anim_box.set_hexpand(True)
        anim_box.set_vexpand(True)
        anim_box.set_can_target(False)

        card_overlay = Gtk.Overlay()
        card_overlay.set_child(deco_entry)
        card_overlay.add_overlay(hbox)
        card_overlay.set_measure_overlay(hbox, True)
        card_overlay.add_overlay(anim_box)

        card = GObject.new(Gtk.Box, css_name="entry")
        card.append(card_overlay)
        card.add_css_class("flowbox-entry")
        card.add_css_class("cover-container")
        card.add_css_class("carrousel-cover-box")
        card.set_overflow(Gtk.Overflow.HIDDEN)

        style_provider = Gtk.CssProvider()
        card.get_style_context().add_provider(style_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)

        slot = {
            "box": card,
            "picture": picture,
            "label": label,
            "anim_box": anim_box,
            "style_provider": style_provider,
            "offset": offset,
            "gameid": None,
        }

        click = Gtk.GestureClick()
        click.set_button(Gdk.BUTTON_PRIMARY)
        click.connect("released", lambda g, n, x, y, slot=slot: self.on_carrousel_slot_click(slot, n))
        card.add_controller(click)

        right_click = Gtk.GestureClick()
        right_click.set_button(Gdk.BUTTON_SECONDARY)
        right_click.connect("pressed", lambda g, n, x, y, slot=slot: self.on_carrousel_slot_right_click(slot, x, y))
        card.add_controller(right_click)

        def on_prepare(source, x, y, slot=slot):
            g = getattr(slot["box"], "game", None)
            if not g:
                return None
            self._drag_source_id = g.gameid
            return Gdk.ContentProvider.new_for_value(g.gameid)

        def on_drag_begin(source, drag, slot=slot):
            self.set_drag_icon(source, getattr(slot["box"], "game", None), slot["box"])

        def on_drag_end(source, drag, delete_data):
            self._drag_source_id = None
            if self._carrousel_dnd_timeout_id is not None:
                GLib.source_remove(self._carrousel_dnd_timeout_id)
                self._carrousel_dnd_timeout_id = None
                self.apply_pending_carrousel_reorder()
            if self.current_sort_id == "custom":
                save_json_file(self.custom_order_data, CUSTOM_ORDER)

        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        drag_source.connect("prepare", on_prepare)
        drag_source.connect("drag-begin", on_drag_begin)
        drag_source.connect("drag-end", on_drag_end)
        card.add_controller(drag_source)

        def on_drop_motion(target, x, y, slot=slot):
            if self.current_sort_id != "custom" or not getattr(self, '_drag_source_id', None):
                return 0

            target_g = getattr(slot["box"], "game", None)
            if not target_g:
                return 0

            source_id = self._drag_source_id
            target_id = target_g.gameid
            if source_id != target_id:
                self._carrousel_dnd_pending = (source_id, target_id)
                if self._carrousel_dnd_timeout_id is None:
                    self._carrousel_dnd_timeout_id = GLib.timeout_add(500, self.apply_pending_carrousel_reorder)

            return Gdk.DragAction.MOVE

        drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop_target.connect("motion", on_drop_motion)
        drop_target.connect("drop", lambda target, value, x, y: True)
        card.add_controller(drop_target)

        return slot

    def set_drag_icon(self, source, game, widget):
        try:
            if game and game.icon:
                if os.path.isfile(game.icon):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(game.icon, 48, 48, True)
                    source.set_icon(Gdk.Texture.new_for_pixbuf(pixbuf), 24, 24)
                else:
                    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                    icon_paintable = theme.lookup_icon(
                        game.icon, None, 48, widget.get_scale_factor(),
                        Gtk.TextDirection.NONE, 0)
                    source.set_icon(icon_paintable, 24, 24)
        except Exception:
            pass

    def move_custom_order(self, ordered, source_id, target_id):
        try:
            src = ordered.index(source_id)
            dst = ordered.index(target_id)
        except ValueError:
            return False

        if src == dst:
            return False

        ordered.pop(src)
        ordered.insert(dst, source_id)
        for idx, gid in enumerate(ordered):
            self.custom_order_data[gid] = idx
        return True

    def carrousel_slot_size(self):
        zoom_pct = self.cover_size
        max_width = max(1, int(230 * (zoom_pct / 100.0)))
        max_height = int(max_width * 1.5)
        return max_width, max_height

    def carrousel_scale_opacity(self, offset):
        anchors = (
            (0.0, 1.05, 1.0),
            (1.0, 0.82, 0.75),
            (2.0, 0.62, 0.5),
            (3.0, 0.46, 0.25),
            (4.0, 0.3, 0.0),
        )
        d = abs(offset)
        for (d0, s0, o0), (d1, s1, o1) in zip(anchors, anchors[1:]):
            if d <= d1:
                t = (d - d0) / (d1 - d0)
                return s0 + (s1 - s0) * t, o0 + (o1 - o0) * t
        return anchors[-1][1], anchors[-1][2]

    def carrousel_glow_alpha(self, offset):
        return max(0.0, 1.0 - abs(offset))

    def set_carrousel_slot_content(self, slot, game):
        max_width, max_height = self.carrousel_slot_size()
        surface = self.get_cover_paintable(game, max_width, max_height)
        slot["picture"].set_paintable(surface)
        slot["picture"].set_size_request(max_width, max_height)
        slot["gameid"] = game.gameid
        slot["box"].game = game
        slot["label"].set_text(game.title)
        slot["label"].set_visible(self.labels_enabled)

    def carrousel_radius_for_count(self, n):
        return min(3, n // 2)

    def carrousel_fit_radius(self, n, width):
        max_radius = self.carrousel_radius_for_count(n)
        if max_radius <= 1 or not width or not self.carrousel_step:
            return max_radius
        fit = int((width / self.carrousel_step - 1) / 2)
        return max(1, min(max_radius, fit))

    def carrousel_fan_center(self, extent, align):
        if align == Gtk.Align.CENTER:
            return extent / 2
        margin = min(extent / 2, self.carrousel_radius * self.carrousel_step + self.carrousel_step / 2)
        if align == Gtk.Align.START:
            return margin
        return extent - margin

    def place_carrousel_slot_base(self, slot):
        _, natural_w, _, _ = slot["box"].measure(Gtk.Orientation.HORIZONTAL, -1)
        _, natural_h, _, _ = slot["box"].measure(Gtk.Orientation.VERTICAL, natural_w)
        base_x = self.carrousel_center_x - natural_w / 2
        base_y = self.carrousel_center_y - natural_h / 2
        self.carrousel_fixed.move(slot["box"], base_x, base_y)

    def carrousel_layout_extent(self):
        fixed = getattr(self, 'carrousel_fixed', None)
        if fixed is not None:
            allocated = fixed.get_width()
            if allocated:
                return allocated
        return self.get_width() or 0

    def update_carrousel_layout(self, *_args):
        if not self.carrousel_step or not getattr(self, 'carrousel_slots', None):
            return
        if getattr(self, '_carrousel_layout_tick_id', None) is not None:
            return

        def do_layout(_widget, _frame_clock):
            self._carrousel_layout_tick_id = None
            self.apply_carrousel_layout()
            return GLib.SOURCE_REMOVE

        self._carrousel_layout_tick_id = self.add_tick_callback(do_layout)

    def apply_carrousel_layout(self):
        if not self.carrousel_step or not getattr(self, 'carrousel_slots', None):
            return
        extent = self.carrousel_layout_extent() or self.carrousel_step * 3
        n = len(self.carrousel_visible_games())
        self.carrousel_radius = self.carrousel_fit_radius(n, extent)
        self.carrousel_center_x = self.carrousel_fan_center(extent, self.grid_position_halign())
        for slot in self.carrousel_slots:
            self.place_carrousel_slot_base(slot)
            self.layout_carrousel_slot(slot, slot.get("visual_offset", slot["offset"]))

    def on_carrousel_focus_changed(self, widget, pspec):
        for slot in getattr(self, 'carrousel_slots', []):
            self.layout_carrousel_slot(slot, slot.get("visual_offset", slot["offset"]))

    def layout_carrousel_slot(self, slot, offset):
        scale, opacity = self.carrousel_scale_opacity(offset)
        radius = getattr(self, 'carrousel_radius', 3)
        d = abs(offset)
        if d > radius:
            opacity *= max(0.0, radius + 1 - d)
        translate_x = offset * self.carrousel_step
        slot["box"].set_opacity(opacity)

        can_target = d <= radius + 0.5
        if slot.get("_can_target") != can_target:
            slot["box"].set_can_target(can_target)
            slot["_can_target"] = can_target

        carrousel_fixed = getattr(self, 'carrousel_fixed', None)
        is_focused = carrousel_fixed is not None and carrousel_fixed.get_property("has-focus")
        if not is_focused and d < 0.5:
            scale = 1.0

        for css_class, active in (("carrousel-current", d < 0.5), ("carrousel-focused", is_focused)):
            if active:
                slot["box"].add_css_class(css_class)
            else:
                slot["box"].remove_css_class(css_class)

        glow_t = self.carrousel_glow_alpha(offset)
        if not is_focused:
            glow_t *= 0.5
        box_shadow = "0 6px 14px alpha(black, 0.65)"
        if glow_t > 0.0:
            box_shadow += (
                f", 0 0 8px 2px alpha(@theme_selected_bg_color, {glow_t:.3f}), "
                f"0 0 30px 10px alpha(@theme_selected_bg_color, {glow_t * 0.5:.3f})"
            )
        sliding = self._carrousel_anim_id is not None
        transition = "none" if sliding else "transform 200ms cubic-bezier(0.25, 0.46, 0.45, 0.94)"
        css = (
            f"entry.flowbox-entry.cover-container.carrousel-cover-box {{ "
            f"transition: {transition}; "
            f"transform: translate({translate_x:.2f}px, 0.00px) scale({scale:.4f}); "
            f"box-shadow: {box_shadow}; }}"
        )
        slot["style_provider"].load_from_data(css.encode("utf-8"))

        slot["visual_offset"] = offset

    def build_carrousel_widget(self):
        outer = Gtk.Fixed()
        outer.set_focusable(True)
        outer.set_halign(Gtk.Align.FILL)
        outer.set_valign(self.grid_position_valign())
        outer.set_hexpand(True)
        outer.set_overflow(Gtk.Overflow.HIDDEN)

        carrousel_key = Gtk.EventControllerKey()
        carrousel_key.connect("key-pressed", self.on_carrousel_key)
        outer.add_controller(carrousel_key)
        outer.connect("notify::has-focus", self.on_carrousel_focus_changed)

        carrousel_scroll = Gtk.EventControllerScroll()
        carrousel_scroll.set_flags(Gtk.EventControllerScrollFlags.BOTH_AXES)
        carrousel_scroll.connect("scroll", self.on_carrousel_scroll)
        outer.add_controller(carrousel_scroll)

        self.carrousel_index = 0
        self.carrousel_fixed = outer
        self.carrousel_min_offset = -4
        self.carrousel_max_offset = 4
        self.carrousel_radius = 3
        self._carrousel_anim_id = None
        self._carrousel_dnd_pending = None
        self._carrousel_dnd_timeout_id = None
        self.carrousel_step = 0
        self.carrousel_center_x = 0
        self.carrousel_center_y = 0
        self.carrousel_slots = [
            self.build_carrousel_slot(offset)
            for offset in range(self.carrousel_min_offset, self.carrousel_max_offset + 1)
        ]
        for slot in self.carrousel_slots:
            outer.put(slot["box"], 0, 0)

        self.connect_carrousel_resize()

        return outer

    def connect_carrousel_resize(self):
        surface = self.get_surface()
        if surface is not None:
            surface.connect("notify::width", lambda s, p: self.update_carrousel_layout())
            surface.connect("notify::height", lambda s, p: self.update_carrousel_layout())
        else:
            self.connect("realize", lambda w: self.connect_carrousel_resize())

    def render_carrousel(self):
        if not hasattr(self, 'carrousel_slots'):
            return

        if self._carrousel_anim_id is not None:
            self.carrousel_fixed.remove_tick_callback(self._carrousel_anim_id)
            self._carrousel_anim_id = None

        max_width, max_height = self.carrousel_slot_size()
        glow_margin = 70
        self.carrousel_step = max_width + 20
        cross_size = max_height + 50 + glow_margin * 2
        self.carrousel_fixed.set_size_request(self.carrousel_step * 3, cross_size)

        extent = self.carrousel_layout_extent() or self.carrousel_step * 3

        games = self.carrousel_visible_games()
        n = len(games)
        self.carrousel_radius = self.carrousel_fit_radius(n, extent)
        self.carrousel_center_x = self.carrousel_fan_center(extent, self.grid_position_halign())
        self.carrousel_center_y = cross_size / 2

        if n == 0:
            for slot in self.carrousel_slots:
                slot["picture"].set_paintable(None)
                slot["gameid"] = None
                slot["label"].set_text("")
                slot["box"].game = None
                self.place_carrousel_slot_base(slot)
                slot["box"].set_opacity(0.0)
                slot["box"].set_can_target(False)
                slot["_can_target"] = False
                slot["style_provider"].load_from_data(
                    b"entry.flowbox-entry.cover-container.carrousel-cover-box { transition: none; box-shadow: none; }"
                )
            return

        self.carrousel_index %= n
        for slot in self.carrousel_slots:
            idx = (self.carrousel_index + slot["offset"]) % n
            self.set_carrousel_slot_content(slot, games[idx])
            self.place_carrousel_slot_base(slot)
            self.layout_carrousel_slot(slot, slot["offset"])

        self.schedule_background_update()
        self.update_icon()

    def carrousel_move(self, delta):
        games = self.carrousel_visible_games()
        n = len(games)
        if not games:
            return

        if self._carrousel_anim_id is not None:
            self.carrousel_fixed.remove_tick_callback(self._carrousel_anim_id)
            self._carrousel_anim_id = None
            for slot in self.carrousel_slots:
                slot.pop("_settle_offset", None)
                self.layout_carrousel_slot(slot, slot["offset"])

        self.carrousel_radius = self.carrousel_fit_radius(n, self.carrousel_layout_extent())
        self.carrousel_index = (self.carrousel_index + delta) % n

        span = self.carrousel_max_offset - self.carrousel_min_offset + 1

        for slot in self.carrousel_slots:
            old_offset = slot["offset"]
            raw_offset = old_offset - delta

            if raw_offset < self.carrousel_min_offset or raw_offset > self.carrousel_max_offset:
                new_offset = self.carrousel_min_offset + (raw_offset - self.carrousel_min_offset) % span
                edge = self.carrousel_max_offset if raw_offset > self.carrousel_max_offset else self.carrousel_min_offset
                idx = (self.carrousel_index + new_offset) % n
                self.set_carrousel_slot_content(slot, games[idx])
                slot["anim_from"] = edge
                slot["anim_to"] = edge
                slot["_settle_offset"] = new_offset
            else:
                new_offset = raw_offset
                slot["anim_from"] = slot.get("visual_offset", old_offset)
                slot["anim_to"] = new_offset
                slot["_settle_offset"] = None

            slot["offset"] = new_offset

        self.carrousel_start_animation()
        self.schedule_background_update()
        self.update_icon()

    def apply_pending_carrousel_reorder(self):
        self._carrousel_dnd_timeout_id = None
        pending = self._carrousel_dnd_pending
        self._carrousel_dnd_pending = None
        if not pending:
            return False

        source_id, target_id = pending
        ordered = [g.gameid for g in self.carrousel_visible_games()]

        if self.move_custom_order(ordered, source_id, target_id):
            self.carrousel_resync_after_reorder(source_id)

        return False

    def carrousel_resync_after_reorder(self, anchor_gameid):
        games = self.carrousel_visible_games()
        n = len(games)
        if n == 0:
            return

        for idx, g in enumerate(games):
            if g.gameid == anchor_gameid:
                self.carrousel_index = idx
                break

        for slot in self.carrousel_slots:
            idx = (self.carrousel_index + round(slot["offset"])) % n
            game = games[idx]
            if slot.get("gameid") != game.gameid:
                self.set_carrousel_slot_content(slot, game)

        self.schedule_background_update()
        self.update_icon()

    def carrousel_start_animation(self):
        if self._carrousel_anim_id is not None:
            self.carrousel_fixed.remove_tick_callback(self._carrousel_anim_id)

        start = GLib.get_monotonic_time()
        duration = 260000

        def step(widget, frame_clock):
            elapsed = GLib.get_monotonic_time() - start
            t = min(1.0, elapsed / duration)
            eased = t * t * (3.0 - 2.0 * t)
            for slot in self.carrousel_slots:
                current = slot["anim_from"] + (slot["anim_to"] - slot["anim_from"]) * eased
                self.layout_carrousel_slot(slot, current)
            if t >= 1.0:
                for slot in self.carrousel_slots:
                    settle_offset = slot.pop("_settle_offset", None)
                    if settle_offset is not None:
                        self.layout_carrousel_slot(slot, settle_offset)
                self._carrousel_anim_id = None
                return False
            return True

        self._carrousel_anim_id = self.carrousel_fixed.add_tick_callback(step)

    def get_carrousel_center_slot(self):
        for slot in self.carrousel_slots:
            if abs(slot["offset"]) < 0.5:
                return slot
        return None

    def on_bottom_bar_key(self, controller, keyval, keycode, state):
        if keyval != Gdk.KEY_Up:
            return False
        return navigate_focus(Gtk.DirectionType.UP)

    def on_zoom_scale_key(self, controller, keyval, keycode, state):
        if keyval not in (Gdk.KEY_Left, Gdk.KEY_Right):
            return False
        direction = Gtk.DirectionType.LEFT if keyval == Gdk.KEY_Left else Gtk.DirectionType.RIGHT
        if adjust_widget_value(self.scale_zoom, "left" if keyval == Gdk.KEY_Left else "right"):
            return True
        return navigate_focus(direction)

    def on_search_entry_key(self, controller, keyval, keycode, state):
        if keyval not in (Gdk.KEY_Left, Gdk.KEY_Right):
            return False

        pos = self.entry_search.get_position()
        if keyval == Gdk.KEY_Left and pos != 0:
            return False
        if keyval == Gdk.KEY_Right and pos != len(self.entry_search.get_text()):
            return False

        direction = Gtk.DirectionType.LEFT if keyval == Gdk.KEY_Left else Gtk.DirectionType.RIGHT
        return navigate_focus(direction)

    def on_carrousel_key(self, controller, keyval, keycode, state):
        if not self.carrousel_active():
            return False
        direction = {
            Gdk.KEY_Right: Gtk.DirectionType.RIGHT,
            Gdk.KEY_Left: Gtk.DirectionType.LEFT,
            Gdk.KEY_Down: Gtk.DirectionType.DOWN,
            Gdk.KEY_Up: Gtk.DirectionType.UP,
        }.get(keyval)
        if direction is None:
            return False
        return navigate_focus(direction)

    def on_carrousel_scroll(self, controller, dx, dy):
        if not self.carrousel_active():
            return False

        delta = dy if dy != 0 else dx
        if delta == 0:
            return False

        self.carrousel_fixed.grab_focus()
        self.on_carrousel_focus_changed(self.carrousel_fixed, None)
        carrousel_move_coalesced(self, 1 if delta > 0 else -1)
        return True

    def on_carrousel_slot_click(self, slot, n_press):
        self.carrousel_fixed.grab_focus()
        self.on_carrousel_focus_changed(self.carrousel_fixed, None)

        offset = round(slot["offset"])
        if offset != 0:
            self.carrousel_move(offset)
            return
        if n_press == 2:
            game = self.selected()
            if not game:
                return
            if game.gameid in self.running:
                self.running_dialog(game.title)
            else:
                self.on_button_play_clicked()

    def on_carrousel_slot_right_click(self, slot, x=None, y=None):
        offset = round(slot["offset"])
        if offset != 0:
            self.carrousel_move(offset)

        game = self.selected()
        if not game:
            return

        if x is not None and y is not None:
            rect = self.pointing_rect(x, y)
        else:
            rect = self.pointing_rect(0, 0, slot["box"].get_width() or 1)
        self.open_context_menu(game, slot["box"], rect)

        def on_menu_closed(popover):
            self.carrousel_fixed.grab_focus()
            self.on_carrousel_focus_changed(self.carrousel_fixed, None)

        self.context_menu.connect("closed", on_menu_closed)
        self.context_menu.popup()

    def on_category_button_clicked(self, button):
        popover = Gtk.Popover()
        popover.set_parent(button)
        popover.connect("closed", lambda p: p.unparent())
        self.apply_popover_background_mode(popover)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        categories = [_("All"), _("Uncategorized")] + self._get_current_categories()
        current_label = self.button_category.get_label()
        focus_btn = None

        for cat_name in categories:
            count = self._count_games_in_category(cat_name)
            btn = Gtk.Button(label=f"{cat_name} ({count})")
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
        if self.gamepad_navigation:
            self.active_popover = popover
        popover.popup()

        if focus_btn:
            focus_btn.grab_focus()

    def on_category_menu_item_selected(self, menu_item, category_name):
        self.button_category.set_label(category_name)
        self.current_category = category_name

        if self.carrousel_active():
            self.carrousel_index = 0
            self.render_carrousel()
            return

        self.flowbox.invalidate_filter()
        self.select_first_visible_child()

    def on_manage_categories_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Manage Categories"), transient_for=self)
        apply_titlebar_preference(dialog)
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

                    if self.carrousel_active():
                        self.render_carrousel()
                    else:
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
                if self.carrousel_active():
                    self.render_carrousel()
                else:
                    self.flowbox.invalidate_filter()

        btn_add.connect("clicked", on_add)
        btn_edit.connect("clicked", on_edit)
        btn_remove.connect("clicked", on_remove)

        dialog.connect("response", lambda d, r: destroy_and_release(d))
        dialog.present()

    def _save_categories(self, categories):
        save_json_file(list(categories), CATEGORIES_FILE)

    def _get_current_categories(self):
        return [cat.strip() for cat in load_json_file(CATEGORIES_FILE, default=[]) if cat.strip()]

    def _count_games_in_category(self, category_name):
        if category_name == _("All"):
            return len(self.games)

        return sum(1 for game in self.games if self.game_in_category(game, category_name))

    def _update_games_category(self, old_cat, new_cat):
        try:
            data = load_json_file(GAMES_JSON, [])
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
                save_json_file(data, GAMES_JSON)
                for g in self.games:
                    child_cat = g.category
                    if isinstance(child_cat, str) and child_cat == old_cat:
                        g.category = [new_cat]
                    elif isinstance(child_cat, list) and old_cat in child_cat:
                        child_cat = [new_cat if c == old_cat else c for c in child_cat]
                        g.category = list(dict.fromkeys(child_cat))
        except Exception:
            pass

    def _remove_games_category(self, cat_to_remove):
        try:
            data = load_json_file(GAMES_JSON, [])
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
                save_json_file(data, GAMES_JSON)
                for g in self.games:
                    child_cat = g.category
                    if isinstance(child_cat, str) and child_cat == cat_to_remove:
                        g.category = []
                    elif isinstance(child_cat, list) and cat_to_remove in child_cat:
                        child_cat.remove(cat_to_remove)
                        g.category = child_cat
        except Exception:
            pass

    def show_power_menu(self, widget):
        dialog = Gtk.Dialog(title="Faugus", transient_for=self)
        apply_titlebar_preference(dialog)
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

    def build_context_menu(self, game):
        title = game.title

        label_menu_title = Gtk.Label(label=title)
        label_menu_title.set_halign(Gtk.Align.START)
        label_menu_title.add_css_class("heading")
        label_menu_title.set_margin_bottom(4)

        is_running = game.gameid in self.running

        last_played_text = None
        last_played_exact = None
        data = load_json_file(GAMES_JSON, [])
        for item_data in data:
            if isinstance(item_data, dict) and item_data.get("gameid") == game.gameid:
                last_played_iso = item_data.get("last_played")
                last_played_text = self.format_last_played(last_played_iso)
                if last_played_iso:
                    try:
                        last_played_exact = datetime.fromisoformat(last_played_iso).strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        pass
                if game.runner != "Steam":
                    game.playtime = item_data.get("playtime", 0)
                break

        if game.runner == "Steam":
            steam_minutes = get_steam_app_playtime_minutes(game.path, game.steam_user)
            formatted = self.format_playtime_display(steam_minutes * 60)
        else:
            formatted = self.format_playtime_display(game.playtime)

        label_menu_playtime = Gtk.Label(label=_("Playtime: {}").format(formatted) if formatted else "")
        label_menu_playtime.set_halign(Gtk.Align.START)
        label_menu_playtime.set_margin_bottom(4)
        label_menu_playtime.set_visible(bool(formatted))

        if is_running:
            session_start = self.get_play_session(game)[0]
            playing_for_text = self.format_playing_for(session_start)
            last_played_label_text = _("Playing for: {}").format(playing_for_text) if playing_for_text else ""
            last_played_label_visible = bool(playing_for_text)
        else:
            never_played = not formatted and not last_played_text
            last_played_label_text = (
                _("Last played: {}").format(last_played_text) if last_played_text
                else (_("Never played") if never_played else "")
            )
            last_played_label_visible = bool(last_played_text) or never_played

        label_menu_last_played = Gtk.Label(label=last_played_label_text)
        label_menu_last_played.set_halign(Gtk.Align.START)
        label_menu_last_played.set_margin_bottom(4)
        label_menu_last_played.set_visible(last_played_label_visible)
        if last_played_exact and not is_running:
            label_menu_last_played.set_tooltip_text(last_played_exact)

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_box.set_margin_start(6)
        header_box.set_margin_end(6)
        header_box.set_margin_top(6)
        header_box.append(label_menu_title)
        header_box.append(label_menu_playtime)
        header_box.append(label_menu_last_played)

        self.proton_log = f"{LOGS_DIR}/{game.gameid}/proton.log"
        self.umu_log = f"{LOGS_DIR}/{game.gameid}/umu.log"

        if os.path.exists(self.proton_log):
            self.action_context_show_logs.set_enabled(True)
            self.current_title = title
        else:
            self.action_context_show_logs.set_enabled(False)

        hide_label = _("Remove from hidden") if game.hidden else _("Hide")
        supports_logs = game.runner not in ("Steam", "Linux-Native")
        if is_running:
            play_label = _("Stop")
        elif supports_logs:
            play_label = _("Play with logs")
        else:
            play_label = _("Play")

        categories = sorted(self._get_current_categories(), key=str.lower)

        categories.insert(0, _("None"))

        raw_cat = game.category
        if isinstance(raw_cat, str):
            current_cats = [raw_cat]
        elif isinstance(raw_cat, list):
            current_cats = raw_cat
        else:
            current_cats = []

        if not current_cats:
            current_cats = [_("None")]

        category_menu = Gio.Menu()
        for cat in categories:
            label_text = f"✓ {cat}" if cat in current_cats else f"   {cat}"
            cat_item = Gio.MenuItem.new(label_text, None)
            cat_item.set_action_and_target_value("win.context-category", GLib.Variant.new_string(cat))
            category_menu.append_item(cat_item)

        show_duplicate = game.runner != "Steam"
        show_prefix_location = game.runner != "Linux-Native"

        if game.runner == "Steam":
            steam_game_dir, steam_prefix_dir = get_steam_app_paths(game.path)
            self.current_game = str(steam_game_dir) if steam_game_dir and os.path.isdir(steam_game_dir) else None
            self.current_prefix = str(steam_prefix_dir) if steam_prefix_dir and os.path.isdir(steam_prefix_dir) else None
        else:
            game_prefix = expand_path(game.prefix)
            self.current_game = os.path.dirname(expand_path(game.path)) or None
            self.current_prefix = game_prefix if os.path.isdir(game_prefix) else None

        self.action_context_game_location.set_enabled(self.current_game is not None)
        self.action_context_prefix_location.set_enabled(self.current_prefix is not None)

        root = Gio.Menu()

        header_section = Gio.Menu()
        header_item = Gio.MenuItem.new()
        header_item.set_attribute_value("custom", GLib.Variant.new_string("header"))
        header_section.append_item(header_item)
        root.append_section(None, header_section)

        actions_section = Gio.Menu()
        actions_section.append(play_label, "win.context-play")
        actions_section.append(_("Edit"), "win.context-edit")
        actions_section.append(_("Delete"), "win.context-delete")

        if show_duplicate:
            actions_section.append(_("Duplicate"), "win.context-duplicate")

        actions_section.append(hide_label, "win.context-hide")
        actions_section.append_submenu(_("Category"), category_menu)

        actions_section.append(_("Open game location"), "win.context-game-location")

        if show_prefix_location:
            actions_section.append(_("Open prefix location"), "win.context-prefix-location")

        if supports_logs:
            actions_section.append(_("Show logs"), "win.context-show-logs")

        root.append_section(None, actions_section)

        run_section = Gio.Menu()

        if supports_logs:
            run_section.append(_("Run file in the prefix"), "win.context-run")

            recent_files = load_json_file(RECENT_RUN_FILES, {}).get(game.gameid, [])
            recent_files = [f for f in recent_files if os.path.isfile(f)]
            if recent_files:
                recent_menu = Gio.Menu()
                recent_files_section = Gio.Menu()
                for file_run in recent_files:
                    file_item = Gio.MenuItem.new(os.path.basename(file_run), None)
                    file_item.set_action_and_target_value("win.context-recent-run", GLib.Variant.new_string(file_run))
                    recent_files_section.append_item(file_item)
                recent_menu.append_section(None, recent_files_section)

                recent_clear_section = Gio.Menu()
                recent_clear_section.append(_("Clear recent"), "win.context-clear-recent")
                recent_menu.append_section(None, recent_clear_section)

                run_section.append_submenu(_("Recent"), recent_menu)

        if run_section.get_n_items() > 0:
            root.append_section(None, run_section)

        popover = Gtk.PopoverMenu.new_from_model(root)
        popover.set_has_arrow(False)
        popover.add_child(header_box, "header")
        self.apply_popover_background_mode(popover, game)

        def find_label_text(widget):
            if type(widget).__name__ == "Label":
                return widget.get_text()
            for child in widget_children(widget):
                text = find_label_text(child)
                if text is not None:
                    return text
            return None

        def find_stack(widget):
            if type(widget).__name__ == "Stack":
                return widget
            for child in widget_children(widget):
                found = find_stack(child)
                if found:
                    return found
            return None

        def find_submenu_page(stack, target_label):
            if not stack:
                return None
            for page in widget_children(stack):
                for header in widget_children(page):
                    if type(header).__name__ == "GtkModelButton" and "title" in header.get_css_classes():
                        if find_label_text(header) == target_label:
                            return page
                        break
            return None

        def collect_model_buttons(widget, out):
            if type(widget).__name__ == "GtkModelButton":
                if "title" not in widget.get_css_classes():
                    out.append(widget)
                return
            for child in widget_children(widget):
                collect_model_buttons(child, out)

        if supports_logs and recent_files:
            recent_page = find_submenu_page(find_stack(popover), _("Recent"))
            if recent_page:
                recent_buttons = []
                collect_model_buttons(recent_page, recent_buttons)
                for button, file_run in zip(recent_buttons, recent_files):
                    button.set_tooltip_text(file_run)

        return popover

    def on_item_right_click(self, item=None, x=None, y=None):
        if item is None:
            selected = self.flowbox.get_selected_children()
            item = selected[0] if selected else None

        if not item:
            return

        self.flowbox.emit('child-activated', item)
        self.flowbox.select_child(item)

        game = self.selected()

        rect = None
        if x is not None and y is not None:
            translated = self.flowbox.translate_coordinates(item, x, y)
            if translated is not None:
                rect = self.pointing_rect(*translated)
        else:
            rect = self.pointing_rect(0, 0, item.get_width() or 1)
        self.open_context_menu(game, item, rect)
        self.context_menu.popup()

    def pointing_rect(self, x, y, width=1):
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), width, 1
        return rect

    def open_context_menu(self, game, parent, rect):
        if self.context_menu is not None and self.context_menu.get_parent():
            self.context_menu.popdown()
            self.context_menu.unparent()

        self.context_menu = self.build_context_menu(game)
        self.context_menu.set_parent(parent)
        if rect is not None:
            self.context_menu.set_pointing_to(rect)

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

        parts = []

        if hours > 0:
            parts.append((_("{} hour") if hours == 1 else _("{} hours")).format(hours))

        if minutes > 0:
            parts.append((_("{} minute") if minutes == 1 else _("{} minutes")).format(minutes))

        return " ".join(parts)

    def format_playtime_display(self, seconds):
        if not seconds:
            return None
        return self.format_playtime(seconds) or _("Less than a minute")

    def elapsed_seconds_since(self, start_iso):
        if not start_iso:
            return None

        try:
            started_at = datetime.fromisoformat(start_iso)
        except ValueError:
            return None

        return max(0, (datetime.now() - started_at).total_seconds())

    def format_playing_for(self, start_iso):
        seconds = self.elapsed_seconds_since(start_iso)
        if seconds is None:
            return None
        return self.format_playtime(seconds) or _("Less than a minute")

    def get_play_session(self, game):
        session = self.play_sessions.get(game.gameid)
        if session is not None:
            return session

        if game.gameid not in self.running:
            return None, game.playtime

        pid = self.running.get(game.gameid)
        if isinstance(pid, dict):
            pid = next(iter(pid.values()), None)

        session_start = None
        if pid:
            try:
                import psutil
                session_start = datetime.fromtimestamp(psutil.Process(pid).create_time()).isoformat()
            except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError, OSError):
                pass

        session = (session_start, game.playtime)
        self.play_sessions[game.gameid] = session
        return session

    def format_last_played(self, last_played_iso):
        seconds = self.elapsed_seconds_since(last_played_iso)
        if seconds is None:
            return None

        if seconds < 60:
            return _("Just now")

        minutes = int(seconds // 60)
        if minutes < 60:
            if minutes == 1:
                return _("A minute ago")
            return _("{} minutes ago").format(minutes)

        hours = int(seconds // 3600)
        if hours < 24:
            if hours == 1:
                return _("An hour ago")
            return _("{} hours ago").format(hours)

        days = int(seconds // 86400)
        if days < 7:
            if days == 1:
                return _("Yesterday")
            return _("{} days ago").format(days)

        weeks = int(days // 7)
        if weeks < 4:
            if weeks == 1:
                return _("A week ago")
            return _("{} weeks ago").format(weeks)

        months = int(days // 30)
        if months < 12:
            if months == 1:
                return _("A month ago")
            return _("{} months ago").format(months)

        years = int(days // 365)
        if years == 1:
            return _("A year ago")
        return _("{} years ago").format(years)

    def build_overview_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(10)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_halign(Gtk.Align.CENTER)

        self.label_overview_title = Gtk.Label()
        self.label_overview_title.add_css_class("overview-panel-title")
        self.label_overview_title.set_halign(Gtk.Align.CENTER)
        self.label_overview_title.set_ellipsize(Pango.EllipsizeMode.END)
        box.append(self.label_overview_title)

        separator = Gtk.Box()
        separator.add_css_class("overview-panel-separator")
        separator.set_hexpand(True)
        box.append(separator)

        stats_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        stats_row.set_halign(Gtk.Align.CENTER)

        self.label_overview_categories = Gtk.Label()
        self.label_overview_categories.add_css_class("overview-panel-stat")
        stats_row.append(self.label_overview_categories)

        self.label_overview_sep1 = Gtk.Label(label="•")
        self.label_overview_sep1.add_css_class("overview-panel-stat")
        stats_row.append(self.label_overview_sep1)

        self.label_overview_playtime = Gtk.Label()
        self.label_overview_playtime.add_css_class("overview-panel-stat")
        stats_row.append(self.label_overview_playtime)

        self.label_overview_sep2 = Gtk.Label(label="•")
        self.label_overview_sep2.add_css_class("overview-panel-stat")
        stats_row.append(self.label_overview_sep2)

        self.label_overview_last_played = Gtk.Label()
        self.label_overview_last_played.add_css_class("overview-panel-stat")
        stats_row.append(self.label_overview_last_played)

        box.append(stats_row)

        self.overview_panel = box
        self.connect_overview_panel_resize()
        self.apply_overview_panel_width()
        self.update_overview_panel()
        return box

    def connect_overview_panel_resize(self):
        surface = self.get_surface()
        if surface is not None:
            surface.connect("notify::width", lambda s, p: self.update_overview_panel_width())
            surface.connect("notify::height", lambda s, p: self.update_overview_panel_width())
        else:
            self.connect("realize", lambda w: self.connect_overview_panel_resize())

    def update_overview_panel_width(self):
        if getattr(self, '_overview_width_tick_id', None) is not None:
            return

        def do_resize(_widget, _frame_clock):
            self._overview_width_tick_id = None
            self.apply_overview_panel_width()
            return GLib.SOURCE_REMOVE

        self._overview_width_tick_id = self.add_tick_callback(do_resize)

    def apply_overview_panel_width(self):
        panel = getattr(self, 'overview_panel', None)
        if panel is None:
            return
        width = self.get_width() or self.window_width
        panel.set_size_request(min(1200, max(240, width - 80)), -1)

        overview_r, overview_g, overview_b = self.get_overview_rgb()
        overview_rgb = f"rgb({overview_r}, {overview_g}, {overview_b})"
        overview_transparent = f"rgba({overview_r}, {overview_g}, {overview_b}, 0)"
        add_css_once("overview_panel", f"""
            .overview-panel-title {{
                font-size: 56px;
                font-weight: bold;
                color: {overview_rgb};
                text-shadow: 0 2px 4px alpha(black, 0.6);
            }}
            .overview-panel-separator {{
                margin-top: 20px;
                margin-bottom: 20px;
                min-height: 3px;
                background-image: linear-gradient(to right,
                    {overview_transparent},
                    {overview_rgb} 25%,
                    {overview_rgb} 75%,
                    {overview_transparent}
                );
            }}
            .overview-panel-stat {{
                font-size: 22px;
                color: {overview_rgb};
                text-shadow: 0 1px 3px alpha(black, 0.6);
            }}
        """)

    def update_overview_panel(self):
        panel = getattr(self, 'overview_panel', None)
        if panel is None:
            return

        game = self.selected() if getattr(self, 'overview_enabled', False) else None
        if not game:
            panel.set_visible(False)
            return

        panel.set_visible(True)
        self.apply_overview_panel_width()
        self.label_overview_title.set_text(game.title)

        is_running = game.gameid in self.running
        session_start, session_baseline_playtime = self.get_play_session(game)

        if is_running:
            elapsed = self.elapsed_seconds_since(session_start) or 0
            formatted_playtime = self.format_playtime_display(session_baseline_playtime + elapsed)
        elif game.runner == "Steam":
            steam_minutes = get_steam_app_playtime_minutes(game.path, game.steam_user)
            formatted_playtime = self.format_playtime_display(steam_minutes * 60)
        else:
            formatted_playtime = self.format_playtime_display(game.playtime)
        playtime_visible = bool(formatted_playtime)
        self.label_overview_playtime.set_text(
            _("Playtime: {}").format(formatted_playtime) if formatted_playtime else ""
        )
        self.label_overview_playtime.set_visible(playtime_visible)

        categories = game.category if isinstance(game.category, list) else ([game.category] if game.category else [])
        categories_visible = bool(categories)
        self.label_overview_categories.set_text(", ".join(categories) if categories else "")
        self.label_overview_categories.set_visible(categories_visible)

        if is_running:
            playing_for_text = self.format_playing_for(session_start)
            last_played_visible = bool(playing_for_text)
            self.label_overview_last_played.set_text(
                _("Playing for: {}").format(playing_for_text) if playing_for_text else ""
            )
            self.label_overview_last_played.set_tooltip_text(None)
        else:
            last_played_text = self.format_last_played(game.last_played)
            never_played = not formatted_playtime and not last_played_text
            last_played_visible = bool(last_played_text) or never_played
            self.label_overview_last_played.set_text(
                _("Last played: {}").format(last_played_text) if last_played_text
                else (_("Never played") if never_played else "")
            )
            if game.last_played:
                self.label_overview_last_played.set_tooltip_text(
                    datetime.fromisoformat(game.last_played).strftime("%Y-%m-%d %H:%M")
                )
            else:
                self.label_overview_last_played.set_tooltip_text(None)
        self.label_overview_last_played.set_visible(last_played_visible)

        self.label_overview_sep1.set_visible(playtime_visible and categories_visible)
        self.label_overview_sep2.set_visible((playtime_visible or categories_visible) and last_played_visible)

    def on_context_menu_play(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            supports_logs = game.runner not in ("Steam", "Linux-Native")
            self.on_button_play_clicked(None, game, with_logs=supports_logs)

    def on_context_menu_edit(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_button_edit_clicked(game)

    def on_context_menu_delete(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_button_delete_clicked(game)

    def on_context_menu_duplicate(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_duplicate_clicked()

    def on_context_menu_hide(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if not game:
            return

        try:
            data = load_json_file_or_none(GAMES_JSON)
            if data is None:
                return

            for item in data:
                if item.get("gameid") == game.gameid:
                    item["hidden"] = not item.get("hidden", False)
                    game.hidden = item["hidden"]
                    break

            save_json_file(data, GAMES_JSON)

        except Exception:
            return

        if game.hidden and not self.show_hidden:
            hidden_child = self.find_flowbox_child_for_game(game)
            if hidden_child is not None:
                self.flowbox.remove(hidden_child)
            if game in self.games:
                self.games.remove(game)

            self.select_first_child_when_ready()

    def on_context_menu_category(self, action, param):
        category_name = param.get_string()
        game = self.selected()
        selected_gameid = game.gameid if game else None
        self.context_menu.popdown()
        if not selected_gameid:
            return
        try:
            data = load_json_file_or_none(GAMES_JSON)
            if data is None:
                return

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

                    for g in self.games:
                        if g.gameid == selected_gameid:
                            g.category = current_cats if current_cats else None
                            break
                    break

            save_json_file(data, GAMES_JSON)

        except Exception:
            return

        if self.carrousel_active():
            games = self.carrousel_visible_games()
            for idx, g in enumerate(games):
                if g.gameid == selected_gameid:
                    self.carrousel_index = idx
                    break
            self.render_carrousel()
            return

        self.flowbox.invalidate_filter()

        self.flowbox.unselect_all()

        child_to_select = next((c for c in widget_children(self.flowbox) if c.get_child_visible() and c.game.gameid == selected_gameid), None)
        if child_to_select is None:
            child_to_select = self.first_visible_child()
        if child_to_select is not None:
            self._focus_flowbox_child(child_to_select)

    def on_context_menu_game_location(self, action, param):
        self.context_menu.popdown()
        subprocess.Popen(["xdg-open", self.current_game])

    def on_context_menu_prefix_location(self, action, param):
        self.context_menu.popdown()
        subprocess.Popen(["xdg-open", self.current_prefix])

    def run_file_in_prefix(self, game, file_run):
        prefix = expand_path(game.prefix)
        runner = resolve_game_runner(game.runner)
        title_formatted = game.gameid
        game_directory = os.path.dirname(expand_path(game.path))
        cwd = game_directory if game_directory and os.path.isdir(game_directory) else None
        escaped_file_run = file_run.replace("'", "'\\''")
        command_parts = []

        command_parts.append("FAUGUS_DISABLE_UPDATES=1")
        if title_formatted:
            command_parts.append(f"LOG_DIR={title_formatted}")
        if prefix:
            command_parts.append(f"WINEPREFIX='{prefix}'")
        if runner:
            command_parts.append(f"PROTONPATH='{resolve_protonpath(runner)}'")
        if escaped_file_run.endswith(".reg"):
            command_parts.append(f"'{UMU_RUN}' regedit '{escaped_file_run}'")
        else:
            command_parts.append(f"'{UMU_RUN}' '{escaped_file_run}'")

        command = ' '.join(command_parts)
        cmd = (sys.executable, "-m", "faugus.runner", command)
        subprocess.Popen(cmd, cwd=cwd, env=subprocess_env())

        self.record_recent_run_file(game.gameid, file_run)

    def record_recent_run_file(self, gameid, file_run):
        data = load_json_file(RECENT_RUN_FILES, {})
        files = [f for f in data.get(gameid, []) if f != file_run]
        files.insert(0, file_run)
        data[gameid] = files[:5]
        save_json_file(data, RECENT_RUN_FILES)

    def on_context_menu_run(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if not game:
            return
        filechooser = new_file_chooser(
            self,
            _("Select a file to run in the prefix"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "run_in_prefix")

        add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                file_run = dialog_fc.get_file().get_path()
                self.run_file_in_prefix(game, file_run)

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_context_menu_recent_run(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if not game:
            return
        file_run = param.get_string()
        if os.path.isfile(file_run):
            self.run_file_in_prefix(game, file_run)

    def on_context_menu_clear_recent(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if not game:
            return
        data = load_json_file(RECENT_RUN_FILES, {})
        if game.gameid in data:
            del data[game.gameid]
            save_json_file(data, RECENT_RUN_FILES)

    def on_context_show_logs(self, action, param):
        self.context_menu.popdown()
        game = self.selected()
        if game:
            self.on_show_logs_clicked()

    def on_show_logs_clicked(self):
        dialog = Gtk.Dialog(title=_("%s Logs") % self.current_title, transient_for=self)
        apply_titlebar_preference(dialog)
        hide_dialog_action_area(dialog)
        dialog.set_modal(True)
        dialog.set_default_size(1280, 720)

        notebook = Gtk.Notebook()
        notebook.set_margin_start(10)
        notebook.set_margin_end(10)
        notebook.set_margin_top(10)
        notebook.set_margin_bottom(10)
        notebook.set_halign(Gtk.Align.FILL)
        notebook.set_valign(Gtk.Align.FILL)
        notebook.set_vexpand(True)
        notebook.set_hexpand(True)

        def add_log_page(log_path, tab_title):
            scrolled_window = Gtk.ScrolledWindow()
            scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            text_view = Gtk.TextView()
            text_view.set_editable(False)
            text_buffer = text_view.get_buffer()
            with open(log_path, "r") as log_file:
                text_buffer.set_text(log_file.read())
            scrolled_window.set_child(text_view)

            tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            tab_label = Gtk.Label(label=tab_title)
            tab_label.set_width_chars(15)
            tab_label.set_xalign(0.5)
            tab_label.set_hexpand(True)
            tab_box.append(tab_label)
            tab_box.set_hexpand(True)

            notebook.append_page(scrolled_window, tab_box)
            return text_buffer

        text_buffers = (
            add_log_page(self.proton_log, "Proton"),
            add_log_page(self.umu_log, "UMU-Launcher"),
        )

        def copy_to_clipboard(button):
            text_buffer = text_buffers[notebook.get_current_page()]
            start_iter, end_iter = text_buffer.get_bounds()
            dialog.get_clipboard().set(text_buffer.get_text(start_iter, end_iter, False))

        def open_location(button):
            subprocess.run(["xdg-open", os.path.dirname(self.proton_log)], check=True)

        button_copy_clipboard = Gtk.Button(label=_("Copy to clipboard"))
        button_copy_clipboard.set_hexpand(True)
        button_copy_clipboard.connect("clicked", copy_to_clipboard)

        button_open_location = Gtk.Button(label=_("Open file location"))
        button_open_location.set_hexpand(True)
        button_open_location.connect("clicked", open_location)

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

    def _existing_gameids(self):
        ids = {g.gameid for g in self.games}
        ids.update(g.get("gameid") for g in load_json_file(GAMES_JSON, []))
        return ids

    def on_duplicate_clicked(self):
        game = self.selected()

        load_red_entry_css()

        dup_dialog = DuplicateDialog(self, game.title)
        dup_dialog.connect("response", self._on_confirm_duplicate_response, game)

    def _on_confirm_duplicate_response(self, dialog, response, game):
        if response != Gtk.ResponseType.OK:
            destroy_and_release(dialog)
            return

        new_title = dialog.entry_title.get_text().strip()
        title_formatted = format_title(new_title)

        if not new_title or not title_formatted:
            dialog.entry_title.add_css_class("entry")
            return

        if any(new_title.casefold() == g.title.casefold() for g in self.games):
            self.show_warning_dialog_main(
                dialog,
                _("%s already exists") % new_title,
                ""
            )
            return

        base_gameid = title_formatted
        title_formatted = unique_gameid(base_gameid, self._existing_gameids())
        if title_formatted != base_gameid:
            print(f"Faugus Launcher: game ID '{base_gameid}' already in use, assigned '{title_formatted}'")

        icon = game.icon
        new_icon = f"{ICONS_DIR}/{title_formatted}.png"
        if os.path.exists(icon):
            shutil.copyfile(icon, new_icon)

        cover = game.cover
        new_cover = f"{COVERS_DIR}/{title_formatted}.png"
        if os.path.exists(cover):
            shutil.copyfile(cover, new_cover)
        else:
            new_cover = ""

        banner = f"{BANNERS_DIR}/{game.gameid}.png"
        if os.path.isfile(banner):
            shutil.copyfile(banner, f"{BANNERS_DIR}/{title_formatted}.png")

        new_addapp_bat = f"{os.path.dirname(expand_path(game.path))}/faugus-{title_formatted}.bat"
        if os.path.exists(expand_path(game.addapp_bat)):
            shutil.copyfile(expand_path(game.addapp_bat), new_addapp_bat)

        game_dict = game_to_dict(game)
        if isinstance(game_dict["category"], list):
            game_dict["category"] = list(game_dict["category"])
        game_dict["gameid"] = title_formatted
        game_dict["title"] = new_title
        game_dict["icon"] = new_icon
        game_dict["cover"] = new_cover
        game_dict["addapp_bat"] = new_addapp_bat

        new_game = Game(**game_dict)

        self.games.append(new_game)
        self.save_games()

        self.show_new_game(new_game)

        destroy_and_release(dialog)

    def on_item_release_event(self, gesture, n_press, x, y):
        current_item = self.flowbox.get_child_at_pos(int(x), int(y))
        if not current_item:
            return

        self.flowbox.select_child(current_item)
        if n_press == 2:
            self.on_item_double_click(current_item)

    def on_item_double_click(self, item):
        self.play_or_notify(self.selected())

    def on_key_press_event(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_h and state & Gdk.ModifierType.CONTROL_MASK:
            try:
                config = ConfigManager()
                current = config.config.get("show-hidden", "False")
                new_value = "False" if current == "True" else "True"
                config.set_value("show-hidden", new_value)
                config.save_config()

                self.show_hidden = new_value == "True"
                self.apply_show_hidden_change()
                self.select_first_child_when_ready()
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

        if not self.carrousel_active() and not self.flowbox.get_selected_children()[0].is_focus():
            return False

        if keyval == Gdk.KEY_Return:
            self.play_or_notify(game)

        if keyval == Gdk.KEY_Delete:
            self.on_button_delete_clicked()

        return False

    def running_dialog(self, title):
        show_message_dialog(_("%s is running") % title, parent=self)

    def play_or_notify(self, game):
        if game.gameid in self.running:
            self.running_dialog(game.title)
        else:
            self.on_button_play_clicked()

    def load_config(self):
        cfg = ConfigManager()

        self.system_tray = cfg.config.get('system-tray', 'False') == 'True'
        self.mono_icon = cfg.config.get('mono-icon', 'False') == 'True'
        self.auto_close_on_launch = cfg.config.get('auto-close-on-launch', 'False') == 'True'
        self.interface_mode = cfg.config.get('interface-mode', '').strip('"')
        self.background_mode = cfg.config.get('background-mode', 'default').strip('"')
        self.overview_color_mode = cfg.config.get('overview-color-mode', 'default').strip('"')
        self.widget_color_mode = cfg.config.get('widget-color-mode', 'default').strip('"')
        self.background_color = cfg.config.get('background-color', 'rgb(61,174,233)').strip('"')
        self.overview_color = cfg.config.get('overview-color', 'rgb(61,174,233)').strip('"')
        self.theme_engine = cfg.config.get('theme-engine', 'adwaita').strip('"')
        self.accent_color = cfg.get_accent_color()
        self.banner_enabled = cfg.config.get('banner-enabled', 'True') == 'True'
        self.steamgriddb_enabled = cfg.config.get('steamgriddb-enabled', 'False') == 'True'
        self.labels_enabled = cfg.config.get('labels-enabled', 'False') == 'True'
        self.zoom_enabled = cfg.config.get('zoom-enabled', 'True') == 'True'
        self.gamepad_navigation = cfg.config.get('gamepad-navigation', 'False') == 'True'
        self.language = cfg.config.get('language', '')
        self.show_hidden = cfg.config.get('show-hidden', 'False') == 'True'
        self.categories_enabled = cfg.config.get('categories-enabled', 'False') == 'True'
        self.sort_enabled = cfg.config.get('sort-enabled', 'False') == 'True'
        self.header_bar = cfg.config.get('header-bar', 'False') == 'True'
        self.startup_window_size = cfg.config.get('startup-window-size', '')
        self.window_width = int(cfg.config.get('width', 1280))
        self.window_height = int(cfg.config.get('height', 720))
        self.cover_size = int(cfg.config.get('cover-size', 100))
        self.grid_position = cfg.config.get('grid-position', 'Middle').strip('"')
        self.grid_orientation = cfg.config.get('grid-orientation', 'Vertical').strip('"')
        grid_max_children_enabled = cfg.config.get('grid-max-children-enabled', 'False') == 'True'
        self.grid_max_children_per_line = int(cfg.config.get('grid-max-children-per-line', 20)) if grid_max_children_enabled else 20
        self.overview_enabled = cfg.config.get('overview-enabled', 'False') == 'True'
        self.sort = cfg.config.get('sort', '')
        self.category = cfg.config.get('category', '')
        self.steam_user = cfg.config.get('steam-user', 'all')

    def load_games(self):
        games_data = load_json_file(GAMES_JSON, [])

        self.games.clear()
        for game_data in games_data:
            game = Game(**prepare_game_kwargs(game_data))

            if not self.show_hidden and game.hidden:
                continue

            self.games.append(game)

        self.games = sorted(self.games, key=lambda x: x.title.lower())

        if self.carrousel_active():
            self.render_carrousel()
            return

        w = self.get_focus()
        while w is not None:
            if w is self.flowbox:
                self.set_focus(None)
                break
            w = w.get_parent()

        self.flowbox.remove_all()
        self.populate_flowbox_incremental()

    def populate_flowbox_incremental(self, batch_size=8):
        games_iter = iter(self.games)

        generation = object()
        self._flowbox_populate_generation = generation

        def step():
            if getattr(self, '_flowbox_populate_generation', None) is not generation:
                return False

            for _ in range(batch_size):
                game = next(games_iter, None)
                if game is None:
                    return False
                self.add_item_list(game)

            return True

        GLib.idle_add(step)

    def schedule_zoom_apply(self, zoom_pct):
        if getattr(self, '_zoom_apply_source', None):
            GLib.source_remove(self._zoom_apply_source)

        def fire():
            self._zoom_apply_source = None
            self.apply_zoom_incremental(zoom_pct)
            return False

        self._zoom_apply_source = GLib.timeout_add(150, fire)

    def apply_zoom_incremental(self, zoom_pct, batch_size=15):
        if self.carrousel_active():
            self.render_carrousel()
            return

        if self.interface_mode not in ("Covers", "Carrousel"):
            return

        children_iter = iter(widget_children(self.flowbox))

        generation = object()
        self._zoom_apply_generation = generation

        zoom_width, zoom_height = self.cover_dimensions(zoom_pct)

        def step():
            if getattr(self, '_zoom_apply_generation', None) is not generation:
                return False

            for _ in range(batch_size):
                child = next(children_iter, None)
                if child is None:
                    return False

                if not hasattr(child, 'game') or not child.game or not hasattr(child, 'cover'):
                    continue

                game = child.game
                surface = self.get_cover_paintable(game, zoom_width, zoom_height)
                child.cover.set_paintable(surface)

            return True

        GLib.idle_add(step)

    def add_item_list(self, game):
        zoom_pct = self.cover_size

        if self.interface_mode == "List":
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        if self.interface_mode == "Grid":
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            hbox.set_size_request(200, -1)
        if self.interface_mode in ("Covers", "Carrousel"):
            hbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        game_label = Gtk.Label.new(game.title)
        game_label.add_css_class("game-label")

        if self.interface_mode in ("Grid", "Covers", "Carrousel"):
            game_label.set_wrap(True)
            game_label.set_lines(2)
            game_label.set_ellipsize(Pango.EllipsizeMode.END)
            game_label.set_max_width_chars(1)
            game_label.set_justify(Gtk.Justification.CENTER)

        child = Gtk.FlowBoxChild()
        child.game = game
        child.label = game_label
        child.hbox = hbox
        child.add_css_class("flowbox-entry")
        child.set_css_name("entry")

        anim_box = Gtk.Box()
        anim_box.add_css_class("launch-overlay")
        anim_box.set_hexpand(True)
        anim_box.set_vexpand(True)
        child.anim_box = anim_box

        if self.interface_mode == "List":
            surface = self.get_game_artwork(game, 40, 40)
            image = new_picture(surface)

            child.image = image

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

            child.set_size_request(300, -1)
            self.flowbox.set_homogeneous(True)
            child.set_valign(Gtk.Align.START)
            child.set_halign(Gtk.Align.FILL)

        if self.interface_mode == "Grid":
            child.set_hexpand(True)
            child.set_vexpand(True)

            block_size = 100

            surface = self.get_game_artwork(game, block_size, block_size)
            image = new_picture(surface)

            child.image = image

            image.set_margin_top(10)
            game_label.set_margin_top(10)
            game_label.set_margin_start(10)
            game_label.set_margin_end(10)
            game_label.set_margin_bottom(10)

            hbox.append(image)
            game_label.set_vexpand(True)
            game_label.set_valign(Gtk.Align.CENTER)
            hbox.append(game_label)

            child.set_valign(Gtk.Align.FILL)
            child.set_halign(Gtk.Align.FILL)

        if self.interface_mode in ("Covers", "Carrousel"):
            child.add_css_class("cover-container")
            child.set_hexpand(True)
            child.set_vexpand(True)

            image2 = new_picture()
            child.cover = image2

            game_label.set_size_request(-1, 50)
            game_label.set_margin_start(10)
            game_label.set_margin_end(10)

            child.set_margin_start(10)
            child.set_margin_end(10)
            child.set_margin_top(10)
            child.set_margin_bottom(10)

            child.set_valign(Gtk.Align.FILL)
            child.set_halign(Gtk.Align.FILL)

            zoom_width, zoom_height = self.cover_dimensions(zoom_pct)

            surface = self.get_cover_paintable(game, zoom_width, zoom_height)
            image2.set_paintable(surface)

            hbox.append(image2)

            child.set_overflow(Gtk.Overflow.HIDDEN)

            game_label.set_visible(self.labels_enabled)
            game_label.set_vexpand(True)
            game_label.set_valign(Gtk.Align.CENTER)
            hbox.append(game_label)

        overlay = Gtk.Overlay()
        deco_entry = Gtk.Entry()
        deco_entry.set_can_target(False)
        deco_entry.set_focusable(False)
        deco_entry.get_delegate().set_focusable(False)
        deco_entry.set_hexpand(True)
        deco_entry.set_vexpand(True)
        deco_entry.set_width_chars(0)
        deco_entry.set_max_width_chars(0)
        deco_entry.add_css_class("game")
        deco_entry.add_css_class("list-row-entry")
        overlay.set_child(deco_entry)
        overlay.add_overlay(hbox)
        overlay.set_measure_overlay(hbox, True)
        overlay.add_overlay(anim_box)
        anim_box.set_can_target(False)
        child.set_child(overlay)

        self.flowbox.append(child)
        self.setup_dnd_for_widget(child)

    def update_game_visual(self, flowbox_child):
        game = flowbox_child.game

        if hasattr(flowbox_child, "image"):
            size = 40 if self.interface_mode == "List" else 100
            flowbox_child.image.set_paintable(self.get_game_artwork(game, size, size))

        if hasattr(flowbox_child, "cover"):
            zoom_width, zoom_height = self.cover_dimensions(getattr(self, "cover_size", 100))

            surface = self.get_cover_paintable(game, zoom_width, zoom_height)
            flowbox_child.cover.set_paintable(surface)

    def cover_dimensions(self, zoom_pct):
        zoom_width = int(230 * (zoom_pct / 100.0))
        return zoom_width, int(zoom_width * 1.5)

    def get_game_artwork(self, game, width, height):
        path = game.icon if os.path.isfile(game.icon) else FAUGUS_PNG
        pixbuf = safe_load_pixbuf(path, width * HIDPI_SCALE, height * HIDPI_SCALE, False)

        if not self.is_game_installed(game):
            pixbuf.saturate_and_pixelate(pixbuf, 0.0, False)

        return HiDpiPaintable(Gdk.Texture.new_for_pixbuf(pixbuf), width, height)

    def get_cover_texture(self, path, installed):
        if not hasattr(self, '_cover_texture_cache'):
            self._cover_texture_cache = {}

        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None

        cache_key = (path, mtime, installed)
        texture = self._cover_texture_cache.get(cache_key)
        if texture is not None:
            return texture

        for key in [k for k in self._cover_texture_cache if k[0] == path]:
            del self._cover_texture_cache[key]

        pixbuf = safe_load_pixbuf(path, None, None, False)
        if not installed:
            pixbuf.saturate_and_pixelate(pixbuf, 0.0, False)

        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self._cover_texture_cache[cache_key] = texture
        return texture

    def get_cover_paintable(self, game, width, height):
        if not os.path.isfile(game.cover):
            return create_accent_placeholder_paintable(width, height, rgb=self.get_accent_rgb())

        texture = self.get_cover_texture(game.cover, self.is_game_installed(game))
        return HiDpiPaintable(texture, width, height)

    def is_game_installed(self, game):
        if game.runner == "Steam":
            steam_user = game.steam_user or None
            cache = getattr(self, '_installed_games_cache', None)
            if cache is None:
                cache = {}
                self._installed_games_cache = cache

            now = GLib.get_monotonic_time()
            entry = cache.get(steam_user)
            if entry is None or (now - entry[0]) > 3_000_000:
                entry = (now, read_installed_games(steam_user))
                cache[steam_user] = entry

            for appid, name in entry[1]:
                if str(game.path) == str(appid) or game.title.lower() == name.lower():
                    return True
            return False

        return os.path.exists(expand_path(game.path))

    def on_search_changed(self, entry):
        if self.carrousel_active():
            self.carrousel_index = 0
            self.render_carrousel()
            return

        self.flowbox.invalidate_filter()

        self.select_first_visible_child()

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

        settings_dialog.present()

    def apply_tray_settings(self, new_system_tray, new_mono_icon):
        tray_needs_reload = (
            self.system_tray != new_system_tray or
            self.mono_icon != new_mono_icon
        )

        if tray_needs_reload and new_system_tray and not self.tray_daemon_running()[1]:
            os.execv(sys.executable, [sys.executable, '-m', 'faugus.tray_only'])

        self.system_tray = new_system_tray
        self.mono_icon = new_mono_icon

        return tray_needs_reload and self.ensure_tray_daemon(force_restart=True)

    def on_settings_dialog_response(self, dialog, response_id, settings_dialog):
        if faugus_backup:
            os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

        if response_id == Gtk.ResponseType.OK:
            settings_dialog.commit_pending_envar_edit()
            if not self.validate_settings_fields(settings_dialog, settings_dialog.entry_default_prefix.get_text()):
                return

            apply_interface_customization(
                settings_dialog.interface_theme,
                settings_dialog.accent_color,
                settings_dialog.combobox_theme_engine.get_active_id(),
            )
            self.apply_overview_panel_width()

            self.save_interface_settings()
            settings_dialog.update_config_file()
            self.manage_autostart_file(settings_dialog.checkbox_autostart.get_active(), settings_dialog.checkbox_minimized_startup.get_active())

            if self.apply_tray_settings(settings_dialog.checkbox_system_tray.get_active(), settings_dialog.checkbox_mono_icon.get_active()):
                return

            new_grid_max_children = int(settings_dialog.entry_grid_max_children.get_value()) if settings_dialog.checkbox_grid_max_children.get_active() else 20
            if (self.interface_mode != settings_dialog.combobox_interface.get_active_id()
                    or self.background_mode != settings_dialog.combobox_background.get_active_id()
                    or self.widget_color_mode != settings_dialog.combobox_widget_color.get_active_id()
                    or self.theme_engine != settings_dialog.combobox_theme_engine.get_active_id()
                    or self.banner_enabled != settings_dialog.checkbox_banner.get_active()
                    or self.labels_enabled != settings_dialog.checkbox_labels.get_active()
                    or self.zoom_enabled != settings_dialog.checkbox_zoom.get_active()
                    or self.grid_position != settings_dialog.combobox_grid_position.get_active_id()
                    or self.grid_orientation != settings_dialog.combobox_grid_orientation.get_active_id()
                    or self.grid_max_children_per_line != new_grid_max_children
                    or self.overview_enabled != settings_dialog.checkbox_overview.get_active()
                    or self.language != settings_dialog.combobox_language.get_active_id()
                    or self.gamepad_navigation != settings_dialog.checkbox_gamepad_navigation.get_active()
                    or self.categories_enabled != settings_dialog.checkbox_categories.get_active()
                    or self.sort_enabled != settings_dialog.checkbox_sort.get_active()
                    or self.header_bar != settings_dialog.checkbox_header_bar.get_active()):
                os.execv(sys.executable, [sys.executable, '-m', 'faugus.launcher'] + sys.argv[1:])

            settings_dialog.update_envar_file()

            hidden_changed = self.show_hidden != settings_dialog.checkbox_hidden_games.get_active()
            self.load_config()
            if hidden_changed:
                self.apply_show_hidden_change()

            destroy_and_release(settings_dialog)

        else:
            apply_interface_customization(
                settings_dialog.original_interface_theme,
                settings_dialog.original_accent_color,
                settings_dialog.original_theme_engine,
            )
            self.background_color = settings_dialog.original_background_color
            self.overview_color = settings_dialog.original_overview_color
            self.apply_background_mode_live(settings_dialog.original_background_mode)
            self.overview_color_mode = settings_dialog.original_overview_color_mode
            self.apply_overview_panel_width()
            destroy_and_release(settings_dialog)

    def validate_settings_fields(self, settings_dialog, default_prefix):
        settings_dialog.entry_default_prefix.remove_css_class("entry")
        settings_dialog.entry_steamgriddb_key.remove_css_class("entry")

        valid = True

        if not default_prefix:
            settings_dialog.entry_default_prefix.add_css_class("entry")
            valid = False

        if (settings_dialog.checkbox_steamgriddb.get_active()
                and not settings_dialog.entry_steamgriddb_key.get_text().strip()):
            settings_dialog.entry_steamgriddb_key.add_css_class("entry")
            valid = False

        return valid

    def manage_autostart_file(self, autostart_enabled, minimized_startup_enabled):
        autostart_path = PathManager.user_home('.config/autostart/faugus-launcher.desktop')
        os.makedirs(os.path.dirname(autostart_path), exist_ok=True)

        if autostart_enabled:
            hide_arg = " --hide" if minimized_startup_enabled else ""
            if IS_FLATPAK:
                exec_cmd = "flatpak run io.github.Faugus.faugus-launcher"
                icon = "io.github.Faugus.faugus-launcher"
            else:
                exec_cmd = f"{LAUNCHER_PATH} {LAUNCHER_MODULE_ARGS}"
                icon = "faugus-launcher"

            with open(autostart_path, "w") as f:
                f.write(
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    "Name=Faugus\n"
                    f"Exec={exec_cmd}{hide_arg}\n"
                    f"Icon={icon}\n"
                    "Categories=Game;\n"
                    "StartupWMClass=faugus-launcher\n"
                )
        else:
            if os.path.exists(autostart_path):
                os.remove(autostart_path)

    def on_button_play_clicked(self, widget=None, game=None, with_logs=False):
        self.button_play.set_sensitive(False)

        def reenable():
            self.button_play.set_sensitive(True)
            return False
        GLib.timeout_add(1000, reenable)

        if game is None:
            game = self.selected()

        if not game:
            return

        if self.carrousel_active():
            center_slot = self.get_carrousel_center_slot() if hasattr(self, 'carrousel_slots') else None
            anim_box = center_slot.get("anim_box") if center_slot else None
        else:
            anim_box = None
            selected = self.flowbox.get_selected_children()
            if selected:
                self.update_game_visual(selected[0])
                anim_box = getattr(selected[0], 'anim_box', None)

        if anim_box:
            anim_box.add_css_class("playing")

            def remove_anim():
                anim_box.remove_css_class("playing")
                return False
            GLib.timeout_add(150, remove_anim)

        gameid = game.gameid
        game_directory = os.path.dirname(expand_path(game.path))
        cwd = game_directory if game_directory and os.path.isdir(game_directory) else None

        cmd = [sys.executable, "-m", "faugus.runner", "--game", gameid]
        if with_logs:
            cmd.append("--logs")

        if game.runner == "Steam":
            self.update_last_played(gameid)
            self.sync_last_played_order(gameid)
            subprocess.Popen(cmd, cwd=cwd, env=subprocess_env())
            return

        if gameid in self.running:
            self.stop_running_game(gameid)

            self.running.pop(gameid, None)
            self.processes.pop(gameid, None)
            self.play_sessions.pop(gameid, None)
            self.save_running()
            self.update_icon()
            return

        proc = subprocess.Popen(cmd, cwd=cwd, env=subprocess_env())

        if not IS_FLATPAK or not self.auto_close_on_launch:
            self.running[gameid] = proc.pid
            self.processes[gameid] = proc
            self.play_sessions[gameid] = (datetime.now().isoformat(), game.playtime)
            self.save_running()
            self.update_overview_panel()

        if self.auto_close_on_launch:
            sys.exit()

        self.update_icon()

    def stop_running_game(self, gameid):
        try:
            os.kill(self.running[gameid], signal.SIGUSR1)
        except ProcessLookupError:
            pass
        kill_by_faugusid(gameid)

        session = self.play_sessions.get(gameid)
        if session:
            elapsed = self.elapsed_seconds_since(session[0])
            if elapsed:
                self.update_last_played(gameid, playtime=session[1] + int(elapsed))

    def on_exit(self, pid, status, game):
        self.running.pop(game, None)
        self.processes.pop(game, None)
        self.play_sessions.pop(game, None)
        self.save_running()

        self.reload_playtimes()
        self.sync_last_played_order(game)

        if self.current_sort_id == "playtime":
            try:
                data = load_json_file(GAMES_JSON, [])
                for item in data:
                    if isinstance(item, dict) and "gameid" in item:
                        self.playtime_data[item["gameid"]] = item.get("playtime", 0)
            except:
                pass

            GLib.idle_add(self.flowbox.invalidate_sort)

        GLib.idle_add(self.update_icon)
        GLib.idle_add(self.update_overview_panel)

    def update_last_played(self, gameid, playtime=None):
        games = load_json_file(GAMES_JSON, default=[])

        timestamp = datetime.now().isoformat()
        for entry in games:
            if isinstance(entry, dict) and entry.get("gameid") == gameid:
                entry["last_played"] = timestamp
                if playtime is not None:
                    entry["playtime"] = playtime
                break

        save_json_file(games, GAMES_JSON)
        self.notify_tray_menu_changed()

        for game in self.games:
            if game.gameid == gameid:
                game.last_played = timestamp
                if playtime is not None:
                    game.playtime = playtime
                break
        self.update_overview_panel()

    def sync_last_played_order(self, gameid):
        if self.current_sort_id != "lastplayed":
            return

        self.latest_games_order.clear()
        try:
            for item in load_json_file(GAMES_JSON, default=[]):
                if not isinstance(item, dict) or "gameid" not in item:
                    continue
                last_played = item.get("last_played")
                if last_played:
                    try:
                        self.latest_games_order[item["gameid"]] = -datetime.fromisoformat(last_played).timestamp()
                    except ValueError:
                        pass
        except:
            pass

        self.flowbox.invalidate_sort()
        if self.carrousel_active() and getattr(self, 'carrousel_slots', None):
            self.carrousel_resync_after_reorder(gameid)

    def on_button_kill_clicked(self, widget):
        for gameid in list(self.running):
            self.stop_running_game(gameid)

        self.running.clear()
        self.processes.clear()
        self.play_sessions.clear()
        self.save_running()
        self.update_icon()

        subprocess.run(r"""
    for pid in $(ls -l /proc/*/exe 2>/dev/null | grep -E 'wine(64)?-preloader|wineserver|winedevice.exe' | awk -F'/' '{print $3}'); do
        kill -9 "$pid"
    done
""", shell=True)

    def on_button_add_clicked(self, widget):

        add_game_dialog = AddGame(self, self.interface_mode)
        add_game_dialog.connect("response", self.on_dialog_response, add_game_dialog)

        add_game_dialog.present()

    def on_window_file_drop(self, drop_target, value, x, y):
        files = value.get_files()
        if not files:
            return False

        file_path = files[0].get_path()
        if not file_path or not os.path.isfile(file_path):
            return False

        windows_extensions = (".exe", ".msi", ".bat", ".lnk", ".reg")
        launcher_id = "windows" if file_path.lower().endswith(windows_extensions) else "linux"

        add_game_dialog = AddGame(self, self.interface_mode)
        add_game_dialog.connect("response", self.on_dialog_response, add_game_dialog)

        add_game_dialog.combobox_launcher.set_active_id_silent(launcher_id)
        add_game_dialog.on_combobox_changed(add_game_dialog.combobox_launcher, skip_cleanup=True)
        add_game_dialog.entry_path.set_text(file_path)

        add_game_dialog.present()
        return True

    def on_button_edit_clicked(self, widget):
        game = self.selected()
        edit_game_dialog = AddGame(self, self.interface_mode)
        edit_game_dialog.connect("response", self.on_edit_dialog_response, edit_game_dialog, game)

        game_runner = game.runner

        if game_runner == "Linux-Native":
            edit_game_dialog.combobox_launcher.set_active_id_silent("linux")
            edit_game_dialog.on_combobox_changed(edit_game_dialog.combobox_launcher, skip_cleanup=True)
            edit_game_dialog.combobox_runtime.set_active_id_silent(
                game.runtime or ("disable-runtime" if game.disable_umu else "umu-steamrt4")
            )
        if game_runner == "Steam":
            edit_game_dialog.combobox_launcher.set_active_id_silent("steam")
            edit_game_dialog.on_combobox_changed(edit_game_dialog.combobox_launcher, skip_cleanup=True)

        if getattr(game, 'steam_user', ''):
            persona_name = dict(edit_game_dialog.steam_users).get(game.steam_user, game.steam_user)
            edit_game_dialog.combobox_steam_user.append(
                game.steam_user, f"{persona_name} ({game.steam_user})", short_text=persona_name)
            edit_game_dialog.combobox_steam_user.set_active_id_silent(game.steam_user)
            edit_game_dialog.populate_steam_title_combobox(game.steam_user)

        if game_runner == "Steam" and game.path:
            edit_game_dialog.combobox_steam_title.set_active_id_silent(game.path)

        if game_runner != "Default":
            edit_game_dialog.checkbox_custom_runner.set_active(True)
            if not edit_game_dialog.combobox_runner.set_active_id(game_runner):
                edit_game_dialog.combobox_runner.set_active(0)
        edit_game_dialog.set_title_silently(game.title)
        edit_game_dialog._steamgriddb_suggestion_id = getattr(game, "steamgriddb_id", "") or None
        edit_game_dialog._steamgriddb_steam_appid = game.path if game_runner == "Steam" else None
        edit_game_dialog.entry_path.set_text(game.path)
        edit_game_dialog.entry_prefix.set_text(game.prefix)
        edit_game_dialog.launch_arguments = game.launch_arguments
        edit_game_dialog.pre_launch = game.pre_launch
        edit_game_dialog.post_launch = game.post_launch
        edit_game_dialog.entry_game_arguments.set_text(game.game_arguments)
        edit_game_dialog.set_title(_("Edit %s") % game.title)
        edit_game_dialog.entry_protonfix.set_text(game.protonfix)
        edit_game_dialog.grid_launcher.set_visible(False)
        edit_game_dialog.button_path_action.set_visible(False)
        edit_game_dialog.button_search.set_visible(True)

        edit_game_dialog.addapp_enabled = game.addapp_enabled
        edit_game_dialog.addapp = game.addapp
        edit_game_dialog.addapp_delay = game.addapp_delay
        edit_game_dialog.addapp_first = game.addapp_first

        edit_game_dialog.lossless_enabled = game.lossless_enabled
        edit_game_dialog.lossless_multiplier = game.lossless_multiplier
        edit_game_dialog.lossless_flow = game.lossless_flow
        edit_game_dialog.lossless_performance = game.lossless_performance
        edit_game_dialog.lossless_hdr = game.lossless_hdr
        edit_game_dialog.lossless_present = game.lossless_present

        if os.path.isfile(game.cover):
            shutil.copyfile(game.cover, edit_game_dialog.cover_path_temp)
        elif os.path.isfile(edit_game_dialog.cover_path_temp):
            os.remove(edit_game_dialog.cover_path_temp)
        edit_game_dialog.update_image_cover()

        banner_path = f"{BANNERS_DIR}/{game.gameid}.png"
        if os.path.isfile(banner_path):
            shutil.copyfile(banner_path, edit_game_dialog.banner_path_temp)
            edit_game_dialog.update_banner_preview(edit_game_dialog.banner_path_temp)

        icon_path = game.icon
        if not os.path.isfile(icon_path):
            icon_path = FAUGUS_PNG

        shutil.copyfile(icon_path, edit_game_dialog.icon_temp)
        surface = self.new_texture_from_image(icon_path, 50, 50)
        image = new_picture(surface)
        edit_game_dialog.button_shortcut_icon.set_child(image)

        if os.path.exists(MANGOHUD_DIR):
            edit_game_dialog.checkbox_mangohud.set_active(game.mangohud == True)

        if os.path.exists(GAMEMODERUN) or os.path.exists("/usr/games/gamemoderun"):
            edit_game_dialog.checkbox_gamemode.set_active(game.gamemode == True)

        edit_game_dialog.checkbox_sdl.set_active(game.sdl_enabled == True)
        edit_game_dialog.checkbox_no_sleep.set_active(game.no_sleep == True)

        if edit_game_dialog.steam_shortcut_users:
            matched_user = self.find_steam_shortcut_user(game.title)
            if matched_user:
                edit_game_dialog.combobox_steam_shortcut_user.set_active_id(matched_user)
                edit_game_dialog.checkbox_shortcut_steam.set_active(True)
            else:
                edit_game_dialog.checkbox_shortcut_steam.set_active(False)

        edit_game_dialog.check_existing_shortcut(game.gameid)

        edit_game_dialog.combobox_steam_title.set_sensitive(False)
        edit_game_dialog.combobox_steam_user.set_sensitive(False)
        edit_game_dialog.entry_title.handler_block(edit_game_dialog.update_prefix_entry_handler_id)

        if game.gameid in self.running:
            edit_game_dialog.button_winetricks.set_sensitive(False)
            edit_game_dialog.button_winetricks.set_tooltip_text(_("%s is running") % game.title)

    def check_steam_shortcut(self, title, steam_user=None):
        for path in get_all_shortcut_paths(steam_user if steam_user is not None else self.steam_user):
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        shortcuts = vdf.binary_load(f)
                    if "shortcuts" in shortcuts:
                        for game in shortcuts["shortcuts"].values():
                            if isinstance(game, dict) and game.get("AppName") == title:
                                return True
                except SyntaxError:
                    continue
        return False

    def find_steam_shortcut_user(self, title):
        for account_id, _ in read_steam_users():
            if self.check_steam_shortcut(title, account_id):
                return account_id
        return None

    def on_button_delete_clicked(self, *_):
        self.reload_playtimes()
        game = self.selected()
        delete_dialog = DeleteDialog(self, game.title, game.prefix, game.runner)
        delete_dialog.connect("response", self._on_confirm_delete_response, game)

    def _on_confirm_delete_response(self, dialog, response, game):
        remove_prefix = dialog.checkbox_remove_prefix.get_active()
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
                prefix_path = expand_path(game.prefix)

                try:
                    shutil.rmtree(prefix_path)
                except PermissionError:
                    try:
                        os.system(f'chmod -R u+rwX "{prefix_path}"')
                        shutil.rmtree(prefix_path)
                    except Exception as e2:
                        self.show_warning_dialog_main(
                            self,
                            _("Failed to remove prefix"),
                            str(e2)
                        )
                except FileNotFoundError:
                    pass

            self.remove_shortcut(game, "both")
            self.remove_steam_shortcut(title)
            self.remove_cover_icon(game)

            addapp_bat_path = expand_path(game.addapp_bat)
            if os.path.exists(addapp_bat_path):
                os.remove(addapp_bat_path)

            self._deleted_gameid = gameid
            self.save_games()

            deleted_child = self.find_flowbox_child_for_game(game)
            if deleted_child is not None:
                self.flowbox.remove(deleted_child)
            if game in self.games:
                self.games.remove(game)

            self.remove_latest_and_order(gameid)
            self.select_first_child_when_ready()

    def reload_playtimes(self):
        games_data = load_json_file(GAMES_JSON, [])
        if not games_data:
            return

        data_map = {g["gameid"]: g for g in games_data if isinstance(g, dict) and "gameid" in g}

        for game in self.games:
            entry = data_map.get(game.gameid)
            if entry:
                game.playtime = entry.get("playtime", 0)
                game.last_played = entry.get("last_played", game.last_played)

    def remove_steam_shortcut(self, title, steam_user=None):
        for path in get_all_shortcut_paths(steam_user if steam_user is not None else self.steam_user):
            if os.path.exists(path):
                try:
                    with open(path, 'rb') as f:
                        shortcuts = vdf.binary_load(f)

                    if "shortcuts" not in shortcuts:
                        continue

                    to_remove = [app_id for app_id, game in shortcuts["shortcuts"].items() if
                                 isinstance(game, dict) and game.get("AppName") == title]

                    if to_remove:
                        for app_id in to_remove:
                            del shortcuts["shortcuts"][app_id]

                        renumber_shortcuts(shortcuts)

                        with open(path, 'wb') as f:
                            vdf.binary_dump(shortcuts, f)
                except SyntaxError:
                    pass

    def remove_latest_and_order(self, gameid):
        custom_order_data = load_json_file(CUSTOM_ORDER, default={})
        if gameid in custom_order_data:
            del custom_order_data[gameid]
            save_json_file(custom_order_data, CUSTOM_ORDER)

        self.notify_tray_menu_changed()

    def show_warning_dialog_main(self, parent, text1, text2, callback=None):
        show_message_dialog(text1, text2, parent=parent, callback=callback)

    def on_dialog_response(self, dialog, response_id, add_game_dialog):
        cover_path_temp = add_game_dialog.cover_path_temp
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

            games = load_json_file(GAMES_JSON, [])

            if any(game.get("title", "").casefold() == title.casefold() for game in games):
                    self.show_warning_dialog_main(
                        add_game_dialog,
                        _("%s already exists") % title,
                        ""
                    )
                    return True

            path = add_game_dialog.entry_path.get_text()
            launch_arguments = add_game_dialog.launch_arguments
            game_arguments = add_game_dialog.entry_game_arguments.get_text()
            protonfix = add_game_dialog.entry_protonfix.get_text()
            runner = add_game_dialog.selected_runner()
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

            if launcher_id in LAUNCHER_EXE_PATHS:
                path = f"{prefix}/{LAUNCHER_EXE_PATHS[launcher_id]}"

            base_gameid = format_title(title)
            title_formatted = unique_gameid(base_gameid, self._existing_gameids())
            if title_formatted != base_gameid:
                print(f"Faugus Launcher: game ID '{base_gameid}' already in use, assigned '{title_formatted}'")

            addapp_bat = f"{os.path.dirname(expand_path(path))}/faugus-{title_formatted}.bat"

            if self.interface_mode in ("Covers", "Carrousel"):
                temp_cover_path = add_game_dialog.cover_path_temp
                if os.path.isfile(temp_cover_path):
                    cover = os.path.join(COVERS_DIR, f"{title_formatted}.png")
                    self.resize_temp_image(temp_cover_path, cover, 460, 690, "cover")
                else:
                    cover = ""

                self.save_temp_banner(add_game_dialog.banner_path_temp, title_formatted)
            else:
                cover = ""

            icon_temp = os.path.expanduser(add_game_dialog.icon_temp)
            icon_final = f'{add_game_dialog.icons_path}/{title_formatted}.png'
            icon = icon_final

            if launcher_id == "linux":
                runner = "Linux-Native"
            if launcher_id == "steam":
                runner = "Steam"

            if runner == "Steam":
                mangohud = ""
                gamemode = ""
                sdl_enabled = ""
                addapp_enabled = ""
                no_sleep = ""
            else:
                mangohud = True if add_game_dialog.checkbox_mangohud.get_active() else ""
                gamemode = True if add_game_dialog.checkbox_gamemode.get_active() else ""
                sdl_enabled = True if add_game_dialog.checkbox_sdl.get_active() else ""
                addapp_enabled = "addapp_enabled" if add_game_dialog.addapp_enabled else ""
                no_sleep = True if add_game_dialog.checkbox_no_sleep.get_active() else ""

            disable_umu = True if (
                launcher_id == "linux" and add_game_dialog.combobox_runtime.get_active_id() == "disable-runtime"
            ) else ""

            game = Game(
                title_formatted,
                title,
                path,
                prefix,
                launch_arguments,
                game_arguments,
                mangohud,
                gamemode,
                sdl_enabled,
                protonfix,
                runner,
                addapp_enabled,
                addapp,
                addapp_bat,
                addapp_delay,
                addapp_first,
                cover,
                lossless_enabled,
                lossless_multiplier,
                lossless_flow,
                lossless_performance,
                lossless_hdr,
                lossless_present,
                playtime,
                hidden,
                no_sleep,
                category,
                icon,
                steamgriddb_id=add_game_dialog._steamgriddb_suggestion_id or "",
                pre_launch=add_game_dialog.pre_launch,
                post_launch=add_game_dialog.post_launch,
                steam_user=add_game_dialog.combobox_steam_user.get_active_id() if launcher_id == "steam" else "",
                disable_umu=disable_umu,
                runtime=add_game_dialog.combobox_runtime.get_active_id()
            )

            desktop_shortcut_state = add_game_dialog.checkbox_shortcut_desktop.get_active()
            appmenu_shortcut_state = add_game_dialog.checkbox_shortcut_appmenu.get_active()
            steam_shortcut_state = add_game_dialog.checkbox_shortcut_steam.get_active()
            steam_shortcut_user_selected = add_game_dialog.combobox_steam_shortcut_user.get_active_id()

            def check_internet_connection():
                import socket
                try:
                    socket.gethostbyname("github.com")
                    return True
                except socket.gaierror:
                    return False

            if launcher_id not in ("windows", "linux", "steam"):
                if not check_internet_connection():
                    self.show_warning_dialog_main(add_game_dialog, _("No internet connection"), "")
                    return True

                destroy_add_game_dialog()
                dialog_destroyed = True
                self.launcher_screen(
                    title, launcher_id, title_formatted, runner, prefix,
                    game, desktop_shortcut_state, appmenu_shortcut_state,
                    steam_shortcut_state, icon_temp, icon_final, steam_shortcut_user_selected
                )

            self.games.append(game)
            self.save_games()

            if launcher_id in ("windows", "linux", "steam"):
                self.add_game_shortcuts(game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, steam_shortcut_user_selected)

                if addapp_enabled == "addapp_enabled":
                    write_addapp_bat(addapp_bat, path, addapp, addapp_delay, addapp_first, game_arguments)

                self.show_new_game(game)

        else:
            def finish_cancel():
                if os.path.isfile(add_game_dialog.icon_temp):
                    os.remove(add_game_dialog.icon_temp)
                if os.path.isdir(add_game_dialog.icon_directory):
                    shutil.rmtree(add_game_dialog.icon_directory)
                destroy_add_game_dialog()

            prefixes = add_game_dialog.created_prefixes
            if prefixes:
                prefix_list = "\n".join(prefixes)
                question = (
                    _("Do you want to discard these prefixes?") if len(prefixes) > 1
                    else _("Do you want to discard this prefix?")
                )

                def on_discard_confirmed(confirmed):
                    if confirmed:
                        for prefix in prefixes:
                            shutil.rmtree(prefix, ignore_errors=True)
                    finish_cancel()

                show_message_dialog(
                    question,
                    prefix_list,
                    parent=add_game_dialog,
                    confirm_label=_("Yes"),
                    cancel_label=_("No"),
                    callback=on_discard_confirmed,
                )
            else:
                finish_cancel()
            dialog_destroyed = True
        if os.path.isfile(cover_path_temp):
            os.remove(cover_path_temp)
        if not dialog_destroyed:
            destroy_add_game_dialog()

    def launcher_screen(self, title, launcher, title_formatted, runner, prefix, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, steam_user=None):
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
        self.label_download.set_size_request(256, -1)

        self.label_download2 = Gtk.Label()
        self.label_download2.set_margin_start(20)
        self.label_download2.set_margin_end(20)
        self.label_download2.set_margin_bottom(20)
        self.label_download2.set_visible(False)
        self.label_download2.set_size_request(256, -1)

        launcher_names = {
            "amazon": "Amazon Games",
            "battle": "Battle.net",
            "ea": "EA App",
            "epic": "Epic Games",
            "gog": "GOG Galaxy",
            "rockstar": "Rockstar Launcher",
            "ubisoft": "Ubisoft Connect",
            "wargaming": "Wargaming Game Center",
        }
        self.label_download.set_text(_("Downloading") + f" {launcher_names[launcher]}...")
        self.download_launcher(launcher, title, title_formatted, runner, prefix, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, steam_user)

        if self.steamgriddb_enabled and os.path.isfile(icon_temp):
            icon_surface = self.new_texture_from_image(icon_temp, 256, 256)
            icon_picture = new_picture(icon_surface)
            icon_picture.set_margin_bottom(20)
            grid_launcher.attach(icon_picture, 0, 0, 1, 1)

        grid_launcher.attach(sizer_labels, 0, 1, 1, 1)
        sizer_labels.append(grid_labels)
        grid_labels.attach(self.label_download, 0, 0, 1, 1)
        grid_labels.attach(self.bar_download, 0, 1, 1, 1)
        grid_labels.attach(self.label_download2, 0, 2, 1, 1)

        if self.interface_mode != "List":
            self.box_main.remove(self.main_hbox)
        else:
            self.box_main.remove(self.list_hbox)

        banner_path = f"{BANNERS_DIR}/{title_formatted}.png"
        if self.banner_overlay_enabled() and os.path.isfile(banner_path):
            self.box_launcher_display = self.wrap_with_static_banner(self.box_launcher, banner_path)
        else:
            self.box_launcher_display = self.wrap_launcher_no_banner(self.box_launcher)
        self.box_main.append(self.box_launcher_display)

    def monitor_process(self, processo, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, title, steam_user=None):
        retcode = processo.poll()

        if retcode is not None:
            if os.path.exists(FAUGUS_TEMP):
                shutil.rmtree(FAUGUS_TEMP)
            self.box_main.remove(self.box_launcher_display)
            self.launcher_banner_base_provider = None
            self.launcher_banner_provider = None
            self.launcher_banner_path = None
            self.launcher_banner_dominant_rgb = None
            if self.interface_mode != "List":
                self.box_main.append(self.main_hbox)
            else:
                self.box_main.append(self.list_hbox)

            if game.gameid == "ea-app":
                game.path = update_ea_path(game.prefix)

            if os.path.exists(expand_path(game.path)):
                if not self.steamgriddb_enabled:
                    extracted_icon = self.extract_best_icon(expand_path(game.path), game.gameid)

                    if extracted_icon:
                        icon_temp = extracted_icon
                        icon_final = icon_temp
                print(f"{title} installed.")
                self.add_game_shortcuts(game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, steam_user)
                self.show_new_game(game)
            else:
                if os.path.exists(expand_path(game.prefix)):
                    shutil.rmtree(expand_path(game.prefix))
                self.remove_shortcut(game, "both")
                self.remove_steam_shortcut(title)
                self.remove_cover_icon(game)

                removed_child = self.find_flowbox_child_for_game(game)
                if removed_child is not None:
                    self.flowbox.remove(removed_child)
                self.games.remove(game)

                self.save_games()
                self.remove_latest_and_order(game.gameid)
                self.show_warning_dialog_main(self, _("%s was not installed!") % title, "")

            return False

        return True

    def extract_best_icon(self, exe_path, gameid):
        os.makedirs(ICONS_DIR, exist_ok=True)
        final = os.path.join(ICONS_DIR, f"{gameid}.png")
        status = extract_ico(exe_path, final)
        return final if status == "ok" else None

    def download_launcher(self, launcher, title, title_formatted, runner, prefix, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, steam_user=None):
            urls = {"amazon": "https://download.amazongames.com/AmazonGamesSetup.exe",
                "battle": "https://downloader.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe",
                "ea": "https://origin-a.akamaihd.net/EA-Desktop-Client-Download/installer-releases/EAappInstaller.exe",
                "epic": "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi",
                "gog": "https://github.com/Faugus/components/releases/download/v1.0.1/gog.tar.gz",
                "rockstar": "https://gamedownloads.rockstargames.com/public/installer/Rockstar-Games-Launcher.exe",
                "ubisoft": "https://static3.cdn.ubi.com/orbit/launcher_installer/UbisoftConnectInstaller.exe",
                "wargaming": "https://redirect.wargaming.net/WGC/Wargaming_Game_Center_Install_NA.exe"}

            file_name = {"amazon": "AmazonGamesSetup.exe", "battle": "Battle.net-Setup.exe", "ea": "EAappInstaller.exe",
                "epic": "EpicGamesLauncherInstaller.msi", "gog": "gog.tar.gz",
                "rockstar": "Rockstar-Games-Launcher.exe", "ubisoft": "UbisoftConnectInstaller.exe",
                "wargaming": "wargaming_game_center_install_na_dgp3m1ci2u7l.exe"}

            os.makedirs(FAUGUS_TEMP, exist_ok=True)
            file_path = os.path.join(FAUGUS_TEMP, file_name[launcher])

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
                if launcher == "amazon":
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{file_path}'"
                elif launcher == "battle":
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 WINE_SIMULATE_WRITECOPY=1 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{file_path}' --installpath='C:\\Program Files (x86)\\Battle.net' --lang=enUS"
                elif launcher == "ea":
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{file_path}' /S"
                elif launcher == "epic":
                    self.label_download2.set_text("")
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} msiexec /i '{file_path}' /passive"
                elif launcher == "gog":
                    self.label_download2.set_text("")
                    import tarfile
                    with tarfile.open(file_path, "r:gz") as tar:
                        tar.extractall(path=FAUGUS_TEMP, filter="fully_trusted")

                    installer_path = os.path.join(FAUGUS_TEMP, "gog", "GalaxySetup.exe")
                    command = f"LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{installer_path}' /VERYSILENT /NORESTART /SUPPRESSMSGBOXES"
                elif launcher == "rockstar":
                    self.label_download.set_text(_("Please don't change the installation path."))
                    self.label_download2.set_text(_("Please close the login window and wait."))
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{file_path}'"
                elif launcher == "ubisoft":
                    self.label_download2.set_text("")
                    command = f"PROTON_ENABLE_WAYLAND=0 LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{file_path}' /S"
                elif launcher == "wargaming":
                    self.label_download2.set_text(_("Please close Wargaming to finish the installation."))
                    command = f"LOG_DIR='{title_formatted}' WINEPREFIX='{prefix}' {UMU_RUN} '{file_path}' /SILENT"

                if runner:
                    command = f"PROTONPATH='{resolve_protonpath(runner)}' {command}"

                self.bar_download.set_visible(False)
                self.label_download2.set_visible(True)
                processo = subprocess.Popen([sys.executable, "-m", "faugus.runner", command], env=subprocess_env())
                GLib.timeout_add(100, self.monitor_process, processo, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, title, steam_user)

            run_in_background(start_download)

    def on_edit_dialog_response(self, dialog, response_id, edit_game_dialog, game):
        if response_id == Gtk.ResponseType.OK:
            if not edit_game_dialog.validate_fields(entry="path+prefix"):
                return True
            game.title = edit_game_dialog.entry_title.get_text()
            game.path = edit_game_dialog.entry_path.get_text()
            game.prefix = os.path.normpath(edit_game_dialog.entry_prefix.get_text())
            game.launch_arguments = edit_game_dialog.launch_arguments
            game.pre_launch = edit_game_dialog.pre_launch
            game.post_launch = edit_game_dialog.post_launch
            game.game_arguments = edit_game_dialog.entry_game_arguments.get_text()
            game.mangohud = edit_game_dialog.checkbox_mangohud.get_active()
            game.gamemode = edit_game_dialog.checkbox_gamemode.get_active()
            game.sdl_enabled = edit_game_dialog.checkbox_sdl.get_active()
            game.protonfix = edit_game_dialog.entry_protonfix.get_text()
            game.runner = edit_game_dialog.selected_runner()
            game.addapp_enabled = edit_game_dialog.addapp_enabled
            game.addapp = edit_game_dialog.addapp
            game.addapp_delay = edit_game_dialog.addapp_delay
            game.addapp_first = edit_game_dialog.addapp_first
            game.lossless_enabled = edit_game_dialog.lossless_enabled
            game.lossless_multiplier = edit_game_dialog.lossless_multiplier
            game.lossless_flow = edit_game_dialog.lossless_flow
            game.lossless_performance = edit_game_dialog.lossless_performance
            game.lossless_hdr = edit_game_dialog.lossless_hdr
            game.lossless_present = edit_game_dialog.lossless_present
            game.no_sleep = edit_game_dialog.checkbox_no_sleep.get_active()
            game.steamgriddb_id = edit_game_dialog._steamgriddb_suggestion_id or ""

            game.addapp_bat = f"{os.path.dirname(expand_path(game.path))}/faugus-{game.gameid}.bat"

            if self.interface_mode in ("Covers", "Carrousel"):
                temp_cover_path = edit_game_dialog.cover_path_temp
                if os.path.isfile(temp_cover_path):
                    cover = os.path.join(COVERS_DIR, f"{game.gameid}.png")
                    if self.resize_temp_image(temp_cover_path, cover, 460, 690, "cover"):
                        game.cover = cover
                else:
                    game.cover = ""

                self.save_temp_banner(edit_game_dialog.banner_path_temp, game.gameid)

            icon_temp = os.path.expanduser(edit_game_dialog.icon_temp)
            icon_final = f'{edit_game_dialog.icons_path}/{game.gameid}.png'
            game.icon = icon_final

            legacy_icon = f'{edit_game_dialog.icons_path}/{game.gameid}.ico'
            if os.path.isfile(legacy_icon):
                os.remove(legacy_icon)

            if edit_game_dialog.combobox_launcher.get_active_id() == "linux":
                game.runner = "Linux-Native"
                game.runtime = edit_game_dialog.combobox_runtime.get_active_id()
                game.disable_umu = True if game.runtime == "disable-runtime" else ""
            else:
                game.disable_umu = ""
            if edit_game_dialog.combobox_launcher.get_active_id() == "steam":
                game.runner = "Steam"
                game.steam_user = edit_game_dialog.combobox_steam_user.get_active_id()

            desktop_shortcut_state = edit_game_dialog.checkbox_shortcut_desktop.get_active()
            appmenu_shortcut_state = edit_game_dialog.checkbox_shortcut_appmenu.get_active()
            steam_shortcut_state = edit_game_dialog.checkbox_shortcut_steam.get_active()

            self.add_game_shortcuts(game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, edit_game_dialog.combobox_steam_shortcut_user.get_active_id())

            if game.addapp_enabled:
                write_addapp_bat(game.addapp_bat, game.path, game.addapp, game.addapp_delay, game.addapp_first, game.game_arguments)

            self.save_games()

            edited_child = self.find_flowbox_child_for_game(game)
            if edited_child is not None:
                edited_child.label.set_text(game.title)
                self.update_game_visual(edited_child)

            self.flowbox.invalidate_sort()

            self.select_game_by_title(game.title)
            self.launcher_banner_dominant_rgb = None
            self.apply_background_update_now()
        else:
            if os.path.isfile(edit_game_dialog.icon_temp):
                os.remove(edit_game_dialog.icon_temp)

        if os.path.isdir(edit_game_dialog.icon_directory):
            shutil.rmtree(edit_game_dialog.icon_directory)
        if os.path.isfile(edit_game_dialog.cover_path_temp):
            os.remove(edit_game_dialog.cover_path_temp)
        edit_game_dialog.closed_event.set()
        destroy_and_release(edit_game_dialog)

    def resize_temp_image(self, temp_path, dest, width, height, kind):
        try:
            resize_image_file(temp_path, dest, width, height)
            return True
        except Exception as e:
            print(f"Error resizing {kind}: {e}")
            return False

    def save_temp_banner(self, temp_banner_path, gameid):
        if os.path.isfile(temp_banner_path):
            self.resize_temp_image(temp_banner_path, os.path.join(BANNERS_DIR, f"{gameid}.png"), 1920, 620, "banner")

    def show_new_game(self, game):
        self.add_item_list(game)
        self.flowbox.invalidate_sort()
        self.entry_search.set_text("")
        self.select_game_by_title(game.title)

    def add_game_shortcuts(self, game, desktop_shortcut_state, appmenu_shortcut_state, steam_shortcut_state, icon_temp, icon_final, steam_user):
        self.add_shortcut(game, desktop_shortcut_state, "desktop", icon_temp, icon_final)
        self.add_shortcut(game, appmenu_shortcut_state, "appmenu", icon_temp, icon_final)
        self.add_steam_shortcut(game, steam_shortcut_state, icon_temp, icon_final, steam_user)

    def add_shortcut(self, game, shortcut_state, shortcut, icon_temp, icon_final):
        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        if not shortcut_state:
            self.remove_shortcut(game, shortcut)
            return

        new_icon_path = f"{ICONS_DIR}/{game.gameid}.png"
        if not os.path.exists(new_icon_path):
            new_icon_path = FAUGUS_PNG

        game_directory = os.path.dirname(expand_path(game.path))
        desktop_file_content = build_desktop_file_content(
            game.title, f'--game {game.gameid}', new_icon_path, game_directory
        )

        os.makedirs(APP_DIR, exist_ok=True)
        os.makedirs(DESKTOP_DIR, exist_ok=True)

        shortcut_path = f"{DESKTOP_DIR if shortcut == 'desktop' else APP_DIR}/{game.gameid}.desktop"
        with open(shortcut_path, 'w') as shortcut_file:
            shortcut_file.write(desktop_file_content)
        os.chmod(shortcut_path, 0o755)

    def add_steam_shortcut(self, game, steam_shortcut_state, icon_temp, icon_final, steam_user=None):
        steam_user = steam_user if steam_user is not None else self.steam_user

        def add_game_to_steam(title, game_directory, icon):
            for path in get_all_shortcut_paths(steam_user):
                shortcuts = load_shortcuts(path)

                if "shortcuts" not in shortcuts:
                    shortcuts["shortcuts"] = {}

                existing_app_id = None
                for app_id, game_info in shortcuts["shortcuts"].items():
                    if isinstance(game_info, dict) and game_info.get("AppName") == title:
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
                        launch_options = f'--host {LAUNCHER_PATH} {LAUNCHER_MODULE_ARGS}--game {game.gameid}'
                    else:
                        exe = f'"{LAUNCHER_PATH}"'
                        launch_options = f'{LAUNCHER_MODULE_ARGS}--game {game.gameid}'

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

                cover_src = f"{COVERS_DIR}/{game.gameid}.png"
                banner_src = f"{BANNERS_DIR}/{game.gameid}.png"

                if os.path.isfile(cover_src):
                    shutil.copy2(cover_src, os.path.join(grid_dir, f"{asset_id}p.png"))

                if os.path.isfile(banner_src):
                    shutil.copy2(banner_src, os.path.join(grid_dir, f"{asset_id}_hero.png"))

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

        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        if not steam_shortcut_state:
            self.remove_steam_shortcut(game.title, steam_user)
            return

        new_icon_path = f"{ICONS_DIR}/{game.gameid}.png"
        if not os.path.exists(new_icon_path):
            new_icon_path = FAUGUS_PNG

        game_directory = os.path.dirname(expand_path(game.path))

        add_game_to_steam(game.title, game_directory, new_icon_path)

    def remove_cover_icon(self, game):
        for directory in (COVERS_DIR, ICONS_DIR, BANNERS_DIR):
            file_path = f"{directory}/{game.gameid}.png"
            if os.path.exists(file_path):
                os.remove(file_path)

    def remove_shortcut(self, game, shortcut):
        applications_shortcut_path = f"{APP_DIR}/{game.gameid}.desktop"
        desktop_shortcut_path = f"{DESKTOP_DIR}/{game.gameid}.desktop"

        if shortcut in ("appmenu", "both") and os.path.exists(applications_shortcut_path):
            os.remove(applications_shortcut_path)
        if shortcut in ("desktop", "both") and os.path.exists(desktop_shortcut_path):
            os.remove(desktop_shortcut_path)

    def apply_show_hidden_change(self):
        if self.show_hidden:
            existing_ids = {g.gameid for g in self.games}
            games_data = load_json_file(GAMES_JSON, [])

            for game_data in games_data:
                if game_data.get("hidden") and game_data.get("gameid") not in existing_ids:
                    game = Game(**prepare_game_kwargs(game_data))
                    self.games.append(game)
                    self.add_item_list(game)

            self.flowbox.invalidate_sort()
        else:
            for game in [g for g in self.games if g.hidden]:
                child = self.find_flowbox_child_for_game(game)
                if child is not None:
                    self.flowbox.remove(child)
                self.games.remove(game)

    def save_games(self):
        all_games_data = load_json_file_or_none(GAMES_JSON)
        if all_games_data is None:
            return

        deleted_id = getattr(self, "_deleted_gameid", None)
        visible_ids = {game.gameid for game in self.games}

        hidden_games_data = [
            game_data for game_data in all_games_data
            if game_data.get("hidden", False)
            and game_data.get("gameid") not in visible_ids
            and game_data.get("gameid") != deleted_id
        ]

        new_games_data = [
            game_to_save_dict(game) for game in self.games
            if game.gameid != deleted_id
        ] + hidden_games_data

        if hasattr(self, "_deleted_gameid"):
            del self._deleted_gameid

        self.backup_games()

        save_json_file(new_games_data, GAMES_JSON)

    def backup_games(self):
        if os.path.isfile(GAMES_JSON):
            os.makedirs(BACKUP_DIR, exist_ok=True)

            now = GLib.DateTime.new_now_local()
            timestamp = now.format("%Y-%m-%d_%H-%M-%S")

            backup_file = os.path.join(
                BACKUP_DIR,
                f"games-data-{timestamp}.json"
            )

            shutil.copy2(GAMES_JSON, backup_file)

            backups = sorted(
                f for f in os.listdir(BACKUP_DIR)
                if f.startswith("games-data-") and f.endswith(".json")
            )

            while len(backups) > 20:
                oldest = backups.pop(0)
                os.remove(os.path.join(BACKUP_DIR, oldest))


class Settings(Gtk.Dialog):
    CHECKBOX_SETTINGS = (
        ("auto-close-on-launch", "checkbox_auto_close_on_launch", False),
        ("mangohud", "checkbox_mangohud", False),
        ("gamemode", "checkbox_gamemode", False),
        ("sdl-enabled", "checkbox_sdl", False),
        ("no-sleep-enabled", "checkbox_no_sleep", False),
        ("discrete-gpu", "checkbox_discrete_gpu", False),
        ("splash-window-enabled", "checkbox_splash_window", True),
        ("automatic-updates", "checkbox_automatic_updates", True),
        ("system-tray", "checkbox_system_tray", False),
        ("autostart-enabled", "checkbox_autostart", False),
        ("mono-icon", "checkbox_mono_icon", False),
        ("labels-enabled", "checkbox_labels", False),
        ("zoom-enabled", "checkbox_zoom", True),
        ("steamgriddb-enabled", "checkbox_steamgriddb", False),
        ("auto-create-shortcuts", "checkbox_auto_create_shortcuts", False),
        ("show-hidden", "checkbox_hidden_games", False),
        ("overview-enabled", "checkbox_overview", False),
        ("gamepad-navigation", "checkbox_gamepad_navigation", False),
        ("wayland-driver", "checkbox_wayland_driver", False),
        ("wow64-enabled", "checkbox_wow64", False),
        ("banner-enabled", "checkbox_banner", True),
        ("grid-max-children-enabled", "checkbox_grid_max_children", False),
        ("minimized-startup-enabled", "checkbox_minimized_startup", False),
        ("categories-enabled", "checkbox_categories", False),
        ("sort-enabled", "checkbox_sort", False),
        ("header-bar", "checkbox_header_bar", False),
    )

    def __init__(self, parent):
        super().__init__(title=_("Settings"), transient_for=parent)
        apply_titlebar_preference(self)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        self.parent = parent
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

        self.label_language = Gtk.Label(label=_("Language"))
        self.label_language.set_halign(Gtk.Align.START)
        self.combobox_language = IdComboBox()

        self.label_interface = Gtk.Label(label=_("Interface Mode"))
        self.label_interface.set_halign(Gtk.Align.START)
        self.combobox_interface = IdComboBox()
        self.combobox_interface.connect("changed", self.on_combobox_interface_changed)
        self.combobox_interface.append("List", _("List"))
        self.combobox_interface.append("Grid", _("Grid"))
        self.combobox_interface.append("Covers", _("Covers"))
        self.combobox_interface.append("Carrousel", _("Carrousel"))

        self.label_background = Gtk.Label(label=_("Background Color"))
        self.label_background.set_halign(Gtk.Align.START)
        self.combobox_background = IdComboBox()
        self.combobox_background.append("default", _("Default"))
        self.combobox_background.append("accent", _("Accent color"))
        self.combobox_background.append("dominant_color", _("Dominant color"))
        self.combobox_background.append("custom", _("Custom"))
        self.combobox_background.connect("changed", self.on_background_changed)
        self.background_color_button, self.box_background = self.create_color_picker(
            self.combobox_background, self.on_background_changed
        )

        self.label_overview_color = Gtk.Label(label=_("Overview Color"))
        self.label_overview_color.set_halign(Gtk.Align.START)
        self.combobox_overview_color = IdComboBox()
        self.combobox_overview_color.append("default", _("Default"))
        self.combobox_overview_color.append("accent", _("Accent color"))
        self.combobox_overview_color.append("dominant_color", _("Dominant color"))
        self.combobox_overview_color.append("custom", _("Custom"))
        self.combobox_overview_color.connect("changed", self.on_overview_color_changed)
        self.overview_color_button, self.box_overview_color = self.create_color_picker(
            self.combobox_overview_color, self.on_overview_color_changed
        )

        self.label_widget_color = Gtk.Label(label=_("Widget Color"))
        self.label_widget_color.set_halign(Gtk.Align.START)
        self.combobox_widget_color = IdComboBox()
        self.combobox_widget_color.append("default", _("Default"))
        self.combobox_widget_color.append("accent", _("Accent color"))
        self.combobox_widget_color.append("solid", _("Solid color"))

        self.checkbox_banner = Gtk.CheckButton(label=_("Banner"))

        self.label_theme_engine = Gtk.Label(label=_("Theme"))
        self.label_theme_engine.set_halign(Gtk.Align.START)
        self.combobox_theme_engine = IdComboBox()
        self.combobox_theme_engine.append("adwaita", "Adwaita ({})".format(_("Default")))
        self.combobox_theme_engine.append("system", _("System Theme"))
        for theme_name in list_gtk4_themes():
            self.combobox_theme_engine.append(theme_name, theme_name)
        self.combobox_theme_engine.connect("changed", self.on_theme_engine_changed)

        self.label_theme = Gtk.Label(label=_("Color Scheme"))
        self.label_theme.set_halign(Gtk.Align.START)
        self.combobox_theme = IdComboBox()
        self.combobox_theme.append("system", _("Default"))
        self.combobox_theme.append("light", _("Light"))
        self.combobox_theme.append("dark", _("Dark"))
        self._combobox_theme_handler = self.combobox_theme.connect("changed", self.on_theme_accent_changed)

        self.label_accent = Gtk.Label(label=_("Accent Color"))
        self.label_accent.set_halign(Gtk.Align.START)
        self.combobox_accent = IdComboBox()
        self.combobox_accent.append("system", _("Default"))
        self.combobox_accent.append("custom", _("Custom"))
        self._combobox_accent_handler = self.combobox_accent.connect("changed", self.on_theme_accent_changed)
        self.color_button, self.box_accent = self.create_color_picker(
            self.combobox_accent, self.on_theme_accent_changed
        )
        self.color_button.set_sensitive(False)

        self.label_startup_window_size = Gtk.Label(label=_("Startup Window Size"))
        self.label_startup_window_size.set_halign(Gtk.Align.START)

        self.combobox_startup_window_size = IdComboBox()
        self.combobox_startup_window_size.append("None", _("Default size"))
        self.combobox_startup_window_size.append("Remember", _("Remember size"))
        self.combobox_startup_window_size.append("Maximized", _("Maximized"))
        self.combobox_startup_window_size.append("Fullscreen", _("Fullscreen"))
        self.combobox_startup_window_size.set_tooltip_text(_("Alt+Enter toggles fullscreen"))

        self.checkbox_labels = Gtk.CheckButton(label=_("Labels"))

        self.checkbox_zoom = Gtk.CheckButton(label=_("Zoom"))
        self.checkbox_zoom.set_active(True)

        self.label_grid_position = Gtk.Label(label=_("Position"))
        self.label_grid_position.set_halign(Gtk.Align.START)
        self.combobox_grid_position = IdComboBox()
        self.combobox_grid_position.append("Top", _("Top"))
        self.combobox_grid_position.append("Middle", _("Middle"))
        self.combobox_grid_position.append("Bottom", _("Bottom"))

        self.label_grid_orientation = Gtk.Label(label=_("Orientation"))
        self.label_grid_orientation.set_halign(Gtk.Align.START)
        self.combobox_grid_orientation = IdComboBox()
        self.combobox_grid_orientation.append("Vertical", _("Vertical"))
        self.combobox_grid_orientation.append("Horizontal", _("Horizontal"))

        self.checkbox_grid_max_children = Gtk.CheckButton(label=_("Maximum Columns"))

        adjustment_grid_max_children = Gtk.Adjustment(
            value=getattr(self.parent, 'grid_max_children_per_line', 20),
            lower=1, upper=50, step_increment=1, page_increment=5, page_size=0
        )
        self.entry_grid_max_children = Gtk.SpinButton(adjustment=adjustment_grid_max_children, climb_rate=1, digits=0)
        self.entry_grid_max_children.set_hexpand(True)
        self.entry_grid_max_children.set_sensitive(False)

        def on_checkbox_grid_max_children_toggled(checkbox):
            self.entry_grid_max_children.set_sensitive(checkbox.get_active())

        self.checkbox_grid_max_children.connect("toggled", on_checkbox_grid_max_children_toggled)

        def on_grid_orientation_changed(combobox):
            if combobox.get_active_id() == "Horizontal":
                self.checkbox_grid_max_children.set_label(_("Maximum Rows"))
            else:
                self.checkbox_grid_max_children.set_label(_("Maximum Columns"))

        self.combobox_grid_orientation.connect("changed", on_grid_orientation_changed)

        self.checkbox_steamgriddb = Gtk.CheckButton(label=_("SteamGridDB"))
        self.checkbox_steamgriddb.connect("toggled", self.on_checkbox_steamgriddb_toggled)

        self.entry_steamgriddb_key = Gtk.Entry()
        self.entry_steamgriddb_key.set_placeholder_text(_("API Key"))

        self.button_steamgriddb_key = Gtk.Button()
        self.button_steamgriddb_key.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_steamgriddb_key.connect("clicked", self.on_button_steamgriddb_key_clicked)
        self.button_steamgriddb_key.set_size_request(50, -1)

        self.label_default_prefix = Gtk.Label(label=_("Default Prefixes Location"))
        self.label_default_prefix.set_halign(Gtk.Align.START)

        self.entry_default_prefix = Gtk.Entry()
        self.entry_default_prefix.set_tooltip_text(_("The location where prefixes are created"))
        self.entry_default_prefix.connect("query-tooltip", on_entry_query_tooltip)
        self.entry_default_prefix.connect("changed", on_entry_changed)

        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

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

        self.label_display = Gtk.Label(label=_("Display"))
        self.label_display.set_halign(Gtk.Align.START)

        self.checkbox_discrete_gpu = Gtk.CheckButton(label=_("Discrete GPU"))

        self.checkbox_auto_close_on_launch = Gtk.CheckButton(label=_("Auto-close on launch"))

        self.checkbox_autostart = Gtk.CheckButton(label=_("Autostart"))

        self.checkbox_system_tray = Gtk.CheckButton(label=_("System tray icon"))
        self.checkbox_system_tray.connect("toggled", self.on_checkbox_system_tray_toggled)

        self.checkbox_minimized_startup = Gtk.CheckButton(label=_("Minimized startup"))
        self.checkbox_minimized_startup.set_sensitive(False)

        self.checkbox_mono_icon = Gtk.CheckButton(label=_("Monochrome icon"))
        self.checkbox_mono_icon.set_sensitive(False)

        self.checkbox_splash_window = Gtk.CheckButton(label=_("Splash window"))
        self.checkbox_splash_window.set_active(True)

        self.checkbox_automatic_updates = Gtk.CheckButton(label=_("Automatic updates"))
        self.checkbox_automatic_updates.set_active(True)

        self.checkbox_auto_create_shortcuts = Gtk.CheckButton(label=_("Auto-create shortcuts"))
        self.checkbox_auto_create_shortcuts.set_tooltip_text(
            _("Automatically creates shortcuts when installing something through the file manager")
        )

        self.checkbox_categories = Gtk.CheckButton(label=_("Categories"))

        self.checkbox_sort = Gtk.CheckButton(label=_("Sort"))

        self.checkbox_header_bar = Gtk.CheckButton(label=_("Header bar"))

        self.checkbox_hidden_games = Gtk.CheckButton(label=_("Hidden games"))
        self.checkbox_hidden_games.set_tooltip_text(_("Ctrl+H toggles hidden games"))

        self.checkbox_overview = Gtk.CheckButton(label=_("Overview"))
        self.checkbox_overview.connect("toggled", self.on_checkbox_overview_toggled)

        self.checkbox_gamepad_navigation = Gtk.CheckButton(label=_("Gamepad navigation"))

        self.checkbox_wayland_driver = Gtk.CheckButton(label=_("Wayland driver (experimental)"))

        self.checkbox_wow64 = Gtk.CheckButton(label=_("WOW64 (experimental)"))

        self.button_winetricks_default = Gtk.Button(label="Winetricks")
        self.button_winetricks_default.connect("clicked", self.on_button_winetricks_default_clicked)
        self.button_winetricks_default.set_size_request(120, -1)

        self.button_winecfg_default = Gtk.Button(label="Winecfg")
        self.button_winecfg_default.connect("clicked", self.on_button_winecfg_default_clicked)
        self.button_winecfg_default.set_size_request(120, -1)

        self.button_run_default = Gtk.Button(label=_("Run"))
        self.button_run_default.set_size_request(120, -1)
        self.button_run_default.connect("clicked", self.on_button_run_default_clicked)
        self.button_run_default.set_tooltip_text(_("Run a file in the prefix"))

        create_mangohud_gamemode_checkboxes(self)
        self.checkbox_sdl = Gtk.CheckButton(label="SDL")
        self.checkbox_sdl.set_tooltip_text(_("May fix gamepad issues with some games"))
        self.checkbox_no_sleep = Gtk.CheckButton(label=_("No Sleep"))
        self.checkbox_no_sleep.set_tooltip_text(_("Prevents the system from suspending while gaming"))

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
        self.button_ok.set_focus_on_click(False)

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

        self.liststore = Gtk.ListStore(str)
        self.liststore.append([""])

        treeview = Gtk.TreeView(model=self.liststore)
        treeview.add_css_class("envar-list")
        treeview.set_has_tooltip(True)
        treeview.connect("query-tooltip", on_treeview_query_tooltip, self.liststore)
        envar_key_controller = Gtk.EventControllerKey()
        envar_key_controller.connect("key-pressed", self.on_envar_key_press)
        treeview.add_controller(envar_key_controller)

        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.set_property("ellipsize", 3)
        renderer.connect("edited", self.on_cell_edited, 0)
        self.commit_pending_envar_edit = track_cell_editing(renderer)

        column = Gtk.TreeViewColumn("", renderer, text=0)
        treeview.set_headers_visible(False)

        treeview.append_column(column)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(130)
        scrolled_window.set_vexpand(True)
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

        frame = Gtk.Frame()

        frame.set_margin_top(10)
        frame.set_margin_start(10)
        frame.set_margin_end(10)

        label_version = Gtk.Label()
        label_version.set_markup(
            '<a href="https://github.com/Faugus/faugus-launcher/releases/tag/{0}">Faugus {0}</a>'.format(VERSION)
        )
        label_version.set_use_markup(True)
        label_version.set_halign(Gtk.Align.START)

        grid_page_general = Gtk.Grid()
        grid_page_general.set_column_homogeneous(True)
        grid_page_general.set_column_spacing(10)
        grid_page_interface = Gtk.Grid()
        grid_page_interface.set_column_homogeneous(True)
        grid_page_interface.set_column_spacing(10)

        box_general_col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_general_col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_general_col3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        box_interface_col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_interface_col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_interface_col3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        box_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_buttons.set_valign(Gtk.Align.CENTER)

        grid_language = build_grid()

        grid_prefix = build_grid()

        grid_runner = build_grid()

        grid_tools = build_grid()

        grid_logs = build_grid()

        grid_version = build_grid()
        grid_version.set_vexpand(True)
        grid_version.set_valign(Gtk.Align.END)

        grid_miscellaneous = build_grid()

        grid_envar = build_grid()

        grid_interface_mode = build_grid()

        grid_steamgriddb = build_grid(margin_top=False)

        grid_theme_colors = build_grid()

        grid_interface_checkboxes = build_grid()

        grid_support = build_grid(column_homogeneous=True)
        grid_support.set_vexpand(True)
        grid_support.set_valign(Gtk.Align.END)

        grid_backup = build_grid(column_homogeneous=True)
        grid_backup.set_vexpand(True)
        grid_backup.set_valign(Gtk.Align.END)

        self.grid_big_interface = build_grid(margin_top=False)

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

        self.combobox_runner.set_hexpand(True)
        self.button_proton_manager.set_hexpand(True)

        box_buttons.append(self.button_winetricks_default)
        box_buttons.append(self.button_winecfg_default)
        box_buttons.append(self.button_run_default)

        grid_tools.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        grid_tools.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        grid_tools.attach(self.checkbox_no_sleep, 0, 2, 1, 1)
        grid_tools.attach(self.checkbox_sdl, 0, 3, 1, 1)
        grid_tools.attach(box_buttons, 2, 0, 1, 4)

        grid_logs.attach(self.button_clearlogs, 0, 0, 1, 1)
        self.button_clearlogs.set_hexpand(True)

        grid_version.attach(label_version, 0, 0, 1, 1)

        grid_miscellaneous.attach(self.label_miscellaneous, 0, 0, 1, 1)
        grid_miscellaneous.attach(self.checkbox_discrete_gpu, 0, 1, 1, 1)
        grid_miscellaneous.attach(self.checkbox_splash_window, 0, 2, 1, 1)
        grid_miscellaneous.attach(self.checkbox_automatic_updates, 0, 3, 1, 1)
        grid_miscellaneous.attach(self.checkbox_auto_close_on_launch, 0, 4, 1, 1)
        grid_miscellaneous.attach(self.checkbox_gamepad_navigation, 0, 5, 1, 1)
        grid_miscellaneous.attach(self.checkbox_autostart, 0, 6, 1, 1)
        grid_miscellaneous.attach(self.checkbox_system_tray, 0, 7, 1, 1)
        grid_miscellaneous.attach(self.checkbox_minimized_startup, 0, 8, 1, 1)
        grid_miscellaneous.attach(self.checkbox_mono_icon, 0, 9, 1, 1)
        grid_miscellaneous.attach(self.checkbox_auto_create_shortcuts, 0, 10, 1, 1)
        grid_miscellaneous.attach(self.checkbox_wayland_driver, 0, 11, 1, 1)
        grid_miscellaneous.attach(self.checkbox_wow64, 0, 12, 1, 1)

        grid_interface_mode.attach(self.label_interface, 0, 0, 1, 1)
        grid_interface_mode.attach(self.combobox_interface, 0, 1, 1, 1)
        self.combobox_interface.set_hexpand(True)

        grid_theme_colors.attach(self.label_theme_engine, 0, 0, 2, 1)
        grid_theme_colors.attach(self.combobox_theme_engine, 0, 1, 2, 1)
        self.combobox_theme_engine.set_hexpand(True)

        grid_theme_colors.attach(self.label_theme, 0, 2, 2, 1)
        grid_theme_colors.attach(self.combobox_theme, 0, 3, 2, 1)
        self.combobox_theme.set_hexpand(True)
        grid_theme_colors.attach(self.label_accent, 0, 4, 2, 1)
        grid_theme_colors.attach(self.box_accent, 0, 5, 2, 1)
        self.combobox_accent.set_hexpand(True)

        grid_theme_colors.attach(self.label_widget_color, 0, 6, 2, 1)
        grid_theme_colors.attach(self.combobox_widget_color, 0, 7, 2, 1)
        self.combobox_widget_color.set_hexpand(True)

        grid_theme_colors.attach(self.label_background, 0, 8, 2, 1)
        grid_theme_colors.attach(self.box_background, 0, 9, 2, 1)
        self.combobox_background.set_hexpand(True)

        grid_theme_colors.attach(self.label_overview_color, 0, 10, 2, 1)
        grid_theme_colors.attach(self.box_overview_color, 0, 11, 2, 1)
        self.combobox_overview_color.set_hexpand(True)

        grid_interface_checkboxes.attach(self.label_display, 0, 0, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_labels, 0, 1, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_zoom, 0, 2, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_sort, 0, 3, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_categories, 0, 4, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_banner, 0, 5, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_overview, 0, 6, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_header_bar, 0, 7, 1, 1)
        grid_interface_checkboxes.attach(self.checkbox_hidden_games, 0, 8, 1, 1)

        grid_envar.attach(self.label_envar, 0, 0, 1, 1)
        grid_envar.attach(scrolled_window, 0, 1, 1, 1)
        scrolled_window.set_hexpand(True)

        grid_backup.attach(self.label_settings, 0, 0, 2, 1)
        grid_backup.attach(button_backup, 0, 1, 1, 1)
        grid_backup.attach(button_restore, 1, 1, 1, 1)

        grid_steamgriddb.attach(self.checkbox_steamgriddb, 0, 0, 2, 1)
        grid_steamgriddb.attach(self.entry_steamgriddb_key, 0, 1, 1, 1)
        grid_steamgriddb.attach(self.button_steamgriddb_key, 1, 1, 1, 1)
        self.entry_steamgriddb_key.set_hexpand(True)

        self.grid_big_interface.attach(self.label_startup_window_size, 0, 0, 2, 1)
        self.grid_big_interface.attach(self.combobox_startup_window_size, 0, 1, 2, 1)
        self.combobox_startup_window_size.set_hexpand(True)
        self.grid_big_interface.attach(self.label_grid_position, 0, 2, 2, 1)
        self.grid_big_interface.attach(self.combobox_grid_position, 0, 3, 2, 1)
        self.combobox_grid_position.set_hexpand(True)
        self.grid_big_interface.attach(self.label_grid_orientation, 0, 4, 2, 1)
        self.grid_big_interface.attach(self.combobox_grid_orientation, 0, 5, 2, 1)
        self.combobox_grid_orientation.set_hexpand(True)
        self.grid_big_interface.attach(self.checkbox_grid_max_children, 0, 6, 2, 1)
        self.grid_big_interface.attach(self.entry_grid_max_children, 0, 7, 2, 1)

        grid_support.attach(self.label_support, 0, 0, 2, 1)
        grid_support.attach(button_kofi, 0, 1, 1, 1)
        grid_support.attach(button_paypal, 1, 1, 1, 1)

        box_general_col1.append(grid_prefix)
        box_general_col1.append(grid_runner)
        box_general_col1.append(self.label_default_prefix_tools)
        box_general_col1.append(grid_tools)
        box_general_col1.append(grid_version)

        box_general_col2.append(grid_miscellaneous)

        box_general_col3.append(grid_envar)
        box_general_col3.append(grid_logs)

        grid_page_general.attach(box_general_col1, 0, 0, 1, 1)
        grid_page_general.attach(box_general_col2, 1, 0, 1, 1)
        grid_page_general.attach(box_general_col3, 2, 0, 1, 1)
        box_general_col1.set_hexpand(True)
        box_general_col3.set_hexpand(True)

        box_interface_col1.append(grid_interface_mode)
        box_interface_col1.append(self.grid_big_interface)
        box_interface_col1.append(grid_steamgriddb)

        box_interface_col2.append(grid_theme_colors)

        box_interface_col3.append(grid_interface_checkboxes)

        grid_page_interface.attach(box_interface_col1, 0, 0, 1, 1)
        grid_page_interface.attach(box_interface_col2, 1, 0, 1, 1)
        grid_page_interface.attach(box_interface_col3, 2, 0, 1, 1)
        box_interface_col1.set_hexpand(True)
        box_interface_col3.set_hexpand(True)

        self.view_stack = Gtk.Stack()

        settings_tab_switcher = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        settings_tab_switcher.add_css_class("linked")
        settings_tab_switcher.set_homogeneous(True)
        settings_tab_switcher.set_hexpand(True)
        settings_tab_switcher.set_margin_top(10)
        settings_tab_switcher.set_margin_start(10)
        settings_tab_switcher.set_margin_end(10)

        settings_tab_pages = [
            ("general", _("General"), grid_page_general),
            ("interface", _("Interface"), grid_page_interface),
        ]
        first_settings_tab_button = None
        self.tab_button_widgets = []
        for name, label, page in settings_tab_pages:
            self.view_stack.add_titled(page, name, label)
            button = Gtk.ToggleButton(label=label)
            button.set_focusable(False)
            if first_settings_tab_button is None:
                first_settings_tab_button = button
                button.set_active(True)
            else:
                button.set_group(first_settings_tab_button)
            button.connect(
                "toggled",
                lambda btn, n=name: self.view_stack.set_visible_child_name(n) if btn.get_active() else None,
            )
            settings_tab_switcher.append(button)
            self.tab_button_widgets.append(button)
        self.tab_names = [name for name, _label, _page in settings_tab_pages]

        box_settings_tabs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_settings_tabs.append(settings_tab_switcher)
        box_settings_tabs.append(self.view_stack)

        grid_outside_tabs = Gtk.Grid()
        grid_outside_tabs.set_column_homogeneous(True)
        grid_outside_tabs.set_column_spacing(10)
        grid_outside_tabs.set_margin_top(10)

        box_outside_col1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_outside_col2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_outside_col3 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        box_outside_col1.append(grid_language)
        box_outside_col2.append(grid_support)
        box_outside_col3.append(grid_backup)

        grid_outside_tabs.attach(box_outside_col1, 0, 0, 1, 1)
        grid_outside_tabs.attach(box_outside_col2, 1, 0, 1, 1)
        grid_outside_tabs.attach(box_outside_col3, 2, 0, 1, 1)
        box_outside_col1.set_hexpand(True)
        box_outside_col3.set_hexpand(True)

        box_settings_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_settings_root.append(box_settings_tabs)
        box_settings_root.append(grid_outside_tabs)

        frame.set_child(box_settings_root)

        box_bottom = build_bottom_button_box(self.button_cancel, self.button_ok)
        box_bottom.set_margin_top(10)

        frame_scroll = Gtk.ScrolledWindow()
        frame_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        frame_scroll.set_propagate_natural_height(True)
        frame_scroll.set_vexpand(True)
        frame_scroll.set_child(frame)

        self.box.append(frame_scroll)
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
        if os.path.exists(LOGS_DIR):
            size = self.get_dir_size(LOGS_DIR)
            self.button_clearlogs.set_label(_("Clear Logs (%s)") % size)
            self.button_clearlogs.set_sensitive(True)
        else:
            self.button_clearlogs.set_label(_("Clear Logs"))
            self.button_clearlogs.set_sensitive(False)

    def on_clear_logs_clicked(self, button):
        if os.path.exists(LOGS_DIR):
            shutil.rmtree(LOGS_DIR)
        self.update_button_label()

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
            completions = get_translation_completions(LOCALE_DIR, "faugus-launcher")
            for lang, completion in completions.items():
                if lang == "en_US" or completion < MIN_TRANSLATION_PERCENT:
                    continue
                lang_name = self.LANG_NAMES.get(lang, lang)
                available_langs.append((lang_name, lang))

        available_langs.sort(key=lambda x: x[0])

        for lang_name, lang_code in available_langs:
            self.combobox_language.append(lang_code, lang_name)

        self.combobox_language.set_active(0)

    def on_combobox_interface_changed(self, combobox):
        active_id = combobox.get_active_id()

        covers_or_carrousel = active_id in ("Covers", "Carrousel")
        not_list = active_id != "List"

        covers_carrousel_tip = _("Covers or Carrousel mode")

        for checkbox in (self.checkbox_labels, self.checkbox_zoom):
            checkbox.set_sensitive(covers_or_carrousel)
            checkbox.set_tooltip_text(None if covers_or_carrousel else covers_carrousel_tip)

        self._refresh_banner_checkbox_sensitivity()

        covers_carrousel_or_grid = active_id in ("Covers", "Carrousel", "Grid")
        covers_carrousel_grid_tip = _("Grid, Covers or Carrousel mode")
        self.label_grid_position.set_sensitive(covers_carrousel_or_grid)
        self.combobox_grid_position.set_sensitive(covers_carrousel_or_grid)
        self.combobox_grid_position.set_tooltip_text(None if covers_carrousel_or_grid else covers_carrousel_grid_tip)

        self.checkbox_overview.set_sensitive(covers_carrousel_or_grid)
        self.checkbox_overview.set_tooltip_text(None if covers_carrousel_or_grid else covers_carrousel_grid_tip)

        grid_or_covers = active_id in ("Grid", "Covers")
        grid_covers_tip = _("Grid or Covers mode")
        self.label_grid_orientation.set_sensitive(grid_or_covers)
        self.combobox_grid_orientation.set_sensitive(grid_or_covers)
        self.combobox_grid_orientation.set_tooltip_text(None if grid_or_covers else grid_covers_tip)

        self.checkbox_grid_max_children.set_sensitive(grid_or_covers)
        self.entry_grid_max_children.set_sensitive(grid_or_covers and self.checkbox_grid_max_children.get_active())
        self.checkbox_grid_max_children.set_tooltip_text(None if grid_or_covers else grid_covers_tip)

        self.label_startup_window_size.set_sensitive(not_list)
        self.combobox_startup_window_size.set_sensitive(not_list)
        self.combobox_startup_window_size.set_tooltip_text(
            _("Alt+Enter toggles fullscreen") if not_list else covers_carrousel_grid_tip
        )

    def on_checkbox_steamgriddb_toggled(self, checkbox):
        self.entry_steamgriddb_key.set_sensitive(checkbox.get_active())
        self._refresh_banner_checkbox_sensitivity()

    def on_button_steamgriddb_key_clicked(self, widget):
        import webbrowser
        webbrowser.open("https://www.steamgriddb.com/profile/preferences/api")

    def _refresh_banner_checkbox_sensitivity(self):
        covers_or_carrousel = self.combobox_interface.get_active_id() in ("Covers", "Carrousel")
        enabled = covers_or_carrousel and self.checkbox_steamgriddb.get_active()
        self.checkbox_banner.set_sensitive(enabled)
        self.checkbox_banner.set_tooltip_text(
            None if enabled else _("Covers or Carrousel mode with SteamGridDB")
        )

    def create_color_picker(self, combobox, on_changed):
        button = Gtk.ColorButton()
        button.connect("color-set", on_changed)
        button.get_first_child().connect_after("clicked", self.on_color_button_clicked)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.append(combobox)
        box.append(button)
        return button, box

    def set_button_color(self, button, color):
        rgba = Gdk.RGBA()
        rgba.parse(color)
        button.set_rgba(rgba)

    def on_color_button_clicked(self, button):
        for window in Gtk.Window.get_toplevels():
            if isinstance(window, Gtk.ColorChooserDialog):
                window.get_content_area().get_first_child().set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)

    def on_theme_accent_changed(self, widget):
        self.color_button.set_sensitive(self.combobox_accent.get_active_id() == "custom")

        self.interface_theme = self.combobox_theme.get_active_id() or "system"
        if self.combobox_accent.get_active_id() == "custom":
            self.accent_color = self.color_button.get_rgba().to_string()
        else:
            self.accent_color = "system"

        apply_interface_customization(self.interface_theme, self.accent_color, self.theme_engine)

        self.parent.interface_theme = self.interface_theme
        self.parent.accent_color = self.accent_color

        self.parent.update_placeholder_accent_css()
        self.parent.update_widget_color_css()
        self.parent.refresh_placeholder_covers()
        self.parent.apply_overview_panel_width()
        if self.parent.background_mode in ("accent", "custom"):
            self.parent.update_accent_background_css()
        self.parent.apply_background_update_now()

    def on_background_changed(self, widget):
        new_mode = self.combobox_background.get_active_id()
        self.background_color_button.set_sensitive(new_mode == "custom")
        self.parent.background_color = self.background_color_button.get_rgba().to_string()
        self.parent.apply_background_mode_live(new_mode)

    def on_overview_color_changed(self, widget):
        self.parent.overview_color_mode = self.combobox_overview_color.get_active_id()
        self.overview_color_button.set_sensitive(self.parent.overview_color_mode == "custom")
        self.parent.overview_color = self.overview_color_button.get_rgba().to_string()
        self.parent.apply_overview_panel_width()

    def on_checkbox_overview_toggled(self, widget):
        enabled = widget.get_active()
        self.label_overview_color.set_sensitive(enabled)
        self.box_overview_color.set_sensitive(enabled)

    def on_theme_engine_changed(self, widget):
        self.theme_engine = self.combobox_theme_engine.get_active_id()
        is_adwaita = self.theme_engine == "adwaita"
        adwaita_tip = None if is_adwaita else _("Adwaita theme")
        self.label_theme.set_sensitive(is_adwaita)
        self.combobox_theme.set_sensitive(is_adwaita)
        self.combobox_theme.set_tooltip_text(adwaita_tip)
        self.label_accent.set_sensitive(is_adwaita)
        self.box_accent.set_sensitive(is_adwaita)
        self.box_accent.set_tooltip_text(adwaita_tip)
        if not is_adwaita:
            self.combobox_theme.set_active_id("system")
            self.combobox_accent.set_active_id("system")

    def on_checkbox_system_tray_toggled(self, widget):
        active = widget.get_active()
        self.checkbox_minimized_startup.set_sensitive(active)
        self.checkbox_mono_icon.set_sensitive(active)

    def populate_combobox_with_runners(self):
        populate_combobox_with_runners(self.combobox_runner)

    def update_config_file(self):
        config = ConfigManager()
        for key, attr, _default in self.CHECKBOX_SETTINGS:
            config.set_value(key, getattr(self, attr).get_active())
        config.set_value("language", self.combobox_language.get_active_id())
        config.set_value("default-prefix", self.entry_default_prefix.get_text())
        config.set_value("default-runner", self.get_default_runner())
        config.set_value("interface-mode", self.combobox_interface.get_active_id())
        config.set_value("background-mode", self.combobox_background.get_active_id())
        config.set_value("overview-color-mode", self.combobox_overview_color.get_active_id())
        config.set_value("widget-color-mode", self.combobox_widget_color.get_active_id())
        config.set_value("background-color", self.background_color_button.get_rgba().to_string())
        config.set_value("overview-color", self.overview_color_button.get_rgba().to_string())
        config.set_value("grid-position", self.combobox_grid_position.get_active_id())
        config.set_value("grid-orientation", self.combobox_grid_orientation.get_active_id())
        config.set_value("grid-max-children-per-line", int(self.entry_grid_max_children.get_value()))
        config.set_value("steamgriddb-api-key", self.entry_steamgriddb_key.get_text().strip())
        config.set_value("startup-window-size", self.combobox_startup_window_size.get_active_id())
        config.set_value("interface-theme", self.interface_theme)
        config.set_value("accent-mode", self.combobox_accent.get_active_id())
        config.set_value("accent-color", self.color_button.get_rgba().to_string())
        config.set_value("theme-engine", self.combobox_theme_engine.get_active_id())
        config.save_config()

        self.set_sensitive(False)

    def get_default_runner(self):
        return self.combobox_runner.get_active_id()

    def update_envar_file(self):
        values = [row[0] for row in self.liststore if row[0].strip() != ""]
        save_json_file(values, ENVAR_DIR)

    def on_button_proton_manager_clicked(self, widget):
        current_runner = self.combobox_runner.get_active_id()

        from faugus.proton_manager import ProtonDownloader
        dialog = ProtonDownloader()
        dialog.set_transient_for(self)

        def on_response(dialog, response_id):
            dialog.closed_event.set()
            destroy_and_release(dialog)

            self.combobox_runner.remove_all()
            self.populate_combobox_with_runners()

            if current_runner:
                self.combobox_runner.set_active_id(current_runner)

        dialog.connect("response", on_response)
        dialog.present()

    def track_modifications(self, container):
        for child in widget_children(container):
            if isinstance(child, (Gtk.Entry, IdComboBox)):
                child.connect("changed", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.CheckButton):
                child.connect("toggled", lambda w: setattr(self, "modified", True))
            elif isinstance(child, Gtk.TreeView):
                selection = child.get_selection()
                selection.connect("changed", lambda sel: setattr(self, "modified", True))
            else:
                self.track_modifications(child)

    def check_modified(self, callback=None):
        if not self.modified:
            if callback:
                callback()
            return

        def on_proceed(proceed):
            if proceed:
                if self.entry_default_prefix.get_text() == "":
                    self.entry_default_prefix.add_css_class("entry")
                    return
                apply_interface_customization(self.interface_theme, self.accent_color, self.combobox_theme_engine.get_active_id())
                self.update_envar_file()
                self.update_config_file()
                self.parent.manage_autostart_file(self.checkbox_autostart.get_active(), self.checkbox_minimized_startup.get_active())
                if self.parent.apply_tray_settings(self.checkbox_system_tray.get_active(), self.checkbox_mono_icon.get_active()):
                    return
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

            command_parts.append("GAMEID=winetricks-gui")
            command_parts.append("STORE=none")
            if default_runner:
                command_parts.append(f"PROTONPATH='{resolve_protonpath(default_runner)}'")

            command_parts.append(f"'{UMU_RUN}'")
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
                command_parts.append(f"PROTONPATH='{resolve_protonpath(default_runner)}'")

            command_parts.append(f"'{UMU_RUN}'")
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
                _("Select a file to run in the prefix"),
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

                    if default_runner:
                        command_parts.append(f"PROTONPATH='{resolve_protonpath(default_runner)}'")
                    if escaped_file_run.endswith(".reg"):
                        command_parts.append(f"'{UMU_RUN}' regedit '{escaped_file_run}'")
                    else:
                        command_parts.append(f"'{UMU_RUN}' '{escaped_file_run}'")

                    command = ' '.join(command_parts)
                    cmd = (sys.executable, "-m", "faugus.runner", command)

                    def run_command():
                        process = subprocess.Popen(cmd, cwd=cwd, env=subprocess_env())
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

            backup_win = BackupWindow(self)
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
        zip_filter.set_name(_("Faugus Backup files"))
        zip_filter.add_pattern("*.tar")
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

            from faugus.backup import RestoreWindow, restore_legacy_flat

            restore_dialog = RestoreWindow(self)

            def on_restore_response(dialog, response_id):
                if response_id == Gtk.ResponseType.OK:
                    global faugus_backup
                    faugus_backup = True
                    self.response(Gtk.ResponseType.OK)
                destroy_and_release(dialog)

            restore_dialog.connect("response", on_restore_response)
            restore_dialog.present()

            temp_dir = os.path.join(FAUGUS_TEMP, "temp-restore")

            def extract_worker():
                error = None
                try:
                    if zip_file.lower().endswith(".zip"):
                        shutil.unpack_archive(zip_file, temp_dir)
                    else:
                        shutil.unpack_archive(zip_file, temp_dir, filter="fully_trusted")
                except Exception as e:
                    error = e
                GLib.idle_add(on_extracted, error)

            def on_extracted(error):
                if restore_dialog.is_closed:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return False

                if error is not None or not os.path.exists(os.path.join(temp_dir, ".faugus_marker")):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    restore_dialog.discard()
                    self.show_warning_dialog_settings(
                        self, _("This is not a valid Faugus backup file."), False, lambda ok: None)
                    return False

                manifest_path = os.path.join(temp_dir, "manifest.json")

                if os.path.isfile(manifest_path):
                    manifest = load_json_file(manifest_path, default={})
                    restore_dialog.load_content(temp_dir, manifest)
                    return False

                restore_dialog.discard()

                def on_confirm(ok):
                    if not ok:
                        shutil.rmtree(temp_dir)
                        return

                    restore_legacy_flat(temp_dir)
                    shutil.rmtree(temp_dir)
                    global faugus_backup
                    faugus_backup = True
                    self.response(Gtk.ResponseType.OK)

                self.show_warning_dialog_settings(
                    self, _("Are you sure you want to overwrite the settings?"), True, on_confirm)
                return False

            run_in_background(extract_worker)

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
        preferred_path = expand_path(entry_value) if entry_value else None
        set_file_chooser_start_folder(filechooser, "settings_default_prefix", preferred_path)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                folder = dialog_fc.get_file().get_path()
                if folder:
                    self.entry_default_prefix.set_text(folder)
            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def load_config(self):
        cfg = ConfigManager()

        default_prefix = cfg.config.get('default-prefix', '').strip('"')
        default_runner = cfg.config.get('default-runner', '').strip('"')
        interface_mode = cfg.config.get('interface-mode', '').strip('"')
        background_mode = cfg.config.get('background-mode', 'default').strip('"')
        overview_color_mode = cfg.config.get('overview-color-mode', 'default').strip('"')
        widget_color_mode = cfg.config.get('widget-color-mode', 'default').strip('"')
        background_color = cfg.config.get('background-color', 'rgb(61,174,233)').strip('"')
        overview_color = cfg.config.get('overview-color', 'rgb(61,174,233)').strip('"')
        steamgriddb_api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
        language = cfg.config.get('language', '')
        startup_window_size = cfg.config.get('startup-window-size', '')
        grid_position = cfg.config.get('grid-position', 'Middle').strip('"')
        grid_orientation = cfg.config.get('grid-orientation', 'Vertical').strip('"')
        grid_max_children_per_line = int(cfg.config.get('grid-max-children-per-line', 20))
        self.interface_theme = cfg.config.get('interface-theme', 'system')
        self.accent_color = cfg.get_accent_color()
        accent_color = cfg.config.get('accent-color', 'rgb(61,174,233)')
        self.theme_engine = cfg.config.get('theme-engine', 'adwaita').strip('"')
        self.original_interface_theme = self.interface_theme
        self.original_accent_color = self.accent_color
        self.original_background_mode = background_mode
        self.original_overview_color_mode = overview_color_mode
        self.original_background_color = background_color
        self.original_overview_color = overview_color
        self.original_theme_engine = self.theme_engine

        self.entry_default_prefix.set_text(default_prefix)

        if not self.combobox_runner.set_active_id(default_runner):
            self.combobox_runner.set_active(0)
        self.entry_steamgriddb_key.set_text(steamgriddb_api_key)
        self.combobox_interface.set_active_id(interface_mode)
        self.set_button_color(self.background_color_button, background_color)
        self.set_button_color(self.overview_color_button, overview_color)
        self.combobox_background.set_active_id(background_mode)
        self.combobox_overview_color.set_active_id(overview_color_mode)
        self.combobox_widget_color.set_active_id(widget_color_mode)
        self.combobox_grid_position.set_active_id(grid_position)
        self.combobox_grid_orientation.set_active_id(grid_orientation)
        self.entry_grid_max_children.set_value(grid_max_children_per_line)

        self.combobox_theme.handler_block(self._combobox_theme_handler)
        self.combobox_accent.handler_block(self._combobox_accent_handler)

        if not self.combobox_theme_engine.set_active_id(self.theme_engine):
            self.combobox_theme_engine.set_active_id("adwaita")
        self.on_theme_engine_changed(self.combobox_theme_engine)

        is_custom_accent = self.accent_color != "system"
        self.set_button_color(self.color_button, accent_color)
        self.color_button.set_sensitive(is_custom_accent)

        self.combobox_theme.set_active_id(self.interface_theme)
        self.combobox_accent.set_active_id("custom" if is_custom_accent else "system")

        self.combobox_theme.handler_unblock(self._combobox_theme_handler)
        self.combobox_accent.handler_unblock(self._combobox_accent_handler)

        for key, attr, default in self.CHECKBOX_SETTINGS:
            getattr(self, attr).set_active(cfg.config.get(key, str(default)) == 'True')
        self.on_checkbox_steamgriddb_toggled(self.checkbox_steamgriddb)
        self.on_checkbox_overview_toggled(self.checkbox_overview)
        self.combobox_startup_window_size.set_active_id(startup_window_size)

        index_language = 0
        for i, lang_code in enumerate(self.combobox_language.get_ids()):
            if lang_code == "en_US":
                index_language = i
                break

        if language != "":
            language_primary = language.split("_")[0].split("-")[0].lower()
            for i, lang_code in enumerate(self.combobox_language.get_ids()):
                if lang_code == language or (lang_code or "").lower() == language_primary:
                    index_language = i
                    break

        self.combobox_language.set_active(index_language)
        self.load_liststore_from_file(ENVAR_DIR)

    def load_liststore_from_file(self, filename=ENVAR_DIR):
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
        sdl_enabled,
        protonfix,
        runner,
        addapp_enabled,
        addapp,
        addapp_bat,
        addapp_delay,
        addapp_first,
        cover,
        lossless_enabled,
        lossless_multiplier,
        lossless_flow,
        lossless_performance,
        lossless_hdr,
        lossless_present,
        playtime,
        hidden,
        no_sleep,
        category,
        icon,
        steamgriddb_id="",
        pre_launch="",
        post_launch="",
        steam_user="",
        disable_umu="",
        runtime="",
        last_played="",
    ):
        self.gameid = gameid
        self.title = title
        self.path = path
        self.launch_arguments = launch_arguments
        self.game_arguments = game_arguments
        self.mangohud = mangohud
        self.gamemode = gamemode
        self.prefix = prefix
        self.sdl_enabled = sdl_enabled
        self.protonfix = protonfix
        self.runner = runner
        self.addapp_enabled = addapp_enabled
        self.addapp = addapp
        self.addapp_bat = addapp_bat
        self.addapp_delay = addapp_delay
        self.addapp_first = addapp_first
        self.cover = cover
        self.lossless_enabled = lossless_enabled
        self.lossless_multiplier = lossless_multiplier
        self.lossless_flow = lossless_flow
        self.lossless_performance = lossless_performance
        self.lossless_hdr = lossless_hdr
        self.lossless_present = lossless_present
        self.playtime = playtime
        self.hidden = hidden
        self.no_sleep = no_sleep
        self.category = category
        self.icon = icon
        self.runtime = runtime
        self.steamgriddb_id = steamgriddb_id
        self.pre_launch = pre_launch
        self.post_launch = post_launch
        self.steam_user = steam_user
        self.disable_umu = disable_umu
        self.last_played = last_played


class DuplicateDialog(Gtk.Dialog):
    def __init__(self, parent, title):
        super().__init__(title=_("Duplicate %s") % title, transient_for=parent)
        apply_titlebar_preference(self)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        label_title = Gtk.Label(label=_("Title"))
        label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.set_has_tooltip(True)
        self.entry_title.set_hexpand(True)
        self.entry_title.connect("query-tooltip", on_entry_query_tooltip)

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        button_cancel.set_hexpand(True)

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        button_ok.set_hexpand(True)

        content_area = self.get_content_area()
        content_area.set_halign(Gtk.Align.FILL)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_hexpand(True)
        box_top.set_margin_start(10)
        box_top.set_margin_end(10)
        box_top.set_margin_top(10)
        box_top.set_margin_bottom(20)

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_homogeneous(True)
        box_bottom.set_hexpand(True)
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
        apply_titlebar_preference(self)
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

        self.checkbox_remove_prefix = Gtk.CheckButton(label=_("Also remove the prefix:"))
        self.checkbox_remove_prefix.set_halign(Gtk.Align.CENTER)

        content_area = self.get_content_area()
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        box_top.append(label)
        if os.path.basename(prefix) != "default" and runner != "Linux-Native" and runner != "Steam":
            box_top.append(self.checkbox_remove_prefix)
            box_top.append(prefix_label)
            if pfx_count > 0:
                box_top.append(warn_label)

        frame.set_child(box_top)

        content_area.append(frame)
        content_area.append(build_bottom_button_box(button_no, button_yes))

        self.present()


class AddGame(Gtk.Dialog, HiDpiMixin):
    def __init__(self, parent, interface_mode):
        super().__init__(title=_("New Game/App"), transient_for=parent)
        apply_titlebar_preference(self)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)

        self.closed_event = threading.Event()

        self.parent_window = parent
        self.interface_mode = interface_mode
        self.created_prefixes = []

        cfg = ConfigManager()
        self.steamgriddb_enabled = (
            cfg.config.get('steamgriddb-enabled', 'False') == 'True'
            and bool(cfg.config.get('steamgriddb-api-key', '').strip('"'))
        )

        init_addon_defaults(self)

        os.makedirs(COVERS_DIR, exist_ok=True)
        os.makedirs(BANNERS_DIR, exist_ok=True)

        self.cover_path_temp = os.path.join(COVERS_DIR, "cover_temp.png")
        if os.path.isfile(self.cover_path_temp):
            os.remove(self.cover_path_temp)
        self.banner_path_temp = os.path.join(BANNERS_DIR, "banner_temp.png")
        if os.path.isfile(self.banner_path_temp):
            os.remove(self.banner_path_temp)
        self.icon_directory = f"{ICONS_DIR}/icon_temp/"
        os.makedirs(self.icon_directory, exist_ok=True)

        self.icons_path = ICONS_DIR
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.png'

        self.box = self.get_content_area()
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)
        self.box.set_halign(Gtk.Align.FILL)
        self.box.set_valign(Gtk.Align.CENTER)
        self.box.set_vexpand(True)
        self.box.set_hexpand(True)

        box_buttons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_buttons.set_valign(Gtk.Align.CENTER)

        self.grid_page1 = Gtk.Grid()
        self.grid_page1.set_column_homogeneous(True)
        self.grid_page1.set_column_spacing(10)
        self.grid_page2 = Gtk.Grid()
        self.grid_page2.set_column_homogeneous(True)
        self.grid_page2.set_column_spacing(10)

        self.grid_launcher = build_grid(margin_bottom=False)

        self.grid_title = build_grid(margin_bottom=False)

        self.grid_steam_user = build_grid(margin_bottom=False)

        self.grid_steam_title = build_grid(margin_bottom=False)

        self.grid_path = build_grid(margin_bottom=False)

        self.grid_runtime = build_grid(margin_bottom=False)

        self.grid_prefix = build_grid(margin_bottom=False)

        self.grid_runner = build_grid(margin_bottom=False)

        self.grid_shortcut = build_grid(column_homogeneous=True)

        self.grid_shortcut_icon = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)

        self.grid_protonfix = build_grid(margin_bottom=False)

        self.grid_launch_settings = build_grid(margin_bottom=False)

        self.grid_game_arguments = build_grid(margin_bottom=False)

        self.grid_lossless = build_grid(margin_bottom=False)

        self.grid_addapp = build_grid(margin_bottom=False)

        self.grid_tools = build_grid()

        add_css_once("addgame_dialog", """
        .entry {
            border: 1px solid red;
        }
        .combobox {
            border: 1px solid red;
        }
        .add-game-media-button {
            padding: 0;
            border: none;
            box-shadow: none;
        }
        .add-game-banner-button {
            border-radius: 0;
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

        self.label_steam_user = Gtk.Label(label=_("Steam User"))
        self.label_steam_user.set_halign(Gtk.Align.START)

        def build_steam_user_combobox(users):
            combobox = IdComboBox()
            for account_id, persona_name in users:
                combobox.append(account_id, f"{persona_name} ({account_id})", short_text=persona_name)
            if not users:
                combobox.append(None, "")
            combobox.set_active(0)
            return combobox

        steam_users = read_steam_users()
        self.steam_users = steam_users
        self.combobox_steam_user = build_steam_user_combobox(steam_users)
        self.combobox_steam_user.set_sensitive(bool(steam_users))
        if not steam_users:
            self.combobox_steam_user.set_tooltip_text(_("No Steam users found"))
        self.combobox_steam_user.connect("changed", self.on_combobox_steam_user_changed)

        self.label_steam_title = Gtk.Label(label=_("Title"))
        self.label_steam_title.set_halign(Gtk.Align.START)
        self.combobox_steam_title = None

        self.steam_title_filter_keywords = [
            "Proton",
            "Steam Linux Runtime",
            "Steamworks Common Redistributables",
        ]

        initial_steam_user = self.combobox_steam_user.get_active_id() if steam_users else 'all'
        self.populate_steam_title_combobox(initial_steam_user)

        self.label_title = Gtk.Label(label=_("Title"))
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", on_entry_changed)
        if interface_mode in ("Covers", "Carrousel") or self.steamgriddb_enabled:
            title_focus_controller = Gtk.EventControllerFocus()
            title_focus_controller.connect("leave", lambda c: self.on_entry_focus_out())
            self.entry_title.add_controller(title_focus_controller)
        self.entry_title.set_has_tooltip(True)
        self.entry_title.connect("query-tooltip", on_entry_query_tooltip)

        self._steamgriddb_suggestion_id = None
        self._steamgriddb_steam_appid = None
        self._suggestion_source = None
        self._suggestion_programmatic = False
        self._virtual_keyboard_active_for_title = False

        if self.steamgriddb_enabled:
            self.popover_suggestion = Gtk.Popover()
            self.popover_suggestion.set_has_arrow(False)
            self.popover_suggestion.set_autohide(False)
            self.popover_suggestion.add_css_class("suggestion-popover")
            self.popover_suggestion.set_parent(self.entry_title)

            self.listbox_suggestion = Gtk.ListBox()
            self.listbox_suggestion.set_selection_mode(Gtk.SelectionMode.NONE)
            self.listbox_suggestion.connect("row-activated", self.on_suggestion_row_activated)

            suggestion_scroll = Gtk.ScrolledWindow()
            suggestion_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            suggestion_scroll.set_max_content_height(250)
            suggestion_scroll.set_propagate_natural_height(True)
            suggestion_scroll.set_size_request(300, -1)
            suggestion_scroll.set_child(self.listbox_suggestion)

            self.popover_suggestion.set_child(suggestion_scroll)

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
        self.entry_path.set_tooltip_text(_("Path to the game executable"))
        self.entry_path.set_has_tooltip(True)
        self.entry_path.connect("query-tooltip", on_entry_query_tooltip)
        path_action_group = Gio.SimpleActionGroup()

        action_path_executable = Gio.SimpleAction.new("executable", None)
        action_path_executable.connect("activate", lambda action, param: self.on_button_search_clicked(None))
        path_action_group.add_action(action_path_executable)

        action_path_installer = Gio.SimpleAction.new("installer", None)
        action_path_installer.connect("activate", lambda action, param: self.on_button_installer_clicked(None))
        path_action_group.add_action(action_path_installer)

        self.insert_action_group("pathaction", path_action_group)

        path_action_menu = Gio.Menu()
        path_action_menu.append(_("Select an executable"), "pathaction.executable")
        path_action_menu.append(_("Run an installer"), "pathaction.installer")

        self.button_path_action = Gtk.MenuButton()
        self.button_path_action.set_icon_name("system-search-symbolic")
        self.button_path_action.set_size_request(50, -1)
        self.button_path_action.set_menu_model(path_action_menu)

        self.button_search = Gtk.Button()
        self.button_search.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search.connect("clicked", self.on_button_search_clicked)
        self.button_search.set_size_request(50, -1)
        self.button_search.set_visible(False)

        self.box_path_action = Gtk.Box()
        self.box_path_action.append(self.button_path_action)
        self.box_path_action.append(self.button_search)

        self.label_runtime = Gtk.Label(label=_("Runtime"))
        self.label_runtime.set_halign(Gtk.Align.START)
        self.label_runtime.set_visible(False)
        self.combobox_runtime = IdComboBox()
        self.combobox_runtime.set_visible(False)

        self.label_prefix = Gtk.Label(label=_("Prefix"))
        self.label_prefix.set_halign(Gtk.Align.START)
        self.entry_prefix = Gtk.Entry()
        self.entry_prefix.connect("changed", on_entry_changed)
        self.entry_prefix.set_tooltip_text(_("Path to the prefix"))
        self.entry_prefix.set_has_tooltip(True)
        self.entry_prefix.connect("query-tooltip", on_entry_query_tooltip)
        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        self.checkbox_custom_runner = Gtk.CheckButton(label=_("Specific Proton"))
        self.checkbox_custom_runner.connect("toggled", self.on_checkbox_custom_runner_toggled)
        self.combobox_runner = IdComboBox()

        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_child(
            Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_search_protonfix.connect("clicked", on_button_search_protonfix_clicked)
        self.button_search_protonfix.set_size_request(50, -1)

        self.label_game_arguments = Gtk.Label(label=_("Game Arguments"))
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text("-d3d11 -fullscreen")

        self.button_launch_settings = Gtk.Button(label=_("Launch Settings"))
        self.button_launch_settings.connect("clicked", self.on_button_launch_settings_clicked)

        self.button_addapp = Gtk.Button(label=_("Additional Application"))
        self.button_addapp.connect("clicked", self.on_button_addapp_clicked)
        self.button_addapp.set_tooltip_text(
            _("Additional application to run with the game"))

        self.button_lossless = Gtk.Button(label=_("Lossless Scaling Frame Generation"))
        self.button_lossless.connect("clicked", self.on_button_lossless_clicked)

        create_mangohud_gamemode_checkboxes(self)
        self.checkbox_sdl = Gtk.CheckButton(label="SDL")
        self.checkbox_sdl.set_tooltip_text(_("May fix gamepad issues with some games"))
        self.checkbox_no_sleep = Gtk.CheckButton(label=_("No Sleep"))
        self.checkbox_no_sleep.set_tooltip_text(_("Prevents the system from suspending while gaming"))

        self.button_winecfg = Gtk.Button(label="Winecfg")
        self.button_winecfg.set_size_request(120, -1)
        self.button_winecfg.connect("clicked", self.on_button_winecfg_clicked)

        self.button_winetricks = Gtk.Button(label="Winetricks")
        self.button_winetricks.set_size_request(120, -1)
        self.button_winetricks.connect("clicked", self.on_button_winetricks_clicked)

        self.button_run = Gtk.Button(label=_("Run"))
        self.button_run.set_size_request(120, -1)
        self.button_run.connect("clicked", self.on_button_run_clicked)
        self.button_run.set_tooltip_text(_("Run a file in the prefix"))

        self.label_shortcut = Gtk.Label(label=_("Shortcut"))
        self.label_shortcut.set_margin_start(10)
        self.label_shortcut.set_margin_end(10)
        self.label_shortcut.set_margin_top(10)
        self.label_shortcut.set_halign(Gtk.Align.START)
        self.checkbox_shortcut_desktop = Gtk.CheckButton(label=_("Desktop"))
        self.checkbox_shortcut_appmenu = Gtk.CheckButton(label=_("App Menu"))
        self.checkbox_shortcut_steam = Gtk.CheckButton(label=_("Steam"))

        self.steam_shortcut_users = steam_users
        self.combobox_steam_shortcut_user = build_steam_user_combobox(steam_users)
        self.combobox_steam_shortcut_user.connect("changed", self.on_combobox_steam_shortcut_user_changed)

        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_size_request(120, -1)
        self.button_shortcut_icon.connect(
            "clicked",
            lambda w: self.on_button_shortcut_icon_clicked(w)
            if not self.steamgriddb_enabled
            else show_steamgriddb_picker(self, "icon")
        )
        self.button_shortcut_icon_overlay, self.spinner_icon = wrap_with_spinner(self.button_shortcut_icon, dim_shape="icon")

        icon_click_secondary = Gtk.GestureClick()
        icon_click_secondary.set_button(Gdk.BUTTON_SECONDARY)
        if self.steamgriddb_enabled:
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

        self.update_prefix_entry_handler_id = self.entry_title.connect("changed", self.update_prefix_entry)

        self.view_stack = Gtk.Stack()

        self.tab_switcher = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.tab_switcher.add_css_class("linked")
        self.tab_switcher.set_homogeneous(True)
        self.tab_switcher.set_hexpand(True)
        self.tab_switcher.set_margin_top(10)
        self.tab_switcher.set_margin_start(10)
        self.tab_switcher.set_margin_end(10)

        tab_buttons = [
            ("page1", _("Game/App")),
            ("page2", _("Tools")),
        ]
        first_button = None
        tab_button_widgets = []
        for name, label in tab_buttons:
            button = Gtk.ToggleButton(label=label)
            button.set_focusable(False)
            if first_button is None:
                first_button = button
                button.set_active(True)
            else:
                button.set_group(first_button)
            button.connect("toggled", lambda btn, n=name: self.view_stack.set_visible_child_name(n) if btn.get_active() else None)
            self.tab_switcher.append(button)
            tab_button_widgets.append(button)

        self.tab_names = [n for n, _ in tab_buttons]
        self.tab_button_widgets = tab_button_widgets

        box_tabs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_tabs.append(self.tab_switcher)
        box_tabs.append(self.view_stack)

        frame = Gtk.Frame()
        frame.set_margin_top(10)
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_child(box_tabs)

        frame_scroll = Gtk.ScrolledWindow()
        frame_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        frame_scroll.set_propagate_natural_height(True)
        frame_scroll.set_vexpand(True)
        frame_scroll.set_child(frame)

        self.box.append(frame_scroll)

        def on_cover_primary_click(button):
            if self.interface_mode in ("Covers", "Carrousel") and self.steamgriddb_enabled:
                show_steamgriddb_picker(self, "cover")

        def build_cover_button():
            picture = new_picture()
            picture.set_can_shrink(True)
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_hexpand(True)
            picture.set_vexpand(True)
            picture.set_halign(Gtk.Align.FILL)
            picture.set_valign(Gtk.Align.FILL)
            content, spinner = wrap_with_spinner(picture, dim_shape="cover")
            button = Gtk.Button()
            button.set_size_request(260, 390)
            button.set_margin_top(10)
            button.set_margin_bottom(10)
            button.set_margin_start(10)
            button.set_margin_end(10)
            button.set_vexpand(True)
            button.set_valign(Gtk.Align.CENTER)
            button.set_halign(Gtk.Align.CENTER)
            button.set_overflow(Gtk.Overflow.HIDDEN)
            button.set_child(content)
            button.add_css_class("add-game-media-button")
            button.add_css_class("cover-empty")
            button.connect("clicked", on_cover_primary_click)
            click_secondary = Gtk.GestureClick()
            click_secondary.set_button(Gdk.BUTTON_SECONDARY)
            click_secondary.connect("pressed", self.on_image_clicked)
            button.add_controller(click_secondary)
            return picture, button, spinner

        self.image_cover, self.button_cover, self.spinner_cover1 = build_cover_button()
        self.image_cover2, self.button_cover2, self.spinner_cover2 = build_cover_button()

        self.picture_banner1 = new_picture()
        self.picture_banner1.set_can_shrink(True)
        self.picture_banner1.set_content_fit(Gtk.ContentFit.COVER)
        self.picture_banner1.set_hexpand(True)
        self.picture_banner1.set_vexpand(True)
        self.picture_banner1.set_halign(Gtk.Align.FILL)
        self.picture_banner1.set_valign(Gtk.Align.FILL)
        self.button_banner1 = Gtk.Button()
        self.button_banner1.set_hexpand(True)
        self.button_banner1.set_vexpand(True)
        self.button_banner1.set_overflow(Gtk.Overflow.HIDDEN)
        self.button_banner1.set_child(self.picture_banner1)
        self.button_banner1.add_css_class("add-game-media-button")
        self.button_banner1.add_css_class("add-game-banner-button")
        self.button_banner1.add_css_class("banner-placeholder")

        self.banner_preview1 = Gtk.AspectFrame.new(0.5, 0.5, 1920 / 620, False)
        self.banner_preview1.set_child(self.button_banner1)
        self.banner_preview1.set_hexpand(True)

        self.button_banner1.connect("clicked", lambda w: show_steamgriddb_picker(self, "banner"))

        banner_click_secondary1 = Gtk.GestureClick()
        banner_click_secondary1.set_button(Gdk.BUTTON_SECONDARY)
        banner_click_secondary1.connect("pressed", lambda g, n, x, y: self.on_image_clicked(g, n, x, y, "banner"))
        self.button_banner1.add_controller(banner_click_secondary1)

        self.banner_preview1_overlay, self.spinner_banner1 = wrap_with_spinner(self.banner_preview1)

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

        self.grid_page1.attach(page1, 0, 1, 1, 1)
        if interface_mode in ("Covers", "Carrousel"):
            self.grid_page1.attach(self.button_cover, 1, 1, 1, 1)
        page1.set_hexpand(True)

        self.view_stack.add_titled(self.grid_page1, "page1", _("Game/App"))

        page2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.grid_page2.attach(page2, 0, 1, 1, 1)
        if interface_mode in ("Covers", "Carrousel"):
            self.grid_page2.attach(self.button_cover2, 1, 1, 1, 1)
        page2.set_hexpand(True)

        self.view_stack.add_titled(self.grid_page2, "page2", _("Tools"))

        self.grid_launcher.attach(self.combobox_launcher, 1, 0, 1, 1)
        self.combobox_launcher.set_hexpand(True)
        self.combobox_launcher.set_valign(Gtk.Align.CENTER)

        self.grid_steam_user.attach(self.label_steam_user, 0, 0, 4, 1)
        self.grid_steam_user.attach(self.combobox_steam_user, 0, 1, 4, 1)
        self.combobox_steam_user.set_hexpand(True)

        self.grid_steam_title.attach(self.label_steam_title, 0, 0, 4, 1)
        self.grid_steam_title.attach(self.combobox_steam_title, 0, 1, 4, 1)
        self.combobox_steam_title.set_hexpand(True)

        self.grid_title.attach(self.label_title, 0, 0, 4, 1)
        self.grid_title.attach(self.entry_title, 0, 1, 4, 1)
        self.entry_title.set_hexpand(True)

        self.grid_path.attach(self.label_path, 0, 0, 1, 1)
        self.grid_path.attach(self.entry_path, 0, 1, 3, 1)
        self.entry_path.set_hexpand(True)
        self.grid_path.attach(self.box_path_action, 3, 1, 1, 1)

        self.grid_runtime.attach(self.label_runtime, 0, 0, 1, 1)
        self.grid_runtime.attach(self.combobox_runtime, 0, 1, 1, 1)
        self.combobox_runtime.set_hexpand(True)

        self.grid_prefix.attach(self.label_prefix, 0, 0, 1, 1)
        self.grid_prefix.attach(self.entry_prefix, 0, 1, 3, 1)
        self.entry_prefix.set_hexpand(True)
        self.grid_prefix.attach(self.button_search_prefix, 3, 1, 1, 1)

        self.grid_runner.attach(self.checkbox_custom_runner, 0, 0, 1, 1)
        self.grid_runner.attach(self.combobox_runner, 0, 1, 1, 1)
        self.combobox_runner.set_hexpand(True)

        self.label_shortcut.set_hexpand(True)
        self.grid_shortcut.attach(self.checkbox_shortcut_desktop, 0, 0, 1, 1)
        self.checkbox_shortcut_desktop.set_hexpand(True)
        self.grid_shortcut.attach(self.checkbox_shortcut_appmenu, 0, 1, 1, 1)
        self.checkbox_shortcut_appmenu.set_hexpand(True)
        self.grid_shortcut.attach(self.checkbox_shortcut_steam, 0, 2, 1, 1)
        self.checkbox_shortcut_steam.set_hexpand(True)
        self.grid_shortcut.attach(self.combobox_steam_shortcut_user, 1, 2, 1, 1)
        self.combobox_steam_shortcut_user.set_hexpand(True)
        self.grid_shortcut_icon.append(self.button_shortcut_icon_overlay)
        self.grid_shortcut.attach(self.grid_shortcut_icon, 1, 0, 1, 2)

        page1.append(self.grid_launcher)
        page1.append(self.grid_steam_user)
        page1.append(self.grid_steam_title)
        page1.append(self.grid_title)
        page1.append(self.grid_path)
        page1.append(self.grid_runtime)
        page1.append(self.grid_prefix)
        page1.append(self.grid_runner)
        page1.append(self.label_shortcut)
        page1.append(self.grid_shortcut)

        if interface_mode in ("Covers", "Carrousel") and self.steamgriddb_enabled:
            box_tabs.insert_child_after(self.banner_preview1_overlay, None)

            banner_ratio = 1920 / 620
            banner_size_state = {"width": -1}

            def on_addgame_banner_tick(widget, frame_clock, box=self.banner_preview1_overlay, state=banner_size_state):
                width = widget.get_width()
                if width > 0 and width != state["width"]:
                    state["width"] = width
                    box.set_size_request(-1, int(width / banner_ratio))
                return True

            self.banner_preview1_overlay.add_tick_callback(on_addgame_banner_tick)

        self.grid_protonfix.attach(self.label_protonfix, 0, 0, 1, 1)
        self.grid_protonfix.attach(self.entry_protonfix, 0, 1, 3, 1)
        self.entry_protonfix.set_hexpand(True)
        self.grid_protonfix.attach(self.button_search_protonfix, 3, 1, 1, 1)

        self.grid_game_arguments.attach(self.label_game_arguments, 0, 0, 4, 1)
        self.grid_game_arguments.attach(self.entry_game_arguments, 0, 1, 4, 1)
        self.entry_game_arguments.set_hexpand(True)

        self.grid_lossless.attach(self.button_lossless, 0, 0, 1, 1)
        self.button_lossless.set_hexpand(True)

        self.grid_launch_settings.attach(self.button_launch_settings, 0, 0, 1, 1)
        self.button_launch_settings.set_hexpand(True)

        self.grid_addapp.attach(self.button_addapp, 0, 0, 1, 1)
        self.button_addapp.set_hexpand(True)

        box_buttons.append(self.button_winetricks)
        box_buttons.append(self.button_winecfg)
        box_buttons.append(self.button_run)

        self.grid_tools.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        self.checkbox_gamemode.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_no_sleep, 0, 2, 1, 1)
        self.checkbox_no_sleep.set_hexpand(True)
        self.grid_tools.attach(self.checkbox_sdl, 0, 3, 1, 1)
        self.checkbox_sdl.set_hexpand(True)
        self.grid_tools.attach(box_buttons, 2, 0, 1, 4)

        page2.append(self.grid_protonfix)
        page2.append(self.grid_game_arguments)
        page2.append(self.grid_launch_settings)
        page2.append(self.grid_addapp)
        page2.append(self.grid_lossless)
        page2.append(self.grid_tools)

        bottom_box = build_bottom_button_box(self.button_cancel, self.button_ok)
        bottom_box.set_margin_top(10)

        self.box.append(bottom_box)

        self.populate_combobox_with_launchers()
        self.combobox_launcher.set_active_id("windows")
        self.combobox_launcher.connect("changed", self.on_combobox_changed)

        self.populate_combobox_with_runners()
        self.populate_combobox_with_runtimes()
        self.combobox_runtime.set_active_id("umu-steamrt4")

        self.on_checkbox_custom_runner_toggled(self.checkbox_custom_runner)

        self.checkbox_mangohud.set_active(self.default_mangohud)
        self.checkbox_gamemode.set_active(self.default_gamemode)
        self.checkbox_no_sleep.set_active(self.default_no_sleep)
        self.checkbox_sdl.set_active(self.default_sdl_enabled)

        disable_mangohud_gamemode_if_missing(self)

        if not self.steam_shortcut_users:
            self.checkbox_shortcut_steam.set_sensitive(False)
            self.checkbox_shortcut_steam.set_tooltip_text(_("No Steam users found"))
            self.combobox_steam_shortcut_user.set_sensitive(False)
            self.combobox_steam_shortcut_user.set_tooltip_text(_("No Steam users found"))

        if not os.path.exists(LSFGVK_PATH):
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Vulkan Layer not found"))

        self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

        self.grid_steam_title.set_visible(False)
        self.grid_steam_user.set_visible(False)
        self.update_image_cover()
        if interface_mode not in ("Covers", "Carrousel"):
            self.button_cover.set_visible(False)
            self.button_cover2.set_visible(False)


        self.present()

    def on_combobox_steam_changed(self, combobox):
        self.combobox_steam_title.remove_css_class("combobox")

        title = self.combobox_steam_title.get_active_text()
        steamid = self.combobox_steam_title.get_active_id()

        if not title or not steamid:
            return

        self.set_title_silently(title)
        self._steamgriddb_suggestion_id = None
        self._steamgriddb_steam_appid = steamid
        if getattr(self, 'popover_suggestion', None) is not None:
            self.popover_suggestion.popdown()

        self.entry_path.set_text(steamid)

        icon_path = get_steam_icon_path(steamid)
        if not icon_path:
            icon_path = FAUGUS_PNG

        self.get_artwork()

        shutil.copyfile(icon_path, os.path.expanduser(self.icon_temp))
        self.refresh_icon_preview()

    def on_button_launch_settings_clicked(self, widget):
        def on_result(result, pre_launch, post_launch):
            self.launch_arguments = result
            self.pre_launch = pre_launch
            self.post_launch = post_launch
        show_launch_arguments_dialog(self, self.launch_arguments, self.pre_launch, self.post_launch, on_result)

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

    def on_image_clicked(self, gesture, n_press, x, y, category="cover"):
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
        if category == "banner":
            return self.banner_path_temp, self.refresh_banner_preview
        if category == "icon":
            return self.icon_temp, self.refresh_icon_preview
        return self.cover_path_temp, self.update_image_cover

    def on_refresh(self, widget):
        self.menu.popdown()
        category = self._menu_category
        dest_path, refresh = self.artwork_target(category)

        if self.entry_title.get_text() == "":
            if os.path.isfile(dest_path):
                os.remove(dest_path)
            refresh()
            return

        if self.steamgriddb_enabled:
            self.refresh_single_artwork(category)
        else:
            self.get_artwork()

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
            "cover": self.set_cover_loading,
            "banner": self.set_banner_loading,
        }[category]
        key = {"icon": "icons", "cover": "grids", "banner": "heroes"}[category]

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
                content = verified_content(session.get(url, timeout=15))
                idle_add_while_open(closed_event, self.apply_downloaded_artwork, category, content)
            except requests.RequestException as e:
                print(f"Error refreshing SteamGridDB {category}: {e}")
            finally:
                idle_add_while_open(closed_event, loading_setter, False)

        run_in_background(worker)

    def on_load_file(self, widget):
        self.menu.popdown()
        category = self._menu_category
        dest_path, refresh = self.artwork_target(category)

        titles = {
            "cover": _("Select an image for the cover"),
            "banner": _("Select an image for the banner"),
            "icon": _("Select an image for the icon"),
        }

        filechooser = new_file_chooser(
            self,
            titles.get(category, titles["cover"]),
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
        category = self._menu_category
        dest_path, refresh = self.artwork_target(category)
        dialog = Gtk.Dialog(title=_("Enter the image URL"), transient_for=self)
        apply_titlebar_preference(dialog)
        hide_dialog_action_area(dialog)
        dialog.set_modal(True)
        dialog.set_resizable(False)

        entry = Gtk.Entry()

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

    def set_cover_loading(self, loading):
        set_spinner_loading((self.spinner_cover1, self.spinner_cover2), loading)
        return False

    def set_banner_loading(self, loading):
        set_spinner_loading((self.spinner_banner1,), loading)
        return False

    def set_icon_loading(self, loading):
        set_spinner_loading((self.spinner_icon,), loading)
        return False

    def refresh_icon_preview(self):
        surface = self.new_texture_from_image(self.icon_temp, 50, 50)
        self.button_shortcut_icon.set_child(new_picture(surface))

    def refresh_banner_preview(self):
        self.update_banner_preview(self.banner_path_temp)

    def apply_downloaded_artwork(self, category, content):
        if category == "icon":
            content = resize_icon_bytes(normalize_icon_bytes(content), 256)
        if not is_valid_image_bytes(content):
            print(f"Downloaded {category} artwork is corrupted or incomplete, ignoring.")
            return
        dest_path, refresh = self.artwork_target(category)
        with open(dest_path, "wb") as f:
            f.write(content)
        refresh()

    def update_banner_preview(self, banner_path):
        if banner_path and os.path.isfile(banner_path):
            pixbuf = safe_load_pixbuf(banner_path, None, None, False)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            surface = HiDpiPaintable(texture, 480, 155)
            self.picture_banner1.set_paintable(surface)
            self.button_banner1.remove_css_class("banner-placeholder")
        else:
            self.picture_banner1.set_paintable(None)
            self.button_banner1.add_css_class("banner-placeholder")

    def get_artwork(self):
        import requests

        closed_event = self.closed_event
        cover_path_temp = self.cover_path_temp
        banner_path_temp = self.banner_path_temp
        steamgriddb_enabled = self.steamgriddb_enabled

        game_name = self.entry_title.get_text().strip()
        if not game_name:
            return

        suggestion_id = self._steamgriddb_suggestion_id
        steam_appid = self._steamgriddb_steam_appid

        cfg = ConfigManager()
        api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')

        fetch_icon = steamgriddb_enabled
        fetch_cover = self.interface_mode in ("Covers", "Carrousel")
        fetch_banner_art = fetch_cover and steamgriddb_enabled

        if fetch_icon:
            self.set_icon_loading(True)
        if fetch_cover:
            self.set_cover_loading(True)
        if fetch_banner_art:
            self.set_banner_loading(True)

        def fetch_artwork():
            try:
                icon_url = cover_url = banner_url = None
                if steamgriddb_enabled:
                    session = get_steamgriddb_session()
                    candidates = fetch_steamgriddb_candidates(
                        api_key, game_name, limit=1, game_id=suggestion_id, steam_appid=steam_appid
                    )

                    if fetch_icon:
                        icon_url = candidates["icons"][0]["url"] if candidates["icons"] else None
                        if not icon_url:
                            print(f"SteamGridDB: no icon found for '{game_name}'")

                    if fetch_banner_art:
                        cover_url = candidates["grids"][0]["url"] if candidates["grids"] else None
                        banner_url = candidates["heroes"][0]["url"] if candidates["heroes"] else None
                        if not cover_url:
                            print(f"SteamGridDB: no cover found for '{game_name}'")
                        if not banner_url:
                            print(f"SteamGridDB: no banner found for '{game_name}'")

                    downloads = {
                        category: url
                        for category, url in (("icon", icon_url), ("cover", cover_url), ("banner", banner_url))
                        if url
                    }

                    def download_one(category):
                        try:
                            content = verified_content(session.get(downloads[category], timeout=15))
                            idle_add_while_open(closed_event, self.apply_downloaded_artwork, category, content)
                        except requests.RequestException as e:
                            print(f"Error fetching SteamGridDB {category}: {e}")

                    if downloads:
                        with ThreadPoolExecutor(max_workers=len(downloads)) as pool:
                            list(pool.map(download_one, downloads.keys()))

                if fetch_banner_art:
                    if not cover_url and os.path.isfile(cover_path_temp):
                        os.remove(cover_path_temp)
                        idle_add_while_open(closed_event, self.update_image_cover)
                    if not banner_url and os.path.isfile(banner_path_temp):
                        os.remove(banner_path_temp)
                        idle_add_while_open(closed_event, self.refresh_banner_preview)
                    return

                if not fetch_cover:
                    return

                api_url = f"https://steamgrid.usebottles.com/api/search/{game_name}"
                try:
                    response = requests.get(api_url)
                    response.raise_for_status()
                    image_url = response.text.strip('"')
                    content = verified_content(requests.get(image_url))
                    idle_add_while_open(closed_event, self.apply_downloaded_artwork, "cover", content)

                except requests.RequestException as e:
                    print(f"Error fetching the cover: {e}")

            finally:
                if fetch_icon:
                    idle_add_while_open(closed_event, self.set_icon_loading, False)
                if fetch_cover:
                    idle_add_while_open(closed_event, self.set_cover_loading, False)
                if fetch_banner_art:
                    idle_add_while_open(closed_event, self.set_banner_loading, False)

        run_in_background(fetch_artwork)

    def update_image_cover(self):
        if os.path.isfile(self.cover_path_temp):
            pixbuf = safe_load_pixbuf(self.cover_path_temp, None, None, False)
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            surface = HiDpiPaintable(texture, 260, 390)
            self.image_cover.set_paintable(surface)
            self.image_cover2.set_paintable(surface)
            self.button_cover.remove_css_class("cover-empty")
            self.button_cover2.remove_css_class("cover-empty")
        else:
            self.image_cover.set_paintable(None)
            self.image_cover2.set_paintable(None)
            self.button_cover.add_css_class("cover-empty")
            self.button_cover2.add_css_class("cover-empty")

    def on_entry_focus_out(self):
        if self._steamgriddb_suggestion_id is not None:
            return
        if self.entry_title.get_text() != "":
            self.get_artwork()
        else:
            if os.path.isfile(self.cover_path_temp):
                os.remove(self.cover_path_temp)
            self.update_image_cover()

    def on_title_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape and self.popover_suggestion.get_visible():
            self.popover_suggestion.popdown()
            return True
        return False

    def on_title_focus_leave_for_suggestions(self):
        closed_event = self.closed_event
        entry_title = self.entry_title

        def check():
            if closed_event.is_set():
                return False
            root = entry_title.get_root()
            w = root.get_focus() if root else None
            while w is not None:
                if w is self.popover_suggestion:
                    return False
                w = w.get_parent()
            self.popover_suggestion.popdown()
            return False

        GLib.idle_add(check)

    def on_dialog_click_for_suggestions(self, gesture, n_press, x, y):
        if not self.popover_suggestion.get_visible():
            return

        w = self.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None:
            if w is self.popover_suggestion or w is self.entry_title:
                return
            w = w.get_parent()

        self.popover_suggestion.popdown()

    def on_title_changed_for_suggestions(self, entry):
        if self._suggestion_programmatic or self._virtual_keyboard_active_for_title:
            return

        self._steamgriddb_suggestion_id = None
        self._steamgriddb_steam_appid = None

        if self._suggestion_source:
            GLib.source_remove(self._suggestion_source)
            self._suggestion_source = None

        text = entry.get_text().strip()
        if not text:
            self.popover_suggestion.popdown()
            return

        cfg = ConfigManager()
        api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
        if not api_key:
            return

        closed_event = self.closed_event

        def fire():
            self._suggestion_source = None
            if closed_event.is_set():
                return False
            self.fetch_title_suggestions(text, api_key)
            return False

        self._suggestion_source = GLib.timeout_add(350, fire)

    def fetch_title_suggestions(self, term, api_key):
        closed_event = self.closed_event

        def worker():
            suggestions = fetch_steamgriddb_autocomplete(api_key, term, limit=10)
            idle_add_while_open(closed_event, self.populate_suggestions, term, suggestions)

        run_in_background(worker)

    def populate_suggestions(self, term, suggestions):
        if self.entry_title.get_text().strip() != term:
            return

        child = self.listbox_suggestion.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox_suggestion.remove(child)
            child = nxt

        if not suggestions:
            self.popover_suggestion.popdown()
            return

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
            self.listbox_suggestion.append(row)

        self.popover_suggestion.popup()

    def set_title_silently(self, text):
        self._suggestion_programmatic = True
        self.entry_title.set_text(text)
        self._suggestion_programmatic = False

    def apply_title_suggestion(self, name, game_id):
        self.set_title_silently(re.sub(r'\s*\(\d{4}\)\s*$', '', name).strip())
        self._steamgriddb_suggestion_id = game_id

    def on_suggestion_row_activated(self, listbox, row):
        self.apply_title_suggestion(row.steamgriddb_name, row.steamgriddb_id)
        self.popover_suggestion.popdown()
        self.entry_title.grab_focus_without_selecting()
        self.get_artwork()

    def fetch_title_suggestions_for_keyboard(self, term):
        cfg = ConfigManager()
        api_key = cfg.config.get('steamgriddb-api-key', '').strip('"')
        if not api_key:
            return []
        suggestions = fetch_steamgriddb_autocomplete(api_key, term, limit=10)
        return [{"label": s["name"], "value": s} for s in suggestions]

    def on_keyboard_suggestion_selected(self, item):
        self.apply_title_suggestion(item["name"], item["id"])
        self.get_artwork()

    def cleanup_fields(self):
        self.entry_title.set_text("")
        self.launch_arguments = ""
        self.pre_launch = ""
        self.post_launch = ""
        self.entry_path.set_text("")
        self.entry_prefix.set_text("")
        self.checkbox_shortcut_desktop.set_active(False)
        self.checkbox_shortcut_appmenu.set_active(False)
        self.checkbox_shortcut_steam.set_active(False)
        self.entry_protonfix.set_text("")
        self.entry_game_arguments.set_text("")
        self.checkbox_mangohud.set_active(self.default_mangohud)
        self.checkbox_gamemode.set_active(self.default_gamemode)
        self.checkbox_sdl.set_active(self.default_sdl_enabled)
        self.checkbox_no_sleep.set_active(self.default_no_sleep)
        self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())
        if os.path.isfile(self.cover_path_temp):
            os.remove(self.cover_path_temp)
        if os.path.isfile(self.banner_path_temp):
            os.remove(self.banner_path_temp)
        self.update_image_cover()
        self.update_banner_preview(self.banner_path_temp)

        self.combobox_steam_title.set_active(0)

        for w in (self.combobox_steam_title, self.entry_title,
                  self.entry_prefix, self.entry_path):
            w.remove_css_class("entry")

    def on_combobox_changed(self, combobox, skip_cleanup=False):
        active_id = combobox.get_active_id()

        if not skip_cleanup:
            self.cleanup_fields()

        self.grid_title.set_visible(False)
        self.grid_steam_title.set_visible(False)
        self.grid_steam_user.set_visible(False)
        self.grid_path.set_visible(False)
        self.button_path_action.set_visible(False)
        self.button_search.set_visible(True)
        self.grid_runner.set_visible(False)
        self.grid_runtime.set_visible(False)
        self.grid_prefix.set_visible(False)
        self.button_winetricks.set_visible(False)
        self.button_winecfg.set_visible(False)
        self.button_run.set_visible(False)
        self.grid_protonfix.set_visible(False)
        self.grid_addapp.set_visible(False)
        self.checkbox_sdl.set_visible(False)
        self.checkbox_no_sleep.set_visible(True)
        self.checkbox_shortcut_steam.set_visible(True)
        self.combobox_steam_shortcut_user.set_visible(True)
        self.combobox_runtime.set_visible(False)
        self.grid_page2.set_visible(True)
        self.tab_button_widgets[self.tab_names.index("page2")].set_visible(True)
        self.tab_switcher.set_visible(True)
        self.button_shortcut_icon.set_visible(True)

        if active_id == "windows":
            self.grid_title.set_visible(True)
            self.grid_path.set_visible(True)
            self.button_path_action.set_visible(True)
            self.button_search.set_visible(False)
            self.grid_runner.set_visible(True)
            self.grid_prefix.set_visible(True)
            self.button_winetricks.set_visible(True)
            self.button_winecfg.set_visible(True)
            self.button_run.set_visible(True)
            self.grid_protonfix.set_visible(True)
            self.grid_addapp.set_visible(True)
            self.checkbox_sdl.set_visible(True)

        elif active_id == "linux":
            self.grid_title.set_visible(True)
            self.grid_path.set_visible(True)
            self.grid_runtime.set_visible(True)
            self.label_runtime.set_visible(True)
            self.combobox_runtime.set_visible(True)

        elif active_id == "steam":
            self.grid_steam_title.set_visible(True)
            self.grid_steam_user.set_visible(True)
            self.checkbox_shortcut_steam.set_visible(False)
            self.combobox_steam_shortcut_user.set_visible(False)
            self.grid_page2.set_visible(False)
            self.tab_button_widgets[self.tab_names.index("page2")].set_visible(False)
            self.tab_switcher.set_visible(False)

        else:
            self.grid_runner.set_visible(True)
            self.grid_prefix.set_visible(True)
            self.button_winetricks.set_visible(True)
            self.button_winecfg.set_visible(True)
            self.button_run.set_visible(True)
            self.grid_protonfix.set_visible(True)
            self.checkbox_sdl.set_visible(True)
            self.button_shortcut_icon.set_visible(self.steamgriddb_enabled)

            self.set_title_silently(self.combobox_launcher.get_active_text())
            if getattr(self, 'popover_suggestion', None) is not None:
                self.popover_suggestion.popdown()

            if active_id in ("amazon", "ea", "epic", "rockstar", "ubisoft"):
                self.launch_arguments = "PROTON_ENABLE_WAYLAND=0"
            elif active_id == "battle":
                self.launch_arguments = "WINE_SIMULATE_WRITECOPY=1\nPROTON_ENABLE_WAYLAND=0"

            path = LAUNCHER_EXE_PATHS.get(active_id, "")
            if path:
                self.entry_path.set_text(f"{self.entry_prefix.get_text()}/{path}")

        if self.interface_mode in ("Covers", "Carrousel") and self.entry_title.get_text():
            self.get_artwork()

    def populate_combobox_with_launchers(self):
        self.combobox_launcher.append("windows", _("Windows Game"))
        self.combobox_launcher.append("linux", _("Linux Game"))
        self.combobox_launcher.append("steam", _("Steam Game"))
        self.combobox_launcher.append("amazon", "Amazon Games")
        self.combobox_launcher.append("battle", "Battle.net")
        self.combobox_launcher.append("ea", "EA App")
        self.combobox_launcher.append("epic", "Epic Games")
        self.combobox_launcher.append("gog", "GOG Galaxy")
        self.combobox_launcher.append("rockstar", "Rockstar Launcher")
        self.combobox_launcher.append("ubisoft", "Ubisoft Connect")
        self.combobox_launcher.append("wargaming", "Wargaming Game Center")

    def populate_combobox_with_runtimes(self):
        self.combobox_runtime.append("umu-steamrt4", "SteamRT4 ({})".format(_("Default")))
        self.combobox_runtime.append("umu-sniper", "Sniper")
        self.combobox_runtime.append("umu-soldier", "Soldier")
        self.combobox_runtime.append("umu-scout", "Scout")
        self.combobox_runtime.append("disable-runtime", _("Disabled"))

    def populate_combobox_with_runners(self):
        populate_combobox_with_runners(self.combobox_runner)

    def on_checkbox_custom_runner_toggled(self, checkbox):
        custom = checkbox.get_active()
        self.combobox_runner.set_sensitive(custom)
        if not custom and not self.combobox_runner.set_active_id(self.default_runner):
            self.combobox_runner.set_active(0)

    def selected_runner(self):
        return self.combobox_runner.get_active_id() if self.checkbox_custom_runner.get_active() else "Default"

    def load_config(self):
        cfg = ConfigManager()

        self.default_runner = cfg.config.get('default-runner', '')
        self.default_prefix = cfg.config.get('default-prefix', '')
        self.default_mangohud = cfg.config.get('mangohud') == 'True'
        self.default_gamemode = cfg.config.get('gamemode') == 'True'
        self.default_sdl_enabled = cfg.config.get('sdl-enabled') == 'True'
        self.default_no_sleep = cfg.config.get('no-sleep-enabled') == 'True'

    def record_created_prefix(self, prefix):
        if prefix and os.path.isdir(prefix) and prefix not in self.created_prefixes:
            self.created_prefixes.append(prefix)

    def on_button_run_clicked(self, widget):
        if not self.validate_fields(entry="prefix"):
            return

        filechooser = new_file_chooser(
            self,
            _("Select a file to run in the prefix"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "run_in_prefix")

        add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                file_run = dialog_fc.get_file().get_path()
                title = self.entry_title.get_text()
                prefix = expand_path(self.entry_prefix.get_text())
                title_formatted = format_title(title)
                runner = self.combobox_runner.get_active_id()
                game_directory = os.path.dirname(file_run)
                cwd = game_directory if game_directory and os.path.isdir(game_directory) else None
                escaped_file_run = file_run.replace("'", "'\\''")
                command_parts = []

                if title_formatted:
                    command_parts.append(f"LOG_DIR={title_formatted}")
                if prefix:
                    command_parts.append(f"WINEPREFIX='{prefix}'")
                if runner:
                    command_parts.append(f"PROTONPATH='{resolve_protonpath(runner)}'")
                if escaped_file_run.endswith(".reg"):
                    command_parts.append(f"'{UMU_RUN}' regedit '{escaped_file_run}'")
                else:
                    command_parts.append(f"'{UMU_RUN}' '{escaped_file_run}'")

                command = ' '.join(command_parts)
                cmd = (sys.executable, "-m", "faugus.runner", command)

                def run_command():
                    process = subprocess.Popen(cmd, cwd=cwd, env=subprocess_env())
                    process.wait()
                    GLib.idle_add(self.record_created_prefix, prefix)

                run_in_background(run_command)

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_button_installer_clicked(self, widget):
        if not self.validate_fields(entry="prefix"):
            return

        filechooser = new_file_chooser(
            self,
            _("Select the game installer"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "run_in_prefix")

        add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                file_run = dialog_fc.get_file().get_path()
                title = self.entry_title.get_text()
                prefix = expand_path(self.entry_prefix.get_text())
                title_formatted = format_title(title)
                runner = self.combobox_runner.get_active_id()
                game_directory = os.path.dirname(file_run)
                cwd = game_directory if game_directory and os.path.isdir(game_directory) else None
                escaped_file_run = file_run.replace("'", "'\\''")
                command_parts = []

                if title_formatted:
                    command_parts.append(f"LOG_DIR={title_formatted}")
                if prefix:
                    command_parts.append(f"WINEPREFIX='{prefix}'")
                if runner:
                    command_parts.append(f"PROTONPATH='{resolve_protonpath(runner)}'")
                command_parts.append(f"'{UMU_RUN}' '{escaped_file_run}'")

                command = ' '.join(command_parts)
                cmd = (sys.executable, "-m", "faugus.runner", command)

                existing_shortcuts = list_prefix_shortcuts(prefix)

                def run_command():
                    process = subprocess.Popen(cmd, cwd=cwd, env=subprocess_env())
                    process.wait()
                    GLib.idle_add(self.record_created_prefix, prefix)

                    detected_path = None
                    for attempt in range(10):
                        detected_path = detect_installed_executable(prefix, existing_shortcuts)
                        if detected_path or attempt == 9:
                            break
                        threading.Event().wait(2)

                    if detected_path:
                        GLib.idle_add(self.entry_path.set_text, detected_path)

                        if not self.steamgriddb_enabled:
                            status = self.extract_shortcut_icon(detected_path)
                            GLib.idle_add(self.apply_shortcut_icon_status, status)

                run_in_background(run_command)

            destroy_and_release(dialog_fc)

        filechooser.connect("response", on_response)
        filechooser.present()

    def set_image_shortcut_icon(self):
        shutil.copyfile(FAUGUS_PNG_RASTER, self.icon_temp)

        surface = self.new_texture_from_image(self.icon_temp, 50, 50)
        image = new_picture(surface)

        return image

    def extract_shortcut_icon(self, path):
        os.makedirs(self.icon_directory, exist_ok=True)
        return extract_ico(path, self.icon_temp)

    def apply_shortcut_icon_status(self, status):
        if status == "ok":
            self.refresh_icon_preview()
        elif status == "no_icons":
            self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

    def on_combobox_steam_shortcut_user_changed(self, combobox):
        title = self.entry_title.get_text().strip()
        if not title:
            return
        steam_user = combobox.get_active_id()
        if hasattr(self.parent_window, 'check_steam_shortcut'):
            has_shortcut = self.parent_window.check_steam_shortcut(title, steam_user)
            self.checkbox_shortcut_steam.set_active(has_shortcut)

    def populate_steam_title_combobox(self, steam_user):
        new_combobox = IdComboBox()
        new_combobox.append(None, "")
        for appid, name in read_installed_games(steam_user):
            lname = name.lower()
            if any(keyword.lower() in lname for keyword in self.steam_title_filter_keywords):
                continue
            new_combobox.append(appid, name)
        new_combobox.disable_first_item_selection()
        new_combobox.set_hexpand(True)
        new_combobox.set_sensitive(bool(self.steam_users))
        new_combobox.connect("changed", self.on_combobox_steam_changed)

        old_combobox = self.combobox_steam_title
        if old_combobox is not None:
            parent = old_combobox.get_parent()
            if parent is not None:
                parent.remove(old_combobox)
                parent.attach(new_combobox, 0, 1, 4, 1)
            old_combobox.release()

        self.combobox_steam_title = new_combobox

    def on_combobox_steam_user_changed(self, combobox):
        steam_user = combobox.get_active_id()
        self.cleanup_fields()
        GLib.timeout_add(200, self._populate_steam_title_combobox_once, steam_user)

    def _populate_steam_title_combobox_once(self, steam_user):
        self.populate_steam_title_combobox(steam_user)
        return False

    def on_button_shortcut_icon_clicked(self, widget):
        if not self.validate_fields(entry="path"):
            return

        path = expand_path(self.entry_path.get_text())

        if os.path.isfile(path):
            os.makedirs(self.icon_directory, exist_ok=True)
            status = extract_ico(path, self.icon_converted)
            if status == "no_icons":
                self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

        choose_shortcut_icon(self)

    def check_existing_shortcut(self, gameid=None):
        title = self.entry_title.get_text().strip()
        if not gameid and not title:
            return

        title_formatted = gameid or format_title(title)
        desktop_file_path = f"{DESKTOP_DIR}/{title_formatted}.desktop"
        applications_shortcut_path = f"{APP_DIR}/{title_formatted}.desktop"

        self.checkbox_shortcut_desktop.set_active(os.path.exists(desktop_file_path))
        self.checkbox_shortcut_appmenu.set_active(os.path.exists(applications_shortcut_path))

    def update_prefix_entry(self, entry):
        title_formatted = format_title(entry.get_text())
        prefix = f"{self.default_prefix}/{title_formatted}"
        self.entry_prefix.set_text(prefix)

    def on_button_winecfg_clicked(self, widget):
        self.set_sensitive(False)

        if not self.validate_fields(entry="prefix"):
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        prefix = expand_path(self.entry_prefix.get_text())
        title_formatted = format_title(title)
        runner = self.combobox_runner.get_active_id()

        command_parts = []

        if title_formatted:
            command_parts.append(f"LOG_DIR='{title_formatted}'")
        if prefix:
            command_parts.append(f"WINEPREFIX='{prefix}'")
        if runner:
            command_parts.append(f"PROTONPATH='{resolve_protonpath(runner)}'")

        command_parts.append(f"'{UMU_RUN}'")
        command_parts.append("'winecfg'")

        command = ' '.join(command_parts)

        print(command)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command], env=subprocess_env())
            process.wait()
            GLib.idle_add(self.record_created_prefix, prefix)
            GLib.idle_add(self.set_sensitive, True)

        run_in_background(run_command)

    def on_button_winetricks_clicked(self, widget):
        self.set_sensitive(False)

        if not self.validate_fields(entry="prefix"):
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        prefix = expand_path(self.entry_prefix.get_text())
        title_formatted = format_title(title)
        runner = self.combobox_runner.get_active_id()

        command_parts = []

        if title_formatted:
            command_parts.append(f"LOG_DIR={title_formatted}")
        if prefix:
            command_parts.append(f"WINEPREFIX='{prefix}'")
        command_parts.append("GAMEID=winetricks-gui")
        command_parts.append("STORE=none")
        if runner:
            command_parts.append(f"PROTONPATH='{resolve_protonpath(runner)}'")

        command_parts.append(f"'{UMU_RUN}'")
        command_parts.append("''")

        command = ' '.join(command_parts)

        print(command)

        def run_command():
            process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command, "winetricks"], env=subprocess_env())
            process.wait()
            GLib.idle_add(self.record_created_prefix, prefix)
            GLib.idle_add(self.set_sensitive, True)

        run_in_background(run_command)

    def on_button_search_clicked(self, widget):
        entry_value = self.entry_path.get_text()
        preferred_path = os.path.dirname(entry_value) if entry_value else None

        filechooser = new_file_chooser(
            self,
            _("Select the game executable"),
            Gtk.FileChooserAction.OPEN,
        )
        set_file_chooser_start_folder(filechooser, "game_exe", preferred_path)

        if self.combobox_launcher.get_active_id() != "linux":
            add_windows_file_filters(filechooser)

        def on_response(dialog_fc, response):
            if response == Gtk.ResponseType.ACCEPT:
                path = dialog_fc.get_file().get_path()

                if not self.steamgriddb_enabled:
                    status = self.extract_shortcut_icon(path)
                    self.apply_shortcut_icon_status(status)

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

        filechooser.set_current_folder(Gio.File.new_for_path(expand_path(self.entry_prefix.get_text() or self.default_prefix)))

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
        prefix = self.entry_prefix.get_text()
        path = self.entry_path.get_text()

        self.combobox_steam_title.remove_css_class("combobox")
        self.entry_title.remove_css_class("entry")
        self.entry_prefix.remove_css_class("entry")
        self.entry_path.remove_css_class("entry")

        page1_button = self.tab_button_widgets[self.tab_names.index("page1")]

        if self.grid_steam_title.get_visible() and not self.combobox_steam_title.get_active_text():
            self.combobox_steam_title.add_css_class("combobox")
            page1_button.set_active(True)

        required = {
            "prefix": [(self.entry_title, title), (self.entry_prefix, prefix)],
            "path": [(self.entry_title, title), (self.entry_path, path)],
            "path+prefix": [(self.entry_title, title), (self.entry_path, path), (self.entry_prefix, prefix), (self.entry_title, format_title(title))],
        }.get(entry, [])
        invalid = [widget for widget, value in required if not value]
        for widget in invalid:
            widget.add_css_class("entry")
        if invalid:
            page1_button.set_active(True)
            return False
        return True


def build_desktop_file_content(title, exec_args, icon_path, working_directory):
    if IS_FLATPAK:
        exec_line = f'Exec=flatpak run --command={LAUNCHER_PATH} io.github.Faugus.faugus-launcher {LAUNCHER_MODULE_ARGS}{exec_args}\n'
    else:
        exec_line = f'Exec={LAUNCHER_PATH} {LAUNCHER_MODULE_ARGS}{exec_args}\n'

    return (
        f'[Desktop Entry]\n'
        f'Name={title}\n'
        f'{exec_line}'
        f'Icon={icon_path}\n'
        f'Type=Application\n'
        f'Categories=Game;\n'
        f'Path={working_directory}\n'
    )


def create_shortcuts_from_installer(prefix, existing_shortcuts):
    new_shortcuts = list_prefix_shortcuts(prefix) - existing_shortcuts
    resolved = resolve_new_shortcuts(prefix, new_shortcuts)
    best = pick_best_shortcut(resolved)
    if not best:
        return

    unix_path = best["target"]
    title = best["name"]
    on_desktop = any(r["on_desktop"] for r in resolved if r["target"] == unix_path)
    on_appmenu = any(r["on_appmenu"] for r in resolved if r["target"] == unix_path)
    if not (on_desktop or on_appmenu):
        return

    title_formatted = format_title(title)
    applications_shortcut_path = f"{APP_DIR}/{title_formatted}.desktop"
    desktop_shortcut_path = f"{DESKTOP_DIR}/{title_formatted}.desktop"

    needs_appmenu = on_appmenu and not os.path.isfile(applications_shortcut_path)
    needs_desktop = on_desktop and not os.path.isfile(desktop_shortcut_path)
    if not (needs_appmenu or needs_desktop):
        return

    os.makedirs(SHORTCUT_ICONS_DIR, exist_ok=True)
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(DESKTOP_DIR, exist_ok=True)

    icon_final = os.path.join(SHORTCUT_ICONS_DIR, f"{title_formatted}.png")
    status = extract_ico(unix_path, icon_final)
    icon_path = icon_final if status == "ok" else FAUGUS_PNG

    game_directory = os.path.dirname(unix_path)

    desktop_file_content = build_desktop_file_content(
        title, f'"{unix_path}"', icon_path, game_directory
    )

    for needed, shortcut_path in ((needs_appmenu, applications_shortcut_path), (needs_desktop, desktop_shortcut_path)):
        if needed:
            with open(shortcut_path, 'w') as f:
                f.write(desktop_file_content)
            os.chmod(shortcut_path, 0o755)


def run_file(file_path):
    cfg = ConfigManager()

    default_prefix = cfg.config.get('default-prefix', '').strip('"')
    mangohud = cfg.config.get('mangohud', 'False') == 'True'
    gamemode = cfg.config.get('gamemode', 'False') == 'True'
    sdl_enabled = cfg.config.get('sdl-enabled', 'False') == 'True'
    no_sleep = cfg.config.get('no-sleep-enabled', 'False') == 'True'
    default_runner = cfg.config.get('default-runner', '').strip('"')
    auto_create_shortcuts = cfg.config.get('auto-create-shortcuts', 'False') == 'True'

    if file_path.endswith(".reg"):
        mangohud = False
        gamemode = False
        sdl_enabled = False
        no_sleep = False

    file_dir = os.path.dirname(os.path.abspath(file_path))
    prefix = f"{expand_path(default_prefix)}/default"
    command_parts = []

    if sdl_enabled:
        command_parts.append("PROTON_PREFER_SDL=1")
    if no_sleep:
        command_parts.append("NO_SLEEP=1")
    command_parts.append(f'WINEPREFIX="{prefix}"')
    if default_runner:
        command_parts.append(f'PROTONPATH="{resolve_protonpath(default_runner)}"')
    if gamemode:
        command_parts.append("gamemoderun")
    if mangohud:
        command_parts.append("mangohud")
    command_parts.append(f'"{UMU_RUN}"')
    if file_path.endswith(".reg"):
        command_parts.append(f'regedit "{file_path}"')
    else:
        command_parts.append(f'"{file_path}"')

    command = ' '.join(command_parts)

    if auto_create_shortcuts and not file_path.endswith(".reg"):
        existing_shortcuts = list_prefix_shortcuts(prefix)
        process = subprocess.Popen([sys.executable, "-m", "faugus.runner", command], cwd=file_dir, env=subprocess_env())
        process.wait()

        for attempt in range(10):
            if list_prefix_shortcuts(prefix) - existing_shortcuts or attempt == 9:
                break
            threading.Event().wait(2)

        create_shortcuts_from_installer(prefix, existing_shortcuts)
    else:
        subprocess.Popen([sys.executable, "-m", "faugus.runner", command], cwd=file_dir, env=subprocess_env())


def main():
    suppress_adwaita_theme_warning()

    start_hidden = "--hide" in sys.argv
    console_mode = "--console" in sys.argv
    sys.argv = [arg for arg in sys.argv if arg not in ("--hide", "--console", "--ui-child")]

    if len(sys.argv) == 2:
        run_file(sys.argv[1])
        sys.exit(0)

    app = FaugusApp(start_hidden, console_mode)
    app.run(sys.argv)


def prefixes_count(prefix):
    games = load_json_file(GAMES_JSON)
    return sum(1 for x in games if x.get("prefix") == prefix) - 1


if __name__ == "__main__":
    main()
