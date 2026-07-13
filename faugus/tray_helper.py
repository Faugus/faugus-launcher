

import os
import json
import shutil
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')

from gi.repository import Gtk, GLib, AyatanaAppIndicator3
from faugus.path_manager import (
    IS_FLATPAK, PathManager, faugus_mono_icon, games_json, latest_games,
)
from faugus.config_manager import ConfigManager
from faugus.language_config import setup_gettext
from faugus.tray_ipc import send_command, COMMAND_PRESENT, COMMAND_QUIT, COMMAND_LAUNCH


GLib.log_set_handler("libayatana-appindicator", GLib.LogLevelFlags.LEVEL_WARNING, lambda *a: None)

_ = setup_gettext('faugus-launcher')


def load_json_file(filepath, default=None):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


if IS_FLATPAK:
    tray_icon = 'io.github.Faugus.faugus-launcher'
    mono_dest = Path(PathManager.user_data('faugus-launcher/faugus-mono.svg'))
    mono_dest.parent.mkdir(parents=True, exist_ok=True)
    if not mono_dest.exists():
        shutil.copy(faugus_mono_icon, mono_dest)
    faugus_mono_icon = PathManager.user_data('faugus-launcher/faugus-mono.svg')
else:
    tray_icon = PathManager.get_icon('faugus-launcher.svg')

GLib.set_prgname("faugus-launcher")


class TrayHelper:
    def __init__(self):
        self.cfg = ConfigManager()
        mono_icon = self.cfg.config.get('mono-icon', 'False') == 'True'
        icon = faugus_mono_icon if mono_icon else tray_icon

        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "faugus-launcher",
            icon,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_icon_theme_path("")
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self.menu = Gtk.Menu()
        self.menu.connect("show", self.on_menu_show)
        self.indicator.set_menu(self.menu)

    def on_menu_show(self, menu):
        for child in menu.get_children():
            menu.remove(child)

        games_by_id = {}
        for entry in load_json_file(games_json, []):
            gameid = entry.get("gameid")
            if gameid:
                games_by_id[gameid] = entry.get("title", gameid)

        added = 0
        if os.path.exists(latest_games):
            with open(latest_games) as f:
                for gameid in map(str.strip, f):
                    if added >= 5:
                        break
                    title = games_by_id.get(gameid)
                    if not title:
                        continue
                    item = Gtk.MenuItem(label=title)
                    item.connect("activate", self.on_game_selected, gameid)
                    menu.append(item)
                    added += 1

        if added:
            menu.append(Gtk.SeparatorMenuItem())

        restore_item = Gtk.MenuItem(label=_("Open Faugus"))
        restore_item.connect("activate", self.on_restore)
        menu.append(restore_item)

        quit_item = Gtk.MenuItem(label=_("Quit"))
        quit_item.connect("activate", self.on_quit)
        menu.append(quit_item)

        menu.show_all()

    def on_game_selected(self, widget, gameid):
        send_command(f"{COMMAND_LAUNCH}:{gameid}")

    def on_restore(self, widget):
        send_command(COMMAND_PRESENT)

    def on_quit(self, widget):
        send_command(COMMAND_QUIT)
        Gtk.main_quit()


def main():
    TrayHelper()
    Gtk.main()


if __name__ == "__main__":
    main()
