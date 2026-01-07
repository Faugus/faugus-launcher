#!/usr/bin/env python3

import gi
import sys
import subprocess
import argparse
import re
import json
import time
import shlex
import gettext

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, GLib, GdkPixbuf, Gio
from threading import Thread
from faugus.config_manager import *
from faugus.dark_theme import *

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')
if IS_FLATPAK:
    share_dir = os.path.expanduser('~/.local/share')
    faugus_png = PathManager.get_icon('io.github.Faugus.faugus-launcher.png')
else:
    share_dir = PathManager.user_data()
    faugus_png = PathManager.get_icon('faugus-launcher.png')

umu_run = PathManager.user_data('faugus-launcher/umu-run')
config_file_dir = PathManager.user_config('faugus-launcher/config.ini')
envar_dir = PathManager.user_config('faugus-launcher/envar.txt')
games_dir = PathManager.user_config('faugus-launcher/games.json')
faugus_launcher_dir = PathManager.user_config('faugus-launcher')
faugus_components = PathManager.find_binary('faugus-components')
faugus_proton_downloader = PathManager.find_binary('faugus-proton-downloader')
prefixes_dir = str(Path.home() / 'Faugus')
logs_dir = PathManager.user_config('faugus-launcher/logs')
faugus_notification = PathManager.system_data('faugus-launcher/faugus-notification.ogg')
eac_dir = f'PROTON_EAC_RUNTIME={PathManager.user_config("faugus-launcher/components/eac")}'
be_dir = f'PROTON_BATTLEYE_RUNTIME={PathManager.user_config("faugus-launcher/components/be")}'
proton_cachyos = PathManager.system_data('steam/compatibilitytools.d/proton-cachyos-slr/')

compatibility_dir = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
os.makedirs(compatibility_dir, exist_ok=True)

use_inhibit = os.path.exists("/run/dbus/system_bus_socket")

try:
    translation = gettext.translation(
        'faugus-run',
        localedir=LOCALE_DIR,
        languages=[lang] if lang else ['en_US']
    )
    translation.install()
    globals()['_'] = translation.gettext
except FileNotFoundError:
    gettext.install('faugus-run', localedir=LOCALE_DIR)
    globals()['_'] = gettext.gettext

class FaugusRun:
    def __init__(self, message):
        self.message = message
        self.process = None
        self.warning_dialog = None
        self.log_window = None
        self.text_view = None
        self.load_config()

    def show_error_dialog(self, protonpath):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_resizable(False)
        dialog.set_icon_from_file(faugus_png)
        subprocess.Popen(["canberra-gtk-play", "-f", faugus_notification])

        label = Gtk.Label()
        label.set_label(_("%s was not found.") % protonpath)
        label.set_halign(Gtk.Align.CENTER)

        label2 = Gtk.Label()
        label2.set_label(_("Please install it or use another Proton version."))
        label2.set_halign(Gtk.Align.CENTER)

        button_yes = Gtk.Button(label=_("Ok"))
        button_yes.set_size_request(150, -1)
        button_yes.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

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
        box_top.pack_start(label2, True, True, 0)
        box_bottom.pack_start(button_yes, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        dialog.show_all()
        dialog.run()
        dialog.destroy()
        Gtk.main_quit()
        sys.exit()

    def update_protonpath(self, message):
        versions = [
            d for d in os.listdir(compatibility_dir)
            if os.path.isdir(os.path.join(compatibility_dir, d)) and d.startswith("proton-EM-")
        ]

        if not versions:
            return message

        def version_key(v):
            version_str = v.replace("proton-EM-", "")

            if version_str.isdigit():
                return (int(version_str), "")

            match = re.match(r"^(\d+)([A-Za-z]*)$", version_str)
            if match:
                num_part = int(match.group(1))
                alpha_part = match.group(2)
                return (num_part, alpha_part)

            return (0, version_str)

        versions.sort(key=version_key, reverse=True)
        latest_version = versions[0]
        updated_message = re.sub(r'PROTONPATH=Proton-EM\b', f'PROTONPATH={latest_version}', message)
        return updated_message

    def update_test(self):
        if "Proton-EM" in self.message:
            self.message = self.update_protonpath(self.message)

    def start_process(self, command):
        self.start_time = time.time()
        protonpath = next((part.split('=')[1] for part in self.message.split() if part.startswith("PROTONPATH=")), None)
        if protonpath and protonpath != "GE-Proton" and protonpath != "Proton-EM":
            if protonpath == "Proton-CachyOS" and not os.path.exists(proton_cachyos):
                self.close_warning_dialog()
                self.show_error_dialog(protonpath)
            if protonpath == "Linux-Native":
                pass
            else:
                protonpath_path = Path(share_dir) / 'Steam/compatibilitytools.d' / protonpath
                if not protonpath_path.is_dir():
                    self.close_warning_dialog()
                    self.show_error_dialog(protonpath)

        if self.default_runner == "UMU-Proton Latest":
            self.default_runner = ""
        if self.default_runner == "GE-Proton Latest (default)":
            self.default_runner = "GE-Proton"
        if self.default_runner == "Proton-EM Latest":
            self.default_runner = "Proton-EM"

        self.discrete_gpu = "DRI_PRIME=1"
        if not self.discrete_gpu:
            self.discrete_gpu = "DRI_PRIME=0"
        if self.discrete_gpu:
            self.discrete_gpu = "DRI_PRIME=1"
        if self.discrete_gpu == None:
            self.discrete_gpu = "DRI_PRIME=1"

        if "WINEPREFIX" not in self.message:
            if self.default_runner:
                if "PROTONPATH" not in self.message:
                    if "UMU_NO_PROTON" not in self.message:
                        if self.default_runner:
                            if self.default_runner == "Proton-CachyOS":
                                self.message = f'WINEPREFIX="{self.default_prefix}/default" PROTONPATH={proton_cachyos} {self.message}'
                            else:
                                self.message = f'WINEPREFIX="{self.default_prefix}/default" PROTONPATH={self.default_runner} {self.message}'
                else:
                    self.message = f'WINEPREFIX="{self.default_prefix}/default" {self.message}'
            else:
                self.message = f'WINEPREFIX="{self.default_prefix}/default" {self.message}'

        if not "winetricks-gui" in self.message:
            for part in self.message.split():
                if part.startswith("GAMEID="):
                    game_id = part.split("=")[1]
                    if "umu" not in game_id:
                        self.message = f'PROTONFIXES_DISABLE=1 {self.message}'
                    break

        if self.wayland_driver:
            self.message = f'PROTON_ENABLE_WAYLAND=1 {self.message}'
            if self.enable_hdr:
                self.message = f'PROTON_ENABLE_HDR=1 {self.message}'
        if self.enable_wow64:
            self.message = f'PROTON_USE_WOW64=1 {self.message}'
        if "LSFG_LEGACY" in self.message:
            if self.lossless_location:
                self.message = f'LSFG_DLL_PATH="{self.lossless_location}" {self.message}'

        if self.enable_logging:
            match = re.search(r"FAUGUS_LOG=(?:'([^']*)'|\"([^\"]*)\"|(\S+))", self.message)
            if match:
                self.game_title = next(g for g in match.groups() if g).split("/")[-1]
            else:
                self.game_title = "default"

        self.load_env_from_file(envar_dir)
        self.run_processes_sequentially()

    def load_env_from_file(self, filename=envar_dir):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()
                    os.environ[key] = value
        except FileNotFoundError:
            pass

    def run_processes_sequentially(self):
        if "UMU_NO_PROTON" not in self.message:
            if self.enable_logging:
                self.message = f'UMU_LOG=1 PROTON_LOG_DIR={logs_dir}/{self.game_title} PROTON_LOG=1 {self.message}'

        if "Proton-EM" in self.message:
            self.process = subprocess.Popen(
                [sys.executable, "-m", "faugus.proton_downloader"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=8192,
                text=True
            )

            self.stdout_watch_id = GLib.io_add_watch(
                self.process.stdout,
                GLib.PRIORITY_LOW,
                GLib.IO_IN,
                self.on_output
            )
            self.stderr_watch_id = GLib.io_add_watch(
                self.process.stderr,
                GLib.PRIORITY_LOW,
                GLib.IO_IN,
                self.on_output
            )

            GLib.child_watch_add(
                GLib.PRIORITY_DEFAULT,
                self.process.pid,
                self.on_proton_downloader_finished
            )
        else:
            self.execute_final_command()

        print(self.message)

    def on_proton_downloader_finished(self, pid, status):
        if hasattr(self, 'stdout_watch_id'):
            GLib.source_remove(self.stdout_watch_id)
        if hasattr(self, 'stderr_watch_id'):
            GLib.source_remove(self.stderr_watch_id)
        self.update_test()

        self.execute_final_command()

    def execute_final_command(self):
        if "UMU_NO_PROTON" not in self.message:
            cmd = f"{sys.executable} -m faugus.components; {self.discrete_gpu} {eac_dir} {be_dir} {self.message}"
        else:
            cmd = f"{self.discrete_gpu} {eac_dir} {be_dir} {self.message}"

        use_inhibit = os.path.exists("/run/dbus/system_bus_socket")
        popen_cmd = None
        inhibit_ok = False

        try:
            import dbus

            bus = dbus.SessionBus()
            portal = bus.get_object(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop"
            )
            iface = dbus.Interface(
                portal, "org.freedesktop.portal.Inhibit"
            )

            iface.Inhibit(
                "",
                8,
                {"reason": "Game is running"}
            )
            inhibit_ok = True
        except Exception:
            pass

        if not inhibit_ok and not IS_FLATPAK:
            systemd_inhibit = PathManager.find_binary("systemd-inhibit")

            if use_inhibit and systemd_inhibit:
                popen_cmd = [
                    systemd_inhibit,
                    "--what=sleep",
                    "--why=Game is running",
                    "--mode=block",
                    PathManager.find_binary("bash"),
                    "-c",
                    cmd
                ]

        if popen_cmd is None:
            popen_cmd = [
                PathManager.find_binary("bash"),
                "-c",
                cmd
            ]

        self.process = subprocess.Popen(
            popen_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=8192,
            text=True
        )

        self.stdout_watch_id = GLib.io_add_watch(
            self.process.stdout,
            GLib.PRIORITY_LOW,
            GLib.IO_IN,
            self.on_output
        )
        self.stderr_watch_id = GLib.io_add_watch(
            self.process.stderr,
            GLib.PRIORITY_LOW,
            GLib.IO_IN,
            self.on_output
        )

        GLib.child_watch_add(
            GLib.PRIORITY_DEFAULT,
            self.process.pid,
            self.on_process_exit
        )

    def load_config(self):
        cfg = ConfigManager()

        self.discrete_gpu = cfg.config.get('discrete-gpu', 'False') == 'True'
        self.splash_disable = cfg.config.get('splash-disable', 'False') == 'True'
        self.default_runner = cfg.config.get('default-runner', '')
        self.lossless_location = cfg.config.get('lossless-location', '')
        self.default_prefix = cfg.config.get('default-prefix', '')
        self.enable_logging = cfg.config.get('enable-logging', 'False') == 'True'
        self.wayland_driver = cfg.config.get('wayland-driver', 'False') == 'True'
        self.enable_hdr = cfg.config.get('enable-hdr', 'False') == 'True'
        self.enable_wow64 = cfg.config.get('enable-wow64', 'False') == 'True'
        self.language = cfg.config.get('language', '')

    def show_warning_dialog(self):
        self.warning_dialog = Gtk.Window(title="Faugus Launcher")
        self.warning_dialog.set_decorated(False)
        self.warning_dialog.set_resizable(False)
        self.warning_dialog.set_default_size(280, -1)
        self.warning_dialog.set_icon_from_file(faugus_png)

        frame = Gtk.Frame()
        frame.set_label_align(0.5, 0.5)
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        grid = Gtk.Grid()
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)
        frame.add(grid)

        image_path = faugus_png
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)

        pixbuf = pixbuf.scale_simple(75, 75, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_margin_top(20)
        image.set_margin_start(20)
        image.set_margin_end(20)
        image.set_margin_bottom(20)
        grid.attach(image, 0, 0, 1, 1)

        self.label = Gtk.Label()
        self.label.set_margin_start(20)
        self.label.set_margin_end(20)

        self.label2 = Gtk.Label()
        self.label2.set_margin_bottom(20)
        self.label2.set_margin_start(20)
        self.label2.set_margin_end(20)

        grid.attach(self.label, 0, 1, 1, 1)
        grid.attach(self.label2, 0, 2, 1, 1)

        self.warning_dialog.add(frame)

        if not self.splash_disable:
            self.warning_dialog.show_all()

    def show_log_window(self):
        self.log_window = Gtk.Window(title="Winetricks Logs")
        self.log_window.set_default_size(600, 400)
        self.log_window.set_icon_from_file(faugus_png)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        scrolled_window.add(self.text_view)
        self.log_window.add(scrolled_window)

        self.log_window.connect("delete-event", self.on_log_window_delete_event)
        self.log_window.show_all()

    def on_output(self, source, condition):
        if self.enable_logging:
            log_dir = f"{logs_dir}/{self.game_title}"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            if not hasattr(self, "_log_file_cleaned"):
                with open(f"{log_dir}/umu.log", "w") as log_file:
                    log_file.write("")
                self._log_file_cleaned = True

        def remove_ansi_escape(text):
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            return ansi_escape.sub('', text)

        if line := source.readline():
            clean_line = remove_ansi_escape(line).strip()

            if self.enable_logging:
                with open(f"{log_dir}/umu.log", "a") as log_file:
                    log_file.write(clean_line + "\n")
                    log_file.flush()

            self.check_game_output(clean_line)

            if "libgamemode.so.0" in clean_line or "libgamemodeauto.so.0" in clean_line or "libgamemode.so" in clean_line:
                return True

            if "winetricks" in self.message:
                self.append_to_text_view(clean_line)
            else:
                print(line, end='')

        return True

    def check_game_output(self, clean_line):
        if "Downloading" in clean_line or "Updating BattlEye..." in clean_line or "Updating Easy Anti-Cheat..." in clean_line or "Updating UMU-Launcher..." in clean_line:
            self.warning_dialog.show_all()
        if "Updating UMU-Launcher..." in clean_line:
            self.label.set_text(_("Updating UMU-Launcher..."))
        if "UMU-Launcher is up to date." in clean_line:
            self.label.set_text(_("UMU-Launcher is up to date"))
        if "Updating BattlEye..." in clean_line:
            self.label.set_text(_("Updating BattlEye..."))
        if "Updating Easy Anti-Cheat..." in clean_line:
            self.label.set_text(_("Updating Easy Anti-Cheat..."))
        if "Components are up to date." in clean_line:
            self.label.set_text(_("Components are up to date"))
        if "Downloading GE-Proton" in clean_line:
            self.label.set_text(_("Downloading GE-Proton..."))
        if "Downloading UMU-Proton" in clean_line:
            self.label.set_text(_("Downloading UMU-Proton..."))
        if "Downloading steamrt3 (latest)" in clean_line:
            self.label2.set_text(_("Downloading Steam Runtime..."))
        if "SteamLinuxRuntime_sniper.tar.xz" in clean_line:
            self.label2.set_text(_("Extracting Steam Runtime..."))
        if "Extracting GE-Proton" in clean_line:
            self.label.set_text(_("Extracting GE-Proton..."))
        if "Extracting UMU-Proton" in clean_line:
            self.label.set_text(_("Extracting UMU-Proton..."))
        if "GE-Proton is up to date" in clean_line:
            self.label.set_text(_("GE-Proton is up to date"))
        if "UMU-Proton is up to date" in clean_line:
            self.label.set_text(_("UMU-Proton is up to date"))
        if "steamrt3 is up to date" in clean_line:
            self.label2.set_text(_("Steam Runtime is up to date"))
        if "->" in clean_line and "GE-Proton" in clean_line:
            self.label.set_text(_("GE-Proton is up to date"))
        if "->" in clean_line and "UMU-Proton" in clean_line:
            self.label.set_text(_("UMU-Proton is up to date"))
        if "mtree is OK" in clean_line:
            self.label2.set_text(_("Steam Runtime is up to date"))
        if "Downloading proton-EM" in clean_line:
            self.label.set_text(_("Downloading Proton-EM..."))
        if "Extracting archive" in clean_line:
            self.label.set_text(_("Extracting Proton-EM..."))
        if "Proton installed successfully" in clean_line:
            self.label.set_text(_("Proton-EM is up to date"))

        if (
            "fsync" in clean_line
            or "NTSync" in clean_line
            or "Using winetricks" in clean_line
            or "Selected GPU" in clean_line
            or "Skipping fix execution" in clean_line
            or "Executable a unix path" in clean_line
            or "status: 0" in clean_line
            or "PosixPath" in clean_line
            or "SingleInstance" in clean_line
            or "mtree is OK" in clean_line
        ):
            GLib.timeout_add_seconds(0, self.close_warning_dialog)

    def append_to_text_view(self, clean_line):
        if self.text_view:

            if any(keyword in clean_line for keyword in
                   {"zenity", "Gtk-WARNING", "Gtk-Message", "pixbuf"}) or not clean_line:
                return

            buffer = self.text_view.get_buffer()
            end_iter = buffer.get_end_iter()
            buffer.insert(end_iter, clean_line + "\n")
            adj = self.text_view.get_parent().get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())

    def close_warning_dialog(self):
        if self.warning_dialog:
            self.warning_dialog.destroy()
            self.warning_dialog = None

    def close_log_window(self):
        if self.log_window:
            self.log_window.destroy()
            self.log_window = None

    def on_log_window_delete_event(self, widget, event):
        return True

    def show_exit_warning(self):
        parts = self.message.split()
        if parts:
            last_part = parts[-1].strip('"')

            if last_part.endswith(".reg"):
                dialog = Gtk.Dialog(title="Faugus Launcher", modal=True)
                dialog.set_resizable(False)
                dialog.set_icon_from_file(faugus_png)
                subprocess.Popen(["canberra-gtk-play", "-i", "dialog-information"])

                label = Gtk.Label()
                label.set_label(_("The keys and values were successfully added to the registry."))
                label.set_halign(Gtk.Align.CENTER)

                button_yes = Gtk.Button(label=_("Ok"))
                button_yes.set_size_request(150, -1)
                button_yes.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

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
                box_bottom.pack_start(button_yes, True, True, 0)

                content_area.add(box_top)
                content_area.add(box_bottom)

                dialog.show_all()
                dialog.run()
                dialog.destroy()
                Gtk.main_quit()
                sys.exit()

    def on_process_exit(self, pid, condition):
        if self.process.poll() is not None:

            end_time = time.time()
            runtime = int(end_time - getattr(self, "start_time", end_time))

            game_id = None
            for part in self.message.split():
                if part.startswith("GAMEID="):
                    game_id = part.split("=")[1]
                    break

            if game_id and os.path.exists(games_dir):
                try:
                    with open(games_dir, "r", encoding="utf-8") as f:
                        games = json.load(f)

                    for game in games:
                        if game.get("gameid") == game_id:
                            old_time = game.get("playtime", 0)
                            game["playtime"] = old_time + runtime
                            break

                    with open(games_dir, "w", encoding="utf-8") as f:
                        json.dump(games, f, indent=4)

                except Exception as e:
                    pass

            GLib.idle_add(self.close_warning_dialog)
            GLib.idle_add(self.close_log_window)
            GLib.idle_add(self.show_exit_warning)
            GLib.idle_add(Gtk.main_quit)

        return False

def handle_command(message, command=None):
    updater = FaugusRun(message)
    updater.show_warning_dialog()
    if command == "winetricks":
        updater.show_log_window()

    def run_process():
        updater.start_process(command)

    process_thread = Thread(target=run_process)

    def start_thread():
        process_thread.start()

    GLib.idle_add(start_thread)
    Gtk.main()

    process_thread.join()
    sys.exit(0)

def build_launch_command(game):
    gameid = game.get("gameid", "")
    path = game.get("path", "")
    prefix = game.get("prefix", "")
    launch_arguments = game.get("launch_arguments", "")
    game_arguments = game.get("game_arguments", "")
    protonfix = game.get("protonfix", "")
    runner = game.get("runner", "")
    addapp_bat = game.get("addapp_bat", "")
    mangohud = game.get("mangohud", "")
    gamemode = game.get("gamemode", "")
    disable_hidraw = game.get("disable_hidraw", "")
    addapp_checkbox = game.get("addapp_checkbox", "")
    lossless_enabled = game.get("lossless_enabled", "")
    lossless_multiplier = game.get("lossless_multiplier", "")
    lossless_flow = game.get("lossless_flow", "")
    lossless_performance = game.get("lossless_performance", "")
    lossless_hdr = game.get("lossless_hdr", "")

    if lossless_performance:
        lossless_performance = 1
    else:
        lossless_performance = 0
    if lossless_hdr:
        lossless_hdr = 1
    else:
        lossless_hdr = 0

    command_parts = []

    if gameid:
        command_parts.append(f"FAUGUS_LOG='{gameid}'")
    if mangohud:
        command_parts.append(mangohud)
    if disable_hidraw:
        command_parts.append(disable_hidraw)
    if protonfix:
        command_parts.append(f"GAMEID={protonfix}")
    else:
        command_parts.append(f"GAMEID={game['gameid']}")
    if runner:
        if runner == "Linux-Native":
            command_parts.append('UMU_NO_PROTON=1')
        elif runner == "Proton-CachyOS":
            command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
            command_parts.append(f"PROTONPATH={proton_cachyos}")
        else:
            command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
            command_parts.append(f"PROTONPATH={runner}")
    else:
        command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
    if gamemode:
        command_parts.append(gamemode)
    if launch_arguments:
        command_parts.append(launch_arguments)
    if lossless_enabled:
        command_parts.append("LSFG_LEGACY=1")
        if lossless_multiplier:
            command_parts.append(f"LSFG_MULTIPLIER={lossless_multiplier}")
        if lossless_flow:
            command_parts.append(f"LSFG_FLOW_SCALE={lossless_flow/100}")
        if lossless_performance:
            command_parts.append(f"LSFG_PERFORMANCE_MODE={1 if lossless_performance == 'true' else 0}")
        if lossless_hdr:
            command_parts.append(f"LSFG_HDR_MODE={1 if lossless_hdr == 'true' else 0}")

    command_parts.append(f"'{umu_run}'")

    if addapp_checkbox == "addapp_enabled":
        command_parts.append(shlex.quote(addapp_bat))
    else:
        command_parts.append(shlex.quote(path))

    if game_arguments:
        command_parts.append(game_arguments)

    return " ".join(command_parts)

def load_game_from_json(gameid):
    if not os.path.exists(games_dir):
        return None

    try:
        with open(games_dir, "r", encoding="utf-8") as f:
            games = json.load(f)
    except json.JSONDecodeError:
        return None

    for game in games:
        if game.get("gameid") == gameid:
            return game

    return None

def main():
    apply_dark_theme()

    parser = argparse.ArgumentParser(description=None)
    parser.add_argument("message", nargs='?')
    parser.add_argument("command", nargs='?', default=None)
    parser.add_argument("--game")

    args = parser.parse_args()

    if args.game:
        game = load_game_from_json(args.game)
        if not game:
            return

        launch_options = build_launch_command(game)
        handle_command(launch_options, None)
    else:
        handle_command(args.message, args.command)

if __name__ == "__main__":
    main()
