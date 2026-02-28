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
import signal
import shutil
import webbrowser

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf, Gio
from threading import Thread
from faugus.config_manager import *
from faugus.dark_theme import *

IS_FLATPAK = 'FLATPAK_ID' in os.environ or os.path.exists('/.flatpak-info')
from faugus.steam_setup import IS_STEAM_FLATPAK

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
prefixes_dir = str(Path.home() / 'Faugus')
logs_dir = PathManager.user_config('faugus-launcher/logs')
faugus_notification = PathManager.system_data('faugus-launcher/faugus-notification.ogg')
eac_dir = PathManager.user_config("faugus-launcher/components/eac")
be_dir = PathManager.user_config("faugus-launcher/components/be")
proton_cachyos = PathManager.system_data('steam/compatibilitytools.d/proton-cachyos-slr/')

compatibility_dir = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")
os.makedirs(compatibility_dir, exist_ok=True)

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

def format_title(title):
    title = title.strip().lower()
    title = re.sub(r"[^a-z0-9 ]+", "", title)
    title = re.sub(r"\s+", "-", title)
    return title

_env_set = set()
def set_env(key, value):
    os.environ[key] = value
    _env_set.add(key)

class FaugusRun:
    def __init__(self, message):
        self.message = message
        self.process = None
        self.warning_dialog = None
        self.log_window = None
        self.text_view = None
        self.proton_latest = None
        self._env_set = set()
        self.load_config()
        signal.signal(signal.SIGUSR1, self.on_process_exit)

    def start_process(self, command):
        if self.show_donate:
            if self.playtime >= 3600:
                current_month = GLib.DateTime.new_now_local().format("%Y-%m")

                if self.cfg.config.get("donate-last", "") != current_month:
                    self.show_donate_dialog()
                    self.cfg.set_value("donate-last", current_month)

        set_env("PROTON_EAC_RUNTIME", eac_dir)
        set_env("PROTON_BATTLEYE_RUNTIME", be_dir)

        if self.discrete_gpu:
            set_env("DRI_PRIME", "1")
        if self.wayland_driver:
            set_env("PROTON_ENABLE_WAYLAND", "1")
            if self.enable_hdr:
                set_env("PROTON_ENABLE_HDR", "1")
        if self.enable_wow64:
            set_env("PROTON_USE_WOW64", "1")

        self.extract_env_from_message()

        if os.environ.get("PROTONPATH") == "Steam":
            subprocess.Popen(self.message, shell=True)
            self.label.set_text(_("Starting Steam game..."))
            time.sleep(5)
            Gtk.main_quit()
            sys.exit()

        self.start_time = time.time()

        # LSFG_LEGACY env is deprecated in LSFG-VK 2.0
        if os.environ.get("LSFG_LEGACY") or os.environ.get("LSFGVK-ENV"):
            if self.lossless_location:
                set_env("LSFG_DLL_PATH", self.lossless_location) # Deprecated in LSFG-VK v2.0
                set_env("LSFGVK_DLL_PATH", self.lossless_location)

        if self.enable_logging:
            if os.environ.get("LOG_DIR"):
                self.log_dir = os.environ.get("LOG_DIR")
            else:
                self.log_dir = "default"

        if not os.environ.get("UMU_NO_PROTON"):
            if self.enable_logging:
                set_env("UMU_LOG", "1")
                set_env("PROTON_LOG_DIR", f"{logs_dir}/{self.log_dir}")
                set_env("PROTON_LOG", "1")

        if not os.environ.get("WINEPREFIX"):
            if not os.environ.get("UMU_NO_PROTON"):
                set_env("WINEPREFIX", f"{self.default_prefix}/default")
                if self.default_runner == "Proton-CachyOS":
                    set_env("PROTONPATH", f"{proton_cachyos}")
                else:
                    set_env("PROTONPATH", f"{self.default_runner}")

        if os.environ.get("GAMEID") != "winetricks-gui":
            if "umu" not in os.environ.get("GAMEID", "") and not (os.environ.get("GAMEID", "").isnumeric()):
                set_env("PROTONFIXES_DISABLE", "1")

        protonpath = os.environ.get("PROTONPATH")
        if protonpath and protonpath != "Proton-GE Latest" and protonpath != "Proton-EM Latest":
            if protonpath == "Proton-CachyOS" and not os.path.exists(proton_cachyos):
                self.close_warning_dialog()
                self.show_error_dialog(protonpath)
            if protonpath == "Linux-Native":
                pass
            if protonpath == "Steam":
                pass
            else:
                protonpath_path = Path(share_dir) / 'Steam/compatibilitytools.d' / protonpath
                if not protonpath_path.is_dir():
                    self.close_warning_dialog()
                    self.show_error_dialog(protonpath)
        if protonpath == "Proton-EM Latest":
            self.proton_latest = "--em"
        if protonpath == "Proton-GE Latest":
            self.proton_latest = "--ge"

        env_from_file = self.load_env_from_file(envar_dir)
        if env_from_file:
            print("\n=== GLOBAL ENVIRONMENT VARIABLES ===")
            for key in sorted(env_from_file):
                print(f"{key}={env_from_file[key]}")

        print("\n=== ENVIRONMENT VARIABLES ===")
        for key in sorted(_env_set):
            print(f"{key}={os.environ.get(key)}")

        print("\n=== UMU-LAUNCHER COMMAND ===")
        print(f"{self.message}\n")

        self.execute_final_command()

    def execute_final_command(self):
        if not os.environ.get("UMU_NO_PROTON"):
            if self.proton_latest:
                cmd = (
                    f"{sys.executable} -m faugus.proton_downloader {self.proton_latest}; "
                    f"{sys.executable} -m faugus.components; "
                    f"{self.message}"
                )
            else:
                cmd = (
                    f"{sys.executable} -m faugus.components; "
                    f"{self.message}"
                )
        else:
            cmd = f"{self.message}"

        prevent_sleep = os.environ.get("PREVENT_SLEEP")
        use_inhibit = os.path.exists("/run/dbus/system_bus_socket")
        popen_cmd = None
        inhibit_ok = False

        if prevent_sleep:
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

    def show_donate_dialog(self):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_decorated(False)
        dialog.set_resizable(False)
        dialog.set_icon_from_file(faugus_png)
        subprocess.Popen(["canberra-gtk-play", "-f", faugus_notification])

        css_provider = Gtk.CssProvider()
        css = """
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

        content_area = dialog.get_content_area()
        content_area.set_border_width(0)
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        frame = Gtk.Frame()
        frame.set_label_align(0.5, 0.5)
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        frame.add(frame_box)
        content_area.add(frame)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        image_path = faugus_png
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
        pixbuf = pixbuf.scale_simple(75, 75, GdkPixbuf.InterpType.BILINEAR)
        image = Gtk.Image.new_from_pixbuf(pixbuf)

        label = Gtk.Label(label=_("Are you enjoying Faugus Launcher?"))
        label.set_halign(Gtk.Align.CENTER)

        label2 = Gtk.Label(
            label = _("Please consider donating") + " ❤️"
        )
        label2.set_halign(Gtk.Align.CENTER)

        button_kofi = Gtk.Button(label="Ko-fi")
        button_kofi.connect("clicked", self.on_button_kofi_clicked)
        button_kofi.get_style_context().add_class("kofi")

        button_paypal = Gtk.Button(label="PayPal")
        button_paypal.connect("clicked", self.on_button_paypal_clicked)
        button_paypal.get_style_context().add_class("paypal")

        checkbox = Gtk.CheckButton(label=_("Never show this message again"))
        checkbox.set_halign(Gtk.Align.CENTER)

        box_top.pack_start(image, True, True, 0)
        box_top.pack_start(label, True, True, 0)
        box_top.pack_start(label2, True, True, 0)
        box_top.pack_start(button_kofi, True, True, 0)
        box_top.pack_start(button_paypal, True, True, 0)
        box_top.pack_start(checkbox, True, True, 0)

        button_continue = Gtk.Button(label=_("Continue"))
        button_continue.set_size_request(150, -1)
        button_continue.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        box_bottom.pack_start(button_continue, True, True, 0)

        frame_box.pack_start(box_top, True, True, 0)
        frame_box.pack_start(box_bottom, False, False, 0)

        checkbox_state = False

        def on_dialog_response(dialog, response_id):
            nonlocal checkbox_state
            if response_id == Gtk.ResponseType.OK:
                checkbox_state = checkbox.get_active()
            dialog.destroy()

        dialog.connect("response", on_dialog_response)

        dialog.show_all()
        dialog.run()

        if checkbox_state:
            self.cfg.set_value("show-donate", False)

    def on_button_kofi_clicked(self, widget):
        webbrowser.open("https://ko-fi.com/K3K210EMDU")

    def on_button_paypal_clicked(self, widget):
        webbrowser.open("https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD")

    def show_error_dialog(self, protonpath=None, network_error=False):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_resizable(False)
        dialog.set_icon_from_file(faugus_png)
        subprocess.Popen(["canberra-gtk-play", "-f", faugus_notification])

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

        if network_error:
            label = Gtk.Label(label=_("Internet connection error."))
            label.set_halign(Gtk.Align.CENTER)
            box_top.pack_start(label, True, True, 0)
        else:
            label = Gtk.Label(label=_("%s was not found.") % protonpath)
            label.set_halign(Gtk.Align.CENTER)

            label2 = Gtk.Label(
                label=_("Please install it or use another Proton version.")
            )
            label2.set_halign(Gtk.Align.CENTER)

            box_top.pack_start(label, True, True, 0)
            box_top.pack_start(label2, True, True, 0)

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        box_bottom.pack_start(button_ok, True, True, 0)

        content_area.add(box_top)
        content_area.add(box_bottom)

        dialog.show_all()
        dialog.run()
        dialog.destroy()
        Gtk.main_quit()
        sys.exit()

    def extract_env_from_message(self):
        tokens = shlex.split(self.message, posix=True)
        new_tokens = []

        for token in tokens:
            if "=" in token:
                key, value = token.split("=", 1)

                if key.isidentifier():
                    set_env(key, value)
                    continue

            new_tokens.append(token)

        self.message = " ".join(shlex.quote(t) for t in new_tokens)

    def load_env_from_file(self, filename=envar_dir):
        env_from_file = {}

        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or "=" not in line:
                        continue

                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()

                    os.environ[key] = value
                    env_from_file[key] = value

        except FileNotFoundError:
            pass

        return env_from_file

    def load_config(self):
        self.cfg = ConfigManager()

        self.discrete_gpu = self.cfg.config.get('discrete-gpu', 'False') == 'True'
        self.splash_disable = self.cfg.config.get('splash-disable', 'False') == 'True'
        self.default_runner = self.cfg.config.get('default-runner', '')
        self.lossless_location = self.cfg.config.get('lossless-location', '')
        self.default_prefix = self.cfg.config.get('default-prefix', '')
        self.enable_logging = self.cfg.config.get('enable-logging', 'False') == 'True'
        self.wayland_driver = self.cfg.config.get('wayland-driver', 'False') == 'True'
        self.enable_hdr = self.cfg.config.get('enable-hdr', 'False') == 'True'
        self.enable_wow64 = self.cfg.config.get('enable-wow64', 'False') == 'True'
        self.language = self.cfg.config.get('language', '')
        self.show_donate = self.cfg.config.get('show-donate', 'False') == 'True'
        self.playtime = int(self.cfg.config.get("playtime", 0))

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
        self.label.set_margin_bottom(20)

        grid.attach(self.label, 0, 1, 1, 1)

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
        try:
            source.set_encoding(None)
        except Exception:
            pass

        if self.enable_logging:
            log_dir = f"{logs_dir}/{self.log_dir}"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            if not hasattr(self, "_log_file_cleaned"):
                with open(f"{log_dir}/umu.log", "w") as log_file:
                    log_file.write("")
                self._log_file_cleaned = True

        def remove_ansi_escape(text):
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            return ansi_escape.sub('', text)

        raw = source.readline()
        if raw:
            if isinstance(raw, bytes):
                line = raw.decode("utf-8", errors="ignore")
            else:
                line = raw

            clean_line = remove_ansi_escape(line).strip()

            if self.enable_logging:
                with open(f"{log_dir}/umu.log", "a", encoding="utf-8") as log_file:
                    log_file.write(clean_line + "\n")
                    log_file.flush()

            self.check_game_output(clean_line)

            if "libgamemode.so.0" in clean_line or "libgamemodeauto.so.0" in clean_line or "libgamemode.so" in clean_line:
                return True

            if os.environ.get("GAMEID") == "winetricks-gui":
                self.append_to_text_view(clean_line)
            else:
                print(line, end="")

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
        if "Downloading UMU-Proton" in clean_line:
            self.label.set_text(_("Downloading UMU-Proton..."))
        if "Downloading steamrt3 (latest)" in clean_line:
            self.label.set_text(_("Downloading Steam Runtime..."))
        if "SteamLinuxRuntime_sniper.tar.xz" in clean_line:
            self.label.set_text(_("Extracting Steam Runtime..."))
        if "Extracting UMU-Proton" in clean_line:
            self.label.set_text(_("Extracting UMU-Proton..."))
        if "UMU-Proton is up to date" in clean_line:
            self.label.set_text(_("UMU-Proton is up to date"))
        if "steamrt3 is up to date" in clean_line:
            self.label.set_text(_("Steam Runtime is up to date"))
        if "->" in clean_line and "GE-Proton" in clean_line:
            self.label.set_text(_("GE-Proton is up to date"))
        if "->" in clean_line and "UMU-Proton" in clean_line:
            self.label.set_text(_("UMU-Proton is up to date"))
        if "mtree is OK" in clean_line:
            self.label.set_text(_("Steam Runtime is up to date"))

        if "Downloading GE-Proton" in clean_line:
            self.label.set_text(_("Downloading GE-Proton..."))
        if "Extracting GE-Proton" in clean_line:
            self.label.set_text(_("Extracting GE-Proton..."))
        if "GE-Proton is up to date" in clean_line:
            self.label.set_text(_("GE-Proton is up to date"))
        if "Downloading Proton-EM" in clean_line:
            self.label.set_text(_("Downloading Proton-EM..."))
        if "Extracting Proton-EM" in clean_line:
            self.label.set_text(_("Extracting Proton-EM..."))
        if "Proton-EM is up to date" in clean_line:
            self.label.set_text(_("Proton-EM is up to date"))

        if "network error" in clean_line:
            self.show_error_dialog(network_error=True)

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
        import psutil
        def kill_child_proc():

            if self.process and self.process.poll() is None:
                try:
                    parent = psutil.Process(self.process.pid)
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass

        end_time = time.time()
        runtime = int(end_time - getattr(self, "start_time", end_time))

        self.playtime = int(self.cfg.config.get("playtime", 0))
        self.cfg.set_value("playtime", self.playtime + runtime)

        game_id = os.environ.get("GAMEID")

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
        kill_child_proc()

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
    prevent_sleep = game.get("prevent_sleep", "")
    addapp_checkbox = game.get("addapp_checkbox", "")
    lossless_enabled = game.get("lossless_enabled", "")
    lossless_multiplier = game.get("lossless_multiplier", "")
    lossless_flow = game.get("lossless_flow", "")
    lossless_performance = game.get("lossless_performance", "")
    lossless_hdr = game.get("lossless_hdr", "")
    lossless_present = game.get("lossless_present", "")

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
        command_parts.append(f"LOG_DIR='{gameid}'")
    if disable_hidraw:
        command_parts.append("PROTON_DISABLE_HIDRAW=1")
    if prevent_sleep:
        command_parts.append("PREVENT_SLEEP=1")
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
            command_parts.append(f"PROTONPATH='{runner}'")
    else:
        command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
    if lossless_enabled:
        command_parts.append("LSFG_LEGACY=1") # Deprecated in LSFG-VK v2.0
        command_parts.append("LSFGVK_ENV=1")
        if lossless_multiplier:
            command_parts.append(f"LSFG_MULTIPLIER={lossless_multiplier}") # Deprecated in LSFG-VK v2.0
            command_parts.append(f"LSFGVK_MULTIPLIER={lossless_multiplier}")
        if lossless_flow:
            command_parts.append(f"LSFG_FLOW_SCALE={lossless_flow/100}") # Deprecated in LSFG-VK v2.0
            command_parts.append(f"LSFGVK_FLOW_SCALE={lossless_flow/100}")
        if lossless_performance:
            command_parts.append("LSFG_PERFORMANCE_MODE=1") # Deprecated in LSFG-VK v2.0
            command_parts.append("LSFGVK_PERFORMANCE_MODE=1")
        else:
            command_parts.append("LSFG_PERFORMANCE_MODE=0") # Deprecated in LSFG-VK v2.0
            command_parts.append("LSFGVK_PERFORMANCE_MODE=0")
        if lossless_hdr: # HDR mode env is deprecated in LSFG-VK v2.0
            command_parts.append("LSFG_HDR_MODE=1")
        else:
            command_parts.append("LSFG_HDR_MODE=0")
        if lossless_present: # Experimental present mode env is deprecated in LSFG-VK v2.0
            command_parts.append(f"LSFG_EXPERIMENTAL_PRESENT_MODE={lossless_present}")
    if launch_arguments:
        command_parts.append(launch_arguments)
    if gamemode:
        command_parts.append("gamemoderun")
    if mangohud:
        command_parts.append("mangohud")

    if runner != "Steam":
        command_parts.append(f"'{umu_run}'")

    if addapp_checkbox == "addapp_enabled":
        command_parts.append(shlex.quote(addapp_bat))
    else:
        if runner != "Steam":
            command_parts.append(shlex.quote(path))
        else:
            steam_arguments = "-nobigpicture -nochatui -nofriendsui -silent -applaunch"
            if IS_FLATPAK:
                if IS_STEAM_FLATPAK:
                    command_parts.append(f"flatpak-spawn --host flatpak run com.valvesoftware.Steam {steam_arguments} {path}")
                else:
                    command_parts.append(f"flatpak-spawn --host steam {steam_arguments} {path}")
            else:
                if IS_STEAM_FLATPAK:
                    command_parts.append(f"flatpak run com.valvesoftware.Steam {steam_arguments} {path}")
                else:
                    command_parts.append(f"steam {steam_arguments} {path}")

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

def update_games_and_config():
    if os.path.exists(games_dir):
        try:
            with open(games_dir, "r", encoding="utf-8") as f:
                games = json.load(f)
        except json.JSONDecodeError:
            games = []

        changed = False

        for game in games:
            title = game.get("title", "")
            if title:
                formatted = format_title(title)
                if game.get("gameid") != formatted:
                    game["gameid"] = formatted
                    changed = True

            if game.get("playtime", "") == "":
                game["playtime"] = 0
                changed = True

            runner = game.get("runner")
            if runner == "Proton-EM":
                game["runner"] = "Proton-EM Latest"
                changed = True
            elif runner == "GE-Proton":
                game["runner"] = "Proton-GE Latest"
                changed = True
            elif runner == "Steam":
                for key in (
                    "mangohud",
                    "gamemode",
                    "disable_hidraw",
                    "addapp_checkbox",
                    "prevent_sleep",
                ):
                    if game.get(key, "") != "":
                        game[key] = ""
                        changed = True

        if changed:
            with open(games_dir, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=4, ensure_ascii=False)

    config_path = Path(PathManager.user_config("faugus-launcher/config.ini"))
    if not config_path.exists():
        return

    lines = config_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    changed = False

    for line in lines:
        if line.startswith("default-runner="):
            value = line.split("=", 1)[1].strip('"')

            if value == "GE-Proton":
                line = 'default-runner="Proton-GE Latest"'
                changed = True
            elif value == "Proton-EM":
                line = 'default-runner="Proton-EM Latest"'
                changed = True

        new_lines.append(line)

    if changed:
        config_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

def is_apple_silicon():
    path = "/proc/device-tree/compatible"

    if not os.path.exists(path):
        return False

    try:
        with open(path, "rb") as f:
            dtcompat = f.read().decode('utf-8', errors='ignore')

            if "apple,arm-platform" in dtcompat:
                return True
            else:
                return False
    except:
        return False

def main():
    if is_apple_silicon() and 'FAUGUS_MUVM' not in os.environ:
        muvm_path = shutil.which('muvm')
        if muvm_path:
            env = os.environ.copy()
            args = [muvm_path, "-i", "-e", "FAUGUS_MUVM=1", sys.executable, os.path.abspath(__file__)]
            os.execvpe(muvm_path, args + sys.argv[1:], env)

    apply_dark_theme()
    update_games_and_config()

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
