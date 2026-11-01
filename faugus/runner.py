import gi
import sys
import subprocess
import argparse
import re
import time
import shlex
import signal
import warnings
import socket
import struct
import json
import uuid
from datetime import datetime

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib
from threading import Thread, Event
from faugus.config_manager import *
from faugus.utils import *
from faugus.ea_fix import *
from faugus.steam_setup import IS_STEAM_FLATPAK
from faugus.migration import fix_legacy_shortcut_icons

GLib.set_prgname("io.github.Faugus.faugus-launcher")

os.makedirs(COMPATIBILITY_DIR, exist_ok=True)
fix_legacy_shortcut_icons()

_ = setup_gettext('faugus-launcher')

_env_set = set()
_child_only_env = {}


def set_env(key, value):
    os.environ[key] = value
    _env_set.add(key)


def set_child_env(key, value):
    _child_only_env[key] = value


def child_env():
    env = {**os.environ, **_child_only_env}
    env.pop("VK_LOADER_LAYERS_DISABLE", None)
    return env
 
def warm_up_gpu():
    import ctypes

    try:
        vulkan = ctypes.CDLL("libvulkan.so.1")

        class VkInstanceCreateInfo(ctypes.Structure):
            _fields_ = [
                ("sType", ctypes.c_int),
                ("pNext", ctypes.c_void_p),
                ("flags", ctypes.c_uint32),
                ("pApplicationInfo", ctypes.c_void_p),
                ("enabledLayerCount", ctypes.c_uint32),
                ("ppEnabledLayerNames", ctypes.c_void_p),
                ("enabledExtensionCount", ctypes.c_uint32),
                ("ppEnabledExtensionNames", ctypes.c_void_p),
            ]

        create_info = VkInstanceCreateInfo(
            sType=1, pNext=None, flags=0, pApplicationInfo=None,
            enabledLayerCount=0, ppEnabledLayerNames=None,
            enabledExtensionCount=0, ppEnabledExtensionNames=None
        )

        instance = ctypes.c_void_p()
        if vulkan.vkCreateInstance(ctypes.byref(create_info), None, ctypes.byref(instance)) != 0:
            return

        count = ctypes.c_uint32(0)
        vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None)
        vulkan.vkDestroyInstance(instance, None)
    except OSError:
        pass


STATUS_LINE = re.compile(
    "Downloading|Updating|Components are up to date|UMU-Launcher|BattlEye|Easy Anti-Cheat|"
    "GE-Proton|Proton-CachyOS|DW-Proton|Proton-Wineland|steamrt3|steamrt4|SteamLinuxRuntime"
)


DISCORD_FALLBACK_CLIENT_ID = "1566097048770707516"
DISCORD_DETECTABLE_URL = "https://discord.com/api/v10/applications/detectable"
DISCORD_DETECTABLE_CACHE = os.path.join(FAUGUS_LAUNCHER_SHARE_DIR, "discord-detectable.json")
DISCORD_IPC_DIRS = (
    "app/com.discordapp.Discord",
    "app/com.discordapp.DiscordCanary",
    "app/dev.vencord.Vesktop",
    ".flatpak/com.discordapp.Discord/xdg-run",
    ".flatpak/dev.vencord.Vesktop/xdg-run",
    "snap.discord",
    "snap.discord-canary",
)


def discord_frame(opcode, payload):
    data = json.dumps(payload).encode()
    return struct.pack("<II", opcode, len(data)) + data


def discord_connect(client_id):
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime_dir:
        return None
    for directory in DISCORD_IPC_DIRS:
        for index in range(10):
            path = os.path.join(runtime_dir, directory, f"discord-ipc-{index}")
            if not os.path.exists(path):
                continue
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(3)
            try:
                sock.connect(path)
                sock.sendall(discord_frame(0, {"v": 1, "client_id": client_id}))
                if not sock.recv(8):
                    raise OSError
                sock.recv(65536)
                return sock
            except OSError:
                sock.close()
    return None


def discord_load_detectable():
    try:
        if time.time() - os.path.getmtime(DISCORD_DETECTABLE_CACHE) < 7 * 86400:
            with open(DISCORD_DETECTABLE_CACHE, encoding="utf-8") as f:
                return json.load(f)
    except (OSError, ValueError):
        pass
    try:
        import urllib.request
        request = urllib.request.Request(DISCORD_DETECTABLE_URL, headers={"User-Agent": "Faugus-Launcher"})
        with urllib.request.urlopen(request, timeout=15) as response:
            apps = json.load(response)
    except (OSError, ValueError):
        try:
            with open(DISCORD_DETECTABLE_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}
    index = {}
    for app in apps:
        for exe in app.get("executables", []):
            if exe.get("os") not in ("win32", "linux"):
                continue
            name = exe["name"].lower().lstrip(">")
            index.setdefault(name.rsplit("/", 1)[-1], []).append(
                [name, app["id"], app["name"], bool(exe.get("is_launcher"))]
            )
    try:
        with open(DISCORD_DETECTABLE_CACHE, "w", encoding="utf-8") as f:
            json.dump(index, f)
    except OSError:
        pass
    return index


def discord_find_game(index):
    import psutil
    found = None
    for proc in psutil.process_iter(["name", "cmdline"]):
        cmdline = proc.info["cmdline"] or []
        candidates = [proc.info["name"] or ""]
        if cmdline:
            candidates.append(cmdline[0])
        for candidate in candidates:
            normalized = candidate.replace("\\", "/").lower()
            entries = index.get(normalized.rsplit("/", 1)[-1], [])
            if not entries:
                continue
            paths = [normalized]
            if "/" not in normalized:
                try:
                    paths.append(proc.cwd().lower() + "/" + normalized)
                except (psutil.Error, OSError):
                    pass
            for suffix, app_id, name, launcher in entries:
                if any(path == suffix or path.endswith("/" + suffix) for path in paths):
                    if found is None or (found[2] and not launcher):
                        found = [app_id, name, launcher]
    return found


def apply_runner_theme(cfg):
    theme_engine = cfg.config.get('theme-engine', 'adwaita').strip('"')
    apply_theme_engine(theme_engine)
    apply_interface_customization(
        cfg.config.get('interface-theme', 'system'),
        cfg.get_accent_color(),
        theme_engine,
    )


class FaugusSplash(HiDpiMixin):
    def __init__(self, image_path):
        apply_runner_theme(ConfigManager())
        load_frame_css()

        self.pulse_source = None
        self.window = Gtk.Window(title="Faugus")
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(280, 10)

        frame = Gtk.Frame()
        frame.set_label_align(0.5)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.CENTER)
        frame.set_child(box)

        image = new_icon(self.new_texture_from_image(image_path, 75, 75))
        image.set_margin_top(20)
        image.set_margin_start(20)
        image.set_margin_end(20)
        image.set_margin_bottom(20)
        box.append(image)

        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        status_box.set_margin_start(20)
        status_box.set_margin_end(20)
        status_box.set_margin_bottom(20)

        self.label = Gtk.Label()
        status_box.append(self.label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_size_request(240, -1)
        self.progress_bar.set_visible(False)
        status_box.append(self.progress_bar)

        box.append(status_box)

        self.window.set_child(frame)
        self.window.present()

    def run(self):
        self.loop = GLib.MainLoop()
        Thread(target=self.read_commands, daemon=True).start()
        self.loop.run()

    def read_commands(self):
        for line in sys.stdin:
            GLib.idle_add(self.handle_command, line.rstrip("\n"))
        GLib.idle_add(self.loop.quit)

    def handle_command(self, line):
        name, _sep, value = line.partition(" ")
        if name == "LABEL":
            self.label.set_text(value)
        elif name == "FRACTION":
            self.stop_pulse()
            self.progress_bar.set_visible(True)
            self.progress_bar.set_fraction(float(value))
        elif name == "PULSE":
            self.progress_bar.set_visible(True)
            if self.pulse_source is None:
                self.pulse_source = GLib.timeout_add(100, self.pulse_progress)
        elif name == "HIDE":
            self.stop_pulse()
            self.progress_bar.set_visible(False)
        return False

    def pulse_progress(self):
        self.progress_bar.pulse()
        return True

    def stop_pulse(self):
        if self.pulse_source is not None:
            GLib.source_remove(self.pulse_source)
            self.pulse_source = None


class FaugusDonate(HiDpiMixin):
    def __init__(self):
        apply_runner_theme(ConfigManager())
        load_frame_css()
        self.loop = GLib.MainLoop()

        dialog = self.dialog = Gtk.Dialog(title="Faugus")
        dialog.set_default_size(10, 10)
        hide_dialog_action_area(dialog)
        dialog.set_decorated(False)
        dialog.set_resizable(False)
        play_ui_sound("confirm")

        add_css_once("donate_dialog", """
        .paypal {
            color: white;
            background: #001C64;
        }
        .kofi {
            color: white;
            background: #1AC0FF;
        }
        """, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        content_area = dialog.get_content_area()
        content_area.set_halign(Gtk.Align.CENTER)
        content_area.set_valign(Gtk.Align.CENTER)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)

        frame = Gtk.Frame()
        frame.set_label_align(0.5)
        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        frame.set_child(frame_box)
        content_area.append(frame)

        box_top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_top.set_margin_start(20)
        box_top.set_margin_end(20)
        box_top.set_margin_top(20)
        box_top.set_margin_bottom(20)

        texture = self.new_texture_from_image(FAUGUS_PNG_RASTER, 75, 75)
        image = new_icon(texture)

        label = Gtk.Label(label=_("Are you enjoying Faugus?"))
        label.set_halign(Gtk.Align.CENTER)

        label2 = Gtk.Label(
            label = _("Please consider donating") + " ❤️"
        )
        label2.set_halign(Gtk.Align.CENTER)

        button_kofi, button_paypal = make_donate_buttons()

        checkbox = Gtk.CheckButton(label=_("Never show this message again"))
        checkbox.set_halign(Gtk.Align.CENTER)

        box_top.append(image)
        box_top.append(label)
        box_top.append(label2)
        box_top.append(button_kofi)
        box_top.append(button_paypal)
        box_top.append(checkbox)

        button_continue = Gtk.Button(label=_("Continue"))
        button_continue.set_size_request(150, -1)
        button_continue.set_hexpand(True)
        button_continue.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))

        box_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box_bottom.set_margin_start(10)
        box_bottom.set_margin_end(10)
        box_bottom.set_margin_bottom(10)
        box_bottom.append(button_continue)

        frame_box.append(box_top)
        frame_box.append(box_bottom)

        def on_dialog_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK and checkbox.get_active():
                print("checked", flush=True)
            self.loop.quit()

        dialog.connect("response", on_dialog_response)
        dialog.present()

    def run(self):
        self.loop.run()


class FaugusRun(HiDpiMixin):
    def __init__(self, message, command=None, pre_launch="", post_launch="", gameid="", with_logs=False, title="", exe=""):
        self.message = message
        self.command = command
        self.pre_launch = pre_launch
        self.post_launch = post_launch
        self.gameid = gameid
        self.title = title
        self.exe = exe.replace("\\", "/").rsplit("/", 1)[-1].lower()
        self.discord_socket = None
        self.discord_icon = None
        self.discord_stop = Event()
        self.logging_enabled = with_logs
        self.process = None
        self.splash_process = None
        self.steam_runtime_installed = False
        self.log_window = None
        self.text_view = None
        self.proton_latest = None
        self.proton_exists = False

        self.load_config()
        load_frame_css()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: self.on_process_exit(None, None))

    def run(self):
        self.process_thread = Thread(target=self.start_process)

        def start_thread():
            self.process_thread.start()
            return False

        self.loop = GLib.MainLoop()
        GLib.idle_add(start_thread)
        self.loop.run()

        self.process_thread.join()
        sys.exit(0)

    def start_process(self):
        if self.show_donate:
            if self.playtime >= 14400:
                current_month = GLib.DateTime.new_now_local().format("%Y-%m")

                if self.cfg.config.get("donate-last", "") != current_month:
                    self.show_donate_dialog()
                    self.cfg.set_value("donate-last", current_month)
                    self.cfg.save_config()

        set_env("PROTON_EAC_RUNTIME", EAC_DIR)
        set_env("PROTON_BATTLEYE_RUNTIME", BE_DIR)

        gpu = next((g for g in get_gpus() if g["slot"] == self.gpu), None)
        if gpu:
            set_child_env("DRI_PRIME", "pci-" + gpu["slot"].replace(":", "_").replace(".", "_"))
            set_child_env("MESA_VK_DEVICE_SELECT", "{}:{}".format(gpu["vendor"], gpu["device"]))
            set_child_env("MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE", "1")
            if gpu["vendor"] == "10de":
                set_child_env("__NV_PRIME_RENDER_OFFLOAD", "1")
                set_child_env("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
                set_child_env("__VK_LAYER_NV_optimus", "NVIDIA_only")
            else:
                set_child_env("__GLX_VENDOR_LIBRARY_NAME", "mesa")
            GLib.idle_add(warm_up_gpu)
        if self.wayland_driver:
            set_env("PROTON_ENABLE_WAYLAND", "1")
        if self.wow64_enabled:
            set_env("PROTON_USE_WOW64", "1")

        set_env("UMU_USE_STEAM", "1")
        set_env("UMU_CONTAINER_NSENTER", "1")

        self.extract_env_from_message()

        if os.environ.get("FAUGUS_LOG") == "1":
            self.logging_enabled = True

        if self.splash_window_enabled and self.automatic_updates and not os.environ.get("DISABLE_UMU"):
            GLib.idle_add(self.show_splash)

        if self.command == "winetricks":
            GLib.idle_add(self.show_log_window)

        if os.environ.get("PROTONPATH") == "Steam":
            subprocess.Popen(self.message, shell=True, env=child_env())

            def update_ui():
                if self.splash_process:
                    self.splash_label(_("Starting Steam game..."))
                return False

            GLib.idle_add(update_ui)

            def close_app():
                self.loop.quit()
                sys.exit()

            GLib.timeout_add(5000, close_app)
            return

        if os.environ.get("LSFG_LEGACY") or os.environ.get("LSFGVK_ENV"):
            if self.lossless_location:
                set_env("LSFG_DLL_PATH", self.lossless_location)
                set_env("LSFGVK_DLL_PATH", self.lossless_location)

        if self.logging_enabled:
            self.log_dir = os.environ.get("LOG_DIR") or "default"

        if not os.environ.get("PROTONPATH") == "umu-sniper":
            if self.logging_enabled:
                set_env("UMU_LOG", "1")

                target_dir = f"{LOGS_DIR}/{self.log_dir}"
                set_env("PROTON_LOG_DIR", target_dir)
                set_env("PROTON_LOG", "1")

                if os.path.exists(target_dir):
                    for file in os.listdir(target_dir):
                        if "steam" in file or "proton" in file:
                            os.remove(f"{target_dir}/{file}")

        if not os.environ.get("WINEPREFIX") and not os.environ.get("DISABLE_UMU"):
            if not os.environ.get("PROTONPATH") in ["umu-steamrt4", "umu-sniper", "umu-soldier", "umu-scout", "umu-host"]:
                set_env("WINEPREFIX", f"{self.default_prefix}/default")
                set_env("PROTONPATH", f"{resolve_protonpath(self.default_runner)}")

        protonpath = os.environ.get("PROTONPATH")
        if protonpath and protonpath not in ["Proton-GE Latest", "Proton-CachyOS Latest", "DW-Proton Latest", "Proton-Wineland Latest", "umu-steamrt4", "umu-sniper", "umu-soldier", "umu-scout", "umu-host"]:
            if protonpath == "Proton-CachyOS (System)" and not os.path.exists(PROTON_CACHYOS):
                self.close_splash_window()
                self.show_error_dialog(protonpath)
            elif protonpath == "Linux-Native":
                pass
            elif protonpath == "Steam":
                pass
            else:
                protonpath_path = find_compatibilitytool(protonpath)
                if protonpath_path is None:
                    self.close_splash_window()
                    self.show_error_dialog(protonpath)
        latest_flags = {
            "Proton-GE Latest": "--ge",
            "Proton-CachyOS Latest": "--cachyos",
            "DW-Proton Latest": "--dw",
            "Proton-Wineland Latest": "--wineland",
        }
        if protonpath in latest_flags:
            self.proton_latest = latest_flags[protonpath]
            self.proton_exists = find_compatibilitytool(protonpath) is not None

        if protonpath:
            protonpath_path = find_compatibilitytool(protonpath)
            if protonpath in latest_flags:
                protonpath_path = protonpath_path or COMPATIBILITY_DIR / protonpath
            if protonpath_path:
                set_env("PROTONPATH", str(protonpath_path))

        if protonpath and "wineland" in protonpath.lower():
            os.environ.pop("PROTON_ENABLE_WAYLAND", None)
            _env_set.discard("PROTON_ENABLE_WAYLAND")

        self.components_exists = (
            os.path.exists(EAC_DIR) and
            os.path.exists(BE_DIR) and
            os.path.exists(UMU_RUN)
        )

        env_from_file = self.load_env_from_file()
        if env_from_file:
            print("\n=== GLOBAL ENVIRONMENT VARIABLES ===")
            for key in sorted(env_from_file):
                print(f"{key}={env_from_file[key]}")

        print("\n=== ENVIRONMENT VARIABLES ===")
        for key in sorted(_env_set):
            print(f"{key}={os.environ.get(key)}")
        for key in sorted(_child_only_env):
            print(f"{key}={_child_only_env[key]}")

        print("\n=== UMU-LAUNCHER COMMAND ===")
        print(f"{self.message}\n")

        self.execute_final_command()

    def execute_final_command(self):

        def start_and_watch(cmd, is_game=False):
            log_file = None
            if self.logging_enabled:
                log_path = Path(LOGS_DIR) / self.log_dir
                log_path.mkdir(parents=True, exist_ok=True)
                log_file = open(log_path / "umu.log", "a", encoding="utf-8")

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=8192, text=True, start_new_session=is_game,
                env=child_env()
            )

            def watch_stream(stream, lf=None):
                for line in iter(stream.readline, ""):
                    clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line).strip()

                    if lf:
                        lf.write(f"{clean_line}\n")
                        lf.flush()

                    self.check_game_output(clean_line)

                    if clean_line.startswith("PROGRESS "):
                        continue

                    if os.environ.get("GAMEID") == "winetricks-gui":
                        GLib.idle_add(self.append_to_text_view, clean_line)
                    else:
                        print(line, end="")
                stream.close()

            threads = [
                Thread(target=watch_stream, args=(process.stdout, log_file), daemon=True),
                Thread(target=watch_stream, args=(process.stderr, log_file), daemon=True)
            ]
            for t in threads: t.start()

            if is_game:
                self.process = process
                GLib.child_watch_add(GLib.PRIORITY_DEFAULT, process.pid, self.on_process_exit)
                Thread(target=self._watch_game_process, daemon=True).start()
                self.progress_save_source = GLib.timeout_add_seconds(30, self._save_progress_tick)
                if self.gameid:
                    self._mark_running(True)
                    if os.environ.get("DISCORD_RPC"):
                        Thread(target=self._discord_start, daemon=True).start()
                    try:
                        os.remove(stop_request_path(self.gameid))
                    except FileNotFoundError:
                        pass
                    GLib.timeout_add_seconds(1, self._check_stop_request)
                if log_file:
                    def close_log_later():
                        for t in threads:
                            t.join()
                        log_file.flush()
                        log_file.close()
                    Thread(target=close_log_later, daemon=True).start()
            else:
                process.wait()
                for t in threads: t.join(timeout=1)
                if log_file:
                    log_file.close()

        self.inhibit_handle = None
        self.inhibit_fd = None
        if os.environ.get("NO_SLEEP"):
            try:
                result = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
                    "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                    "org.freedesktop.portal.Inhibit", "Inhibit",
                    GLib.Variant("(sua{sv})", ("", 4 | 8, {"reason": GLib.Variant("s", "Game is running")})),
                    GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None,
                )
                self.inhibit_handle = result.unpack()[0]
            except GLib.Error as e:
                print(f"Failed to inhibit sleep via portal: {e}")
                try:
                    result, fd_list = Gio.bus_get_sync(Gio.BusType.SYSTEM, None).call_with_unix_fd_list_sync(
                        "org.freedesktop.login1", "/org/freedesktop/login1",
                        "org.freedesktop.login1.Manager", "Inhibit",
                        GLib.Variant("(ssss)", ("sleep:idle", "Faugus Launcher", "Game is running", "block")),
                        GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1, None, None,
                    )
                    self.inhibit_fd = fd_list.steal_fds()[result.unpack()[0]]
                except GLib.Error as e:
                    print(f"Failed to inhibit sleep via logind: {e}")

        self.steam_runtime_installed = any(
            os.path.isdir(PathManager.user_data("umu", name)) for name in ("steamrt3", "steamrt4")
        )

        cmds_to_run = []
        is_sniper = os.environ.get("PROTONPATH") == "umu-sniper"
        force_off = os.environ.get("FAUGUS_DISABLE_UPDATES") or not self.automatic_updates
        if not os.environ.get("DISABLE_UMU") and (not force_off or not self.components_exists):
            cmds_to_run.append([sys.executable, "-m", "faugus.components"])

        if not is_sniper:
            if force_off: set_env("UMU_RUNTIME_UPDATE", "0")
            if self.proton_latest and (not force_off or not self.proton_exists):
                cmds_to_run.append([sys.executable, "-m", "faugus.proton_downloader", self.proton_latest])

        for cmd in cmds_to_run:
            start_and_watch(cmd)

        if self.pre_launch:
            try:
                subprocess.Popen(self.pre_launch, shell=True, env=child_env())
            except Exception as e:
                print(f"Error running pre-launch command: {e}")

        game_cmd = shlex.split(self.message)
        self.start_time = time.time()

        self.cfg_playtime_baseline = self.playtime
        self.game_playtime_baseline = 0
        if self.gameid:
            for saved_game in load_json_file(GAMES_JSON, []):
                if saved_game.get("gameid") == self.gameid:
                    self.game_playtime_baseline = saved_game.get("playtime", 0)
                    break

        start_and_watch(game_cmd, is_game=True)

    def show_donate_dialog(self):
        result = subprocess.run(
            [sys.executable, "-m", "faugus.runner", "--donate"],
            stdout=subprocess.PIPE, text=True, env=child_env(),
        )
        if result.stdout.strip() == "checked":
            self.cfg.set_value("show-donate", False)
            self.cfg.save_config()

    def show_error_dialog(self, protonpath):
        done = Event()

        text1 = _("%s was not found") % protonpath
        text2 = _("Please install it or use another Proton version.")

        def build_and_show():
            show_message_dialog(text1, text2, callback=lambda ok: done.set())
            return False

        GLib.idle_add(build_and_show)
        done.wait()
        self.loop.quit()
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

    def load_env_from_file(self, filename=ENVAR_DIR):
        env_from_file = {}

        for line in load_json_file(filename, default=[]):
            line = line.strip()
            if not line or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()

            os.environ[key] = value
            env_from_file[key] = value

        return env_from_file

    def load_config(self):
        self.cfg = ConfigManager()

        self.gpu = self.cfg.config.get('gpu', '').strip('"')
        self.splash_window_enabled = self.cfg.config.get('splash-window-enabled', 'True') == 'True'
        self.default_runner = self.cfg.config.get('default-runner', '')
        self.lossless_location = expand_path(self.cfg.config.get('lossless-location', ''))
        self.default_prefix = expand_path(self.cfg.config.get('default-prefix', ''))
        self.wayland_driver = self.cfg.config.get('wayland-driver', 'False') == 'True'
        self.wow64_enabled = self.cfg.config.get('wow64-enabled', 'False') == 'True'
        self.show_donate = self.cfg.config.get('show-donate', 'False') == 'True'
        self.playtime = int(self.cfg.config.get("playtime", 0))
        self.automatic_updates = self.cfg.config.get('automatic-updates', 'True') == 'True'

        apply_runner_theme(self.cfg)

    def show_splash(self):
        game_icon = os.environ.get("SPLASHICON")
        image_path = game_icon if game_icon and os.path.exists(game_icon) else FAUGUS_PNG_RASTER
        self.splash_process = subprocess.Popen(
            [sys.executable, "-m", "faugus.runner", "--splash", image_path],
            stdin=subprocess.PIPE, text=True, env=child_env(),
        )

    def splash_send(self, command):
        try:
            self.splash_process.stdin.write(command + "\n")
            self.splash_process.stdin.flush()
        except (OSError, ValueError, AttributeError):
            pass

    def splash_label(self, text):
        self.splash_send("LABEL " + text)

    def show_progress(self, fraction=None):
        if not self.splash_process:
            return
        self.splash_send("PULSE" if fraction is None else f"FRACTION {fraction}")

    def hide_progress(self):
        if self.splash_process:
            self.splash_send("HIDE")

    def show_log_window(self):
        self.log_window = Gtk.Window(title="Winetricks Logs")
        self.log_window.set_default_size(600, 400)

        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.text_view = Gtk.TextView()
        self.text_view.set_editable(False)
        scrolled_window.set_child(self.text_view)
        self.log_window.set_child(scrolled_window)

        self.log_window.connect("close-request", self.on_log_window_close_request)
        self.log_window.present()

    def check_game_output(self, clean_line):
        if "Downloading upscaler file" in clean_line:
            return False

        if not clean_line.startswith("PROGRESS ") and not STATUS_LINE.search(clean_line):
            return False

        if clean_line.startswith("PROGRESS "):
            fraction = float(clean_line.split()[1])

            def update_progress():
                self.show_progress(fraction)
                return False

            GLib.idle_add(update_progress)
            return False

        def update_ui():
            if (
                "Downloading" in clean_line
                or "Updating BattlEye..." in clean_line
                or "Updating Easy Anti-Cheat..." in clean_line
                or "Updating UMU-Launcher..." in clean_line
            ):
                if self.splash_process is None:
                    self.show_splash()

            if "Components are up to date" in clean_line:
                if self.splash_process:
                    self.splash_label(_("Components are up to date"))
                    self.hide_progress()
                return False

            component = next((c for c in (
                "UMU-Launcher", "BattlEye", "Easy Anti-Cheat", "GE-Proton",
                "Proton-CachyOS", "DW-Proton", "Proton-Wineland",
            ) if c in clean_line), None)
            if component is None and ("steamrt3" in clean_line or "steamrt4" in clean_line or "SteamLinuxRuntime" in clean_line):
                component = "Steam Runtime"

            if component == "Steam Runtime" and self.splash_process:
                if "is up to date" in clean_line or "mtree is OK" in clean_line:
                    self.splash_label(f"{component} " + _("is up to date"))
                    self.hide_progress()
                elif "Downloading" in clean_line or "Extracting" in clean_line or "SteamLinuxRuntime_sniper.tar.xz" in clean_line:
                    action = _("Updating") if self.steam_runtime_installed else _("Downloading")
                    self.splash_label(f"{action} {component}...")
                    self.show_progress()
            elif component and self.splash_process:
                if "Updating" in clean_line:
                    self.splash_label(_("Updating") + f" {component}...")
                elif "Downloading" in clean_line or "Extracting" in clean_line:
                    action = _("Updating") if self.proton_exists else _("Downloading")
                    self.splash_label(f"{action} {component}...")
                elif (
                    "is up to date" in clean_line
                    or "mtree is OK" in clean_line
                    or ("->" in clean_line and component in clean_line)
                ):
                    self.splash_label(f"{component} " + _("is up to date"))
                    self.hide_progress()
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
        process, self.splash_process = self.splash_process, None
        if process:
            try:
                process.stdin.close()
            except OSError:
                pass
            Thread(target=process.wait, daemon=True).start()

    def close_log_window(self):
        if self.log_window:
            destroy_and_release(self.log_window)
            self.log_window = None

    def on_log_window_close_request(self, window):
        return True

    def show_regedit_confirmation(self):
        parts = self.message.split()
        if parts:
            last_part = parts[-1].strip('"')

            if last_part.endswith(".reg"):
                def on_result(ok):
                    self.loop.quit()
                    sys.exit()

                show_message_dialog(
                    _("The keys and values were successfully added to the registry."),
                    callback=on_result,
                )
                return True

        return False

    def _discord_target(self, index):
        game = discord_find_game(index)
        if game:
            return game[0], {}
        title = re.sub(r"[^a-z0-9]", "", self.title.lower())
        matches = []
        for _, app_id, name, launcher in index.get(self.exe, []):
            name = re.sub(r"[^a-z0-9]", "", name.lower())
            if title and not launcher and (name in title or title in name):
                matches.append((name != title, app_id))
        if matches:
            return min(matches)[1], {}
        if any(gameid != self.gameid for gameid in load_json_file(RUNNING_GAMES, {})):
            return None
        activity = {"details": self.title, "status_display_type": 2}
        if self.discord_icon is None:
            self.discord_icon = self._discord_find_icon()
        if self.discord_icon:
            activity["assets"] = {"large_image": self.discord_icon}
        return DISCORD_FALLBACK_CLIENT_ID, activity

    def _discord_find_icon(self):
        cfg = ConfigManager()
        api_key = cfg.config.get("steamgriddb-api-key", "").strip('"')
        if not api_key or cfg.config.get("steamgriddb-enabled", "False") != "True":
            return ""
        game_id = next((g.get("steamgriddb_id") for g in load_json_file(GAMES_JSON, []) if g.get("gameid") == self.gameid), None)
        icons = fetch_steamgriddb_candidates(api_key, self.title, limit=1, game_id=game_id or None)["icons"]
        if not icons:
            return ""
        return icons[0]["thumb"] if icons[0]["url"].lower().endswith(".ico") else icons[0]["url"]

    def _discord_start(self):
        index = discord_load_detectable()
        current = None
        while not self.discord_stop.is_set():
            try:
                target = self._discord_target(index)
                if target != current:
                    self._discord_close()
                    current = target
                    sock = discord_connect(target[0]) if target else None
                    self.discord_socket = sock
                    if sock:
                        activity = {"timestamps": {"start": int(time.time())}, **target[1]}
                        sock.sendall(discord_frame(1, {
                            "cmd": "SET_ACTIVITY",
                            "args": {"pid": os.getpid(), "activity": activity},
                            "nonce": str(uuid.uuid4()),
                        }))
            except OSError:
                self._discord_close()
                current = None
            self.discord_stop.wait(5)
        self._discord_close()

    def _discord_close(self):
        sock, self.discord_socket = self.discord_socket, None
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def _discord_stop(self):
        self.discord_stop.set()
        self._discord_close()

    def _mark_running(self, running):
        games = load_json_file(RUNNING_GAMES, {})
        if running:
            games[self.gameid] = os.getpid()
        else:
            games.pop(self.gameid, None)
        save_json_file(games, RUNNING_GAMES)

    def _check_stop_request(self):
        path = stop_request_path(self.gameid)
        if not os.path.exists(path):
            return True
        os.remove(path)
        self.on_process_exit(None, None)
        return False

    def _save_progress_tick(self):
        self._save_progress()
        return True

    def _save_progress(self):
        runtime = int(time.time() - self.start_time)
        if runtime <= 0:
            return

        self.cfg.load_config()
        self.cfg.set_value("playtime", self.cfg_playtime_baseline + runtime)
        self.cfg.save_config()

        if not self.gameid:
            return

        games = load_json_file(GAMES_JSON, [])
        for game in games:
            if game.get("gameid") == self.gameid:
                game["playtime"] = self.game_playtime_baseline + runtime
                game["last_played"] = datetime.now().isoformat()
                break
        save_json_file(games, GAMES_JSON)

    def on_process_exit(self, pid, condition):
        import psutil

        def kill_child_proc():

            if self.gameid:
                kill_by_faugusid(self.gameid)

            if self.process:
                try:
                    pgid = os.getpgid(self.process.pid)
                    os.killpg(pgid, signal.SIGKILL)
                    return
                except (ProcessLookupError, OSError):
                    pass
                try:
                    parent = psutil.Process(self.process.pid)
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass

        self._discord_stop()

        if getattr(self, "inhibit_handle", None):
            try:
                Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
                    "org.freedesktop.portal.Desktop", self.inhibit_handle,
                    "org.freedesktop.portal.Request", "Close",
                    None, None, Gio.DBusCallFlags.NONE, -1, None,
                )
            except GLib.Error as e:
                print(f"Failed to release sleep inhibitor: {e}")
            self.inhibit_handle = None

        if getattr(self, "inhibit_fd", None) is not None:
            os.close(self.inhibit_fd)
            self.inhibit_fd = None

        if self.post_launch:
            try:
                post_env = child_env()
                post_env.pop("FAUGUSID", None)
                subprocess.Popen(self.post_launch, shell=True, env=post_env)
            except Exception as e:
                print(f"Error running post-launch command: {e}")

        if getattr(self, "progress_save_source", None):
            GLib.source_remove(self.progress_save_source)
            self.progress_save_source = None

        self._save_progress()

        if self.gameid:
            self._mark_running(False)
            try:
                connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                connection.call_sync(
                    TRAY_BUS_NAME, TRAY_OBJECT_PATH, TRAY_INTERFACE, "RefreshMenu",
                    None, None, Gio.DBusCallFlags.NONE, -1, None,
                )
            except GLib.Error:
                pass

        if self.logging_enabled:
            target_dir = f"{LOGS_DIR}/{self.log_dir}"

            if os.path.exists(target_dir):
                for file in os.listdir(target_dir):
                    if "steam" in file:
                        old_path = f"{target_dir}/{file}"
                        new_path = f"{target_dir}/proton.log"

                        os.rename(old_path, new_path)
                        break

        def finish():
            self.close_splash_window()
            self.close_log_window()
            if not self.show_regedit_confirmation():
                self.loop.quit()
            return False

        GLib.idle_add(finish)
        kill_child_proc()

        return False


def build_launch_command(game):
    gameid = game.get("gameid", "")
    path = expand_path(game.get("path", ""))
    prefix = expand_path(game.get("prefix", ""))
    launch_arguments = expand_path(game.get("launch_arguments", ""))
    game_arguments = expand_path(game.get("game_arguments", ""))
    runner = resolve_game_runner(game.get("runner", ""))
    addapp_bat = expand_path(game.get("addapp_bat", ""))
    mangohud = game.get("mangohud", "")
    gamemode = game.get("gamemode", "")
    sdl_enabled = game.get("sdl_enabled", "")
    no_sleep = game.get("no_sleep", "")
    discord_rpc = game.get("discord_rpc", "")
    addapp_enabled = game.get("addapp_enabled", "")
    lossless_enabled = game.get("lossless_enabled", "")
    lossless_multiplier = game.get("lossless_multiplier", "")
    lossless_flow = game.get("lossless_flow", "")
    lossless_performance = game.get("lossless_performance", "")
    lossless_hdr = game.get("lossless_hdr", "")
    lossless_present = game.get("lossless_present", "")
    icon = game.get("icon", "")
    disable_umu = bool(game.get("disable_umu", "")) and runner == "Linux-Native"
    linux_runtime = game.get("runtime","")

    if gameid == "ea-app":
        path = update_ea_path(prefix)

    command_parts = []

    if icon:
        command_parts.append(f"SPLASHICON={icon}")
    if gameid:
        command_parts.append(f"LOG_DIR='{gameid}'")
        command_parts.append(f"FAUGUSID={gameid}")
    if sdl_enabled:
        command_parts.append("PROTON_PREFER_SDL=1")
    if no_sleep:
        command_parts.append("NO_SLEEP=1")
    if discord_rpc:
        command_parts.append("DISCORD_RPC=1")
    if runner:
        if runner == "Linux-Native":
            if disable_umu:
                command_parts.append("DISABLE_UMU=1")
            elif linux_runtime:
                command_parts.append(f"PROTONPATH={linux_runtime}")
        elif runner == "Proton-CachyOS (System)":
            command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
            command_parts.append(f"PROTONPATH={PROTON_CACHYOS}")
        else:
            command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
            reserved_names = (
                "Proton-GE Latest",
                "DW-Proton Latest", "Proton-CachyOS Latest",
                "Proton-Wineland Latest",
            )
            if os.path.isdir(runner):
                command_parts.append(f"PROTONPATH={shlex.quote(runner)}")
            elif runner in reserved_names:
                command_parts.append(f"PROTONPATH='{runner}'")
            else:
                command_parts.append(f"PROTONPATH='{runner}'")
    else:
        command_parts.append(f"WINEPREFIX={shlex.quote(prefix)}")
    command_parts.extend(build_lossless_env(lossless_enabled, lossless_multiplier, lossless_flow, lossless_performance, lossless_hdr, lossless_present))
    if launch_arguments:
        command_parts.append(launch_arguments)
    if gamemode and os.path.exists(GAMEMODERUN):
        command_parts.append("gamemoderun")
    if mangohud and os.path.exists(MANGOHUD_DIR):
        command_parts.append("mangohud")

    if runner != "Steam" and not disable_umu:
        command_parts.append(f"'{UMU_RUN}'")

    if addapp_enabled == "addapp_enabled":
        command_parts.append(shlex.quote(addapp_bat))
    elif runner != "Steam":
        command_parts.append(shlex.quote(path))
    else:
        steam_arguments = "-nobigpicture -nochatui -nofriendsui -silent -applaunch"
        steam_cmd = "flatpak run com.valvesoftware.Steam" if IS_STEAM_FLATPAK else "steam"
        if IS_FLATPAK:
            steam_cmd = f"flatpak-spawn --host {steam_cmd}"
        command_parts.append(f"{steam_cmd} {steam_arguments} {path}")

    if game_arguments:
        command_parts.append(game_arguments)

    return " ".join(command_parts)


def load_game_from_json(gameid):
    for game in load_json_file(GAMES_JSON):
        if game.get("gameid") == gameid:
            return game

    return None


def is_apple_silicon():
    try:
        with open("/proc/device-tree/compatible", "rb") as f:
            return "apple,arm-platform" in f.read().decode('utf-8', errors='ignore')
    except:
        return False


def main():
    suppress_adwaita_theme_warning()

    if is_apple_silicon() and 'FAUGUS_MUVM' not in os.environ:
        import shutil
        muvm_path = shutil.which('muvm')
        if muvm_path:
            env = os.environ.copy()
            args = [muvm_path, "-i", "-e", "FAUGUS_MUVM=1", sys.executable, os.path.abspath(__file__)]
            os.execvpe(muvm_path, args + sys.argv[1:], env)

    parser = argparse.ArgumentParser(description=None)
    parser.add_argument("message", nargs='?')
    parser.add_argument("command", nargs='?', default=None)
    parser.add_argument("--game")
    parser.add_argument("--pre-launch", default="")
    parser.add_argument("--post-launch", default="")
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--splash")
    parser.add_argument("--donate", action="store_true")

    args = parser.parse_args()

    if args.splash:
        FaugusSplash(args.splash).run()
    elif args.donate:
        FaugusDonate().run()
    elif args.game:
        game = load_game_from_json(args.game)
        if not game:
            return

        launch_options = build_launch_command(game)
        FaugusRun(launch_options, None, game.get("pre_launch", ""), game.get("post_launch", ""), args.game, with_logs=args.logs, title=game.get("title", ""), exe=game.get("path", "")).run()
    else:
        FaugusRun(args.message, args.command, args.pre_launch, args.post_launch, with_logs=args.logs).run()


if __name__ == "__main__":
    main()
