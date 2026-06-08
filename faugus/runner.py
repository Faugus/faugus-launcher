#!/usr/bin/env python3

import gi
import sys
import subprocess
import argparse
import re
import json
import time
import shlex
import signal
import fcntl

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, Gdk, GLib
from threading import Thread
from faugus.config_manager import *
from faugus.utils import *
from faugus.ea_fix import *
from faugus.steam_setup import IS_STEAM_FLATPAK

if IS_FLATPAK:
    faugus_png = PathManager.get_icon('io.github.Faugus.faugus-launcher.svg')
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
else:
    faugus_png = PathManager.get_icon('faugus-launcher.svg')
    GLib.set_prgname("faugus-launcher")

eac_dir = PathManager.user_config("faugus-launcher/components/eac")
be_dir = PathManager.user_config("faugus-launcher/components/be")
os.makedirs(compatibility_dir, exist_ok=True)

_ = setup_gettext('faugus-run')

_env_set = set()
def set_env(key, value):
    os.environ[key] = value
    _env_set.add(key)

class FaugusRun(HiDpiMixin):
    def __init__(self, message, command=None):
        self.message = message
        self.command = command
        self.process = None
        self.splash_window = None
        self.log_window = None
        self.text_view = None
        self.proton_latest = None

        self.load_config()
        signal.signal(signal.SIGUSR1, self.on_process_exit)

    def get_scale_factor(self):
        if hasattr(self, "_scale_widget") and self._scale_widget:
            return self._scale_widget.get_scale_factor()
        return 1

    def run(self):
        def run_process():
            self.start_process()

        self.process_thread = Thread(target=run_process)

        def start_thread():
            self.process_thread.start()
            return False

        GLib.idle_add(start_thread)
        Gtk.main()

        self.process_thread.join()
        sys.exit(0)

    def start_process(self):
        if self.show_donate:
            if self.playtime >= 7200:
                current_month = GLib.DateTime.new_now_local().format("%Y-%m")

                if self.cfg.config.get("donate-last", "") != current_month:
                    self.show_donate_dialog()
                    self.cfg.set_value("donate-last", current_month)
                    self.cfg.save_config()

        if not self.splash_disable and not self.disable_updates:
            GLib.idle_add(self.show_splash)

        set_env("PROTON_EAC_RUNTIME", eac_dir)
        set_env("PROTON_BATTLEYE_RUNTIME", be_dir)

        if self.discrete_gpu:
            set_env("DRI_PRIME", "1")
            subprocess.run(
                    ["vulkaninfo", "--summary"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False
                )
        if self.wayland_driver:
            set_env("PROTON_ENABLE_WAYLAND", "1")
            if self.enable_hdr:
                set_env("DXVK_HDR", "1")
        if self.enable_wow64:
            set_env("PROTON_USE_WOW64", "1")

        self.extract_env_from_message()

        if self.command == "winetricks":
            GLib.idle_add(self.show_log_window)

        if os.environ.get("PROTONPATH") == "Steam":
            subprocess.Popen(self.message, shell=True)

            def update_ui():
                if self.splash_window:
                    self.label.set_text(_("Starting Steam game..."))
                return False

            GLib.idle_add(update_ui)

            def close_app():
                Gtk.main_quit()
                sys.exit()
                return False

            GLib.timeout_add(5000, close_app)
            return

        self.start_time = time.time()

        # LSFG_LEGACY env is deprecated in LSFG-VK 2.0
        if os.environ.get("LSFG_LEGACY") or os.environ.get("LSFGVK-ENV"):
            if self.lossless_location:
                set_env("LSFG_DLL_PATH", self.lossless_location) # Deprecated in LSFG-VK v2.0
                set_env("LSFGVK_DLL_PATH", self.lossless_location)

        if self.enable_logging:
            self.log_dir = os.environ.get("LOG_DIR") or "default"

        if not os.environ.get("PROTONPATH") == "umu-sniper":
            if self.enable_logging:
                set_env("UMU_LOG", "1")
                set_env("PROTON_LOG_DIR", f"{logs_dir}/{self.log_dir}")
                set_env("PROTON_LOG", "1")

        if not os.environ.get("WINEPREFIX"):
            if not os.environ.get("PROTONPATH") == "umu-sniper":
                set_env("WINEPREFIX", f"{self.default_prefix}/default")
                if self.default_runner == "Proton-CachyOS (System)":
                    set_env("PROTONPATH", f"{proton_cachyos}")
                else:
                    set_env("PROTONPATH", f"{self.default_runner}")

        if not os.environ.get("GAMEID"):
            set_env("PROTONFIXES_DISABLE", "1")

        protonpath = os.environ.get("PROTONPATH")
        if protonpath and protonpath != "Proton-GE Latest" and protonpath != "Proton-EM Latest" and protonpath != "Proton-CachyOS Latest" and protonpath != "DW-Proton Latest" and protonpath != "umu-sniper":
            if protonpath == "Proton-CachyOS (System)" and not os.path.exists(proton_cachyos):
                self.close_splash_window()
                self.show_error_dialog(protonpath)
            if protonpath == "Linux-Native":
                pass
            if protonpath == "Steam":
                pass
            else:
                protonpath_path = compatibility_dir / protonpath
                if not protonpath_path.is_dir():
                    self.close_splash_window()
                    self.show_error_dialog(protonpath)
        if protonpath == "Proton-EM Latest":
            self.proton_latest = "--em"
            steam_compat_dir = compatibility_dir / "Proton-EM Latest"
            self.proton_exists = steam_compat_dir.is_dir()

        if protonpath == "Proton-GE Latest":
            self.proton_latest = "--ge"
            steam_compat_dir = compatibility_dir / "Proton-GE Latest"
            self.proton_exists = steam_compat_dir.is_dir()

        if protonpath == "Proton-CachyOS Latest":
            self.proton_latest = "--cachyos"
            steam_compat_dir = compatibility_dir / "Proton-CachyOS Latest"
            self.proton_exists = steam_compat_dir.is_dir()

        if protonpath == "DW-Proton Latest":
            self.proton_latest = "--dw"
            steam_compat_dir = compatibility_dir / "DW-Proton Latest"
            self.proton_exists = steam_compat_dir.is_dir()

        self.components_exists = (
            os.path.exists(eac_dir) and
            os.path.exists(be_dir) and
            os.path.exists(umu_run)
        )

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

        set_env("UMU_USE_STEAM", "1")

        self.lock_prefix()
        self.execute_final_command()

    def lock_prefix(self):
        prefix = os.environ.get("WINEPREFIX")

        if not prefix:
            return

        os.makedirs(prefix, exist_ok=True)
        lock_file = os.path.join(prefix, ".faugus.lock")
        self.lock_fd = open(lock_file, "w")

        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.has_lock = True

        except BlockingIOError:
            self.has_lock = False
            set_env("UMU_CONTAINER_NSENTER", "1")

    def execute_final_command(self):
        import gc

        def start_and_watch(cmd, is_game=False):
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=8192, text=True
            )

            def watch_stream(stream):
                for line in iter(stream.readline, ""):
                    clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line).strip()

                    if self.enable_logging:
                        log_path = Path(logs_dir) / self.log_dir
                        log_path.mkdir(parents=True, exist_ok=True)
                        with open(log_path / "umu.log", "a", encoding="utf-8") as f:
                            f.write(f"{clean_line}\n")

                    self.check_game_output(clean_line)

                    if os.environ.get("GAMEID") == "winetricks-gui":
                        GLib.idle_add(self.append_to_text_view, clean_line)
                    else:
                        print(line, end="")
                stream.close()

            threads = [
                Thread(target=watch_stream, args=(process.stdout,), daemon=True),
                Thread(target=watch_stream, args=(process.stderr,), daemon=True)
            ]
            for t in threads: t.start()

            if is_game:
                self.process = process
                GLib.child_watch_add(GLib.PRIORITY_DEFAULT, process.pid, self.on_process_exit)
                Thread(target=self._watch_game_process, daemon=True).start()
            else:
                process.wait()
                for t in threads: t.join(timeout=1)

        popen_prefix = []
        if os.environ.get("PREVENT_SLEEP"):
            try:
                import dbus
                iface = dbus.Interface(dbus.SessionBus().get_object("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"), "org.freedesktop.portal.Inhibit")
                iface.Inhibit("", 8, {"reason": "Game is running"})
            except:
                systemd_inhibit = PathManager.find_binary("systemd-inhibit")
                if not IS_FLATPAK and os.path.exists("/run/dbus/system_bus_socket") and systemd_inhibit:
                    popen_prefix = [systemd_inhibit, "--what=sleep", "--why=Game is running", "--mode=block"]

        cmds_to_run = []
        is_sniper = os.environ.get("PROTONPATH") == "umu-sniper"

        if not is_sniper:
            force_off = os.environ.get("FAUGUS_DISABLE_UPDATES") or self.disable_updates
            if force_off: set_env("UMU_RUNTIME_UPDATE", "0")

            if self.proton_latest and (not force_off or not self.proton_exists):
                cmds_to_run.append([sys.executable, "-m", "faugus.proton_downloader", self.proton_latest])
            if not force_off or not self.components_exists:
                cmds_to_run.append([sys.executable, "-m", "faugus.components"])

        for cmd in cmds_to_run:
            start_and_watch(cmd)

        if cmds_to_run: gc.collect()

        game_cmd = popen_prefix + shlex.split(self.message)
        start_and_watch(game_cmd, is_game=True)

    def show_donate_dialog(self):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_decorated(False)
        dialog.set_resizable(False)
        play_notification_sound()

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
        self._scale_widget = dialog
        surface = self.new_surface_from_image(image_path, 75, 75)
        image = Gtk.Image.new_from_surface(surface)

        label = Gtk.Label(label=_("Are you enjoying Faugus Launcher?"))
        label.set_halign(Gtk.Align.CENTER)

        label2 = Gtk.Label(
            label = _("Please consider donating") + " ❤️"
        )
        label2.set_halign(Gtk.Align.CENTER)

        button_kofi = Gtk.Button(label="Ko-fi")
        button_kofi.connect("clicked", on_button_kofi_clicked)
        button_kofi.get_style_context().add_class("kofi")

        button_paypal = Gtk.Button(label="PayPal")
        button_paypal.connect("clicked", on_button_paypal_clicked)
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
            self.cfg.save_config()

    def show_error_dialog(self, protonpath=None, network_error=False):
        dialog = Gtk.Dialog(title="Faugus Launcher")
        dialog.set_resizable(False)
        play_notification_sound()

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
        self.show_donate = self.cfg.config.get('show-donate', 'False') == 'True'
        self.playtime = int(self.cfg.config.get("playtime", 0))
        self.disable_updates = self.cfg.config.get('disable-updates', 'False') == 'True'

    def show_splash(self):
        self.splash_window = Gtk.Window(title="Faugus Launcher")
        self.splash_window.set_wmclass("faugus-launcher", "faugus-launcher")
        self.splash_window.set_decorated(False)
        self.splash_window.set_resizable(False)
        self.splash_window.set_default_size(280, -1)

        frame = Gtk.Frame()
        frame.set_label_align(0.5, 0.5)
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        grid = Gtk.Grid()
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)
        frame.add(grid)

        game_icon = os.environ.get("SPLASHICON")
        if game_icon and os.path.exists(game_icon):
            image_path = game_icon
        else:
            image_path = faugus_png
        self._scale_widget = self.splash_window
        surface = self.new_surface_from_image(image_path, 75, 75)
        image = Gtk.Image.new_from_surface(surface)
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

        self.splash_window.add(frame)
        self.splash_window.show_all()

        while Gtk.events_pending():
            Gtk.main_iteration()

    def show_log_window(self):
        self.log_window = Gtk.Window(title="Winetricks Logs")
        self.log_window.set_default_size(600, 400)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        scrolled_window.add(self.text_view)
        self.log_window.add(scrolled_window)

        self.log_window.connect("delete-event", self.on_log_window_delete_event)
        self.log_window.show_all()

    def check_game_output(self, clean_line):
        if "Downloading upscaler file" in clean_line:
            return False
        def update_ui():
            if (
                "Downloading" in clean_line
                or "Updating BattlEye..." in clean_line
                or "Updating Easy Anti-Cheat..." in clean_line
                or "Updating UMU-Launcher..." in clean_line
            ):
                if self.splash_window is None:
                    self.show_splash()

            component = None

            if "Components are up to date" in clean_line:
                if self.splash_window:
                    self.label.set_text(_("Components are up to date"))
                return False

            if "UMU-Launcher" in clean_line:
                component = "UMU-Launcher"
            elif "BattlEye" in clean_line:
                component = "BattlEye"
            elif "Easy Anti-Cheat" in clean_line:
                component = "Easy Anti-Cheat"
            elif "UMU-Proton" in clean_line:
                component = "UMU-Proton"
            elif "GE-Proton" in clean_line:
                component = "GE-Proton"
            elif "Proton-EM" in clean_line:
                component = "Proton-EM"
            elif "Proton-CachyOS" in clean_line:
                component = "Proton-CachyOS"
            elif "DW-Proton" in clean_line:
                component = "DW-Proton"
            elif "steamrt3" in clean_line or "steamrt4" in clean_line or "SteamLinuxRuntime" in clean_line:
                component = "Steam Runtime"

            if component and self.splash_window:
                if "Updating" in clean_line:
                    self.label.set_text(_("Updating") + f" {component}...")
                elif "Downloading" in clean_line:
                    self.label.set_text(_("Downloading") + f" {component}...")
                elif "Extracting" in clean_line or "SteamLinuxRuntime_sniper.tar.xz" in clean_line:
                    self.label.set_text(_("Extracting") + f" {component}...")
                elif (
                    "is up to date" in clean_line
                    or "mtree is OK" in clean_line
                    or ("->" in clean_line and component in clean_line)
                ):
                    self.label.set_text(f"{component} " + _("is up to date"))
            return False

        GLib.idle_add(update_ui)

    def _watch_game_process(self):
        import psutil

        try:
            parent = psutil.Process(self.process.pid)
        except:
            return

        ignore = ("bash", "sh", "python")

        while True:
            try:
                for child in parent.children(recursive=True):
                    name = child.name().lower()

                    if any(x in name for x in ignore):
                        continue

                    GLib.idle_add(self.close_splash_window)
                    return
            except:
                return
            time.sleep(0.5)

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

    def close_splash_window(self):
        if self.splash_window:
            self.splash_window.destroy()
            self.splash_window = None

    def close_log_window(self):
        if self.log_window:
            self.log_window.destroy()
            self.log_window = None

    def on_log_window_delete_event(self, widget, event):
        return True

    def show_regedit_confirmation(self):
        parts = self.message.split()
        if parts:
            last_part = parts[-1].strip('"')

            if last_part.endswith(".reg"):
                dialog = Gtk.Dialog(title="Faugus Launcher", modal=True)
                dialog.set_resizable(False)
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
        self.cfg.save_config()
        self.release_prefix()

        game_id = os.environ.get("FAUGUSID")

        if game_id and os.path.exists(games_json):
            try:
                with open(games_json, "r", encoding="utf-8") as f:
                    games = json.load(f)

                for game in games:
                    if game.get("gameid") == game_id:
                        old_time = game.get("playtime", 0)
                        game["playtime"] = old_time + runtime
                        break

                with open(games_json, "w", encoding="utf-8") as f:
                    json.dump(games, f, indent=4)

            except Exception as e:
                pass

        GLib.idle_add(self.close_splash_window)
        GLib.idle_add(self.close_log_window)
        GLib.idle_add(self.show_regedit_confirmation)
        GLib.idle_add(Gtk.main_quit)
        kill_child_proc()

        return False

    def release_prefix(self):
        if hasattr(self, "lock_fd"):
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                self.lock_fd.close()
            except:
                pass

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
    icon = game.get("icon", "")

    if lossless_performance:
        lossless_performance = 1
    else:
        lossless_performance = 0
    if lossless_hdr:
        lossless_hdr = 1
    else:
        lossless_hdr = 0

    if gameid == "ea-app":
        path = update_ea_path(prefix)

    command_parts = []

    if icon:
        command_parts.append(f"SPLASHICON={icon}")
    if gameid:
        command_parts.append(f"LOG_DIR='{gameid}'")
        command_parts.append(f"FAUGUSID={gameid}")
    if disable_hidraw:
        command_parts.append("PROTON_DISABLE_HIDRAW=1")
    if prevent_sleep:
        command_parts.append("PREVENT_SLEEP=1")
    if protonfix:
        command_parts.append(f"GAMEID={protonfix}")
    if runner:
        if runner == "Linux-Native":
            command_parts.append('PROTONPATH=umu-sniper')
        elif runner == "Proton-CachyOS (System)":
            command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
            command_parts.append(f"PROTONPATH={proton_cachyos}")
        else:
            command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
            command_parts.append(f"PROTONPATH='{runner}'")
    else:
        command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
    command_parts.extend(build_lossless_env(lossless_enabled, lossless_multiplier, lossless_flow, lossless_performance, lossless_hdr, lossless_present))
    if launch_arguments:
        command_parts.append(os.path.expanduser(launch_arguments))
    if gamemode and os.path.exists(gamemoderun):
        command_parts.append("gamemoderun")
    if mangohud and os.path.exists(mangohud_dir):
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
    if not os.path.exists(games_json):
        return None

    try:
        with open(games_json, "r", encoding="utf-8") as f:
            games = json.load(f)
    except json.JSONDecodeError:
        return None

    for game in games:
        if game.get("gameid") == gameid:
            return game

    return None

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
        import shutil
        muvm_path = shutil.which('muvm')
        if muvm_path:
            env = os.environ.copy()
            args = [muvm_path, "-i", "-e", "FAUGUS_MUVM=1", sys.executable, os.path.abspath(__file__)]
            os.execvpe(muvm_path, args + sys.argv[1:], env)

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
        FaugusRun(launch_options, None).run()
    else:
        FaugusRun(args.message, args.command).run()

def update_games_json():
    if not os.path.exists(games_json):
        return

    try:
        with open(games_json, "r", encoding="utf-8") as f:
            games = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    changed = False

    icons_dir = PathManager.user_config('faugus-launcher/icons')

    for game in games:
        if game.get("runner") == "Proton-CachyOS":
            game["runner"] = "Proton-CachyOS (System)"
            changed = True

        if "favorite" in game:
            if game["favorite"] == True:
                game["category"] = False

            game.pop("favorite")
            changed = True

        game_id = game.get("gameid")

        if game_id:
            new_icon_path = os.path.join(icons_dir, f"{game_id}.ico")

            if game.get("icon") != new_icon_path:
                game["icon"] = new_icon_path
                changed = True

    if changed:
        with open(games_json, "w", encoding="utf-8") as f:
            json.dump(games, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    update_games_json()
    main()
