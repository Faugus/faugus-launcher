#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, GdkPixbuf

import atexit
import sys
import subprocess
import argparse
import re
import os

config_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
faugus_launcher_dir = f'{config_dir}/faugus-launcher'
prefixes_dir = f'{faugus_launcher_dir}/prefixes'
config_file_dir = f'{faugus_launcher_dir}/config.ini'
share_dir = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))


def remove_ansi_escape(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


class FaugusRun:
    def __init__(self, message):
        self.message = message
        self.process = None
        self.warning_dialog = None
        self.log_window = None
        self.text_view = None
        self.default_runner = None
        self.default_prefix = None

    def show_error_dialog(self, protonpath):
        dialog = Gtk.MessageDialog(
            title="Error",
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.CLOSE,
            text=f"{protonpath} was not found",
        )
        dialog.format_secondary_text("Please install it or use another Proton version.")
        dialog.run()
        dialog.destroy()
        sys.exit(1)

    def start_process(self, command):

        sc_controller_installed = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
            "/usr/local/bin/sc-controller")
        if sc_controller_installed:
            if "SC_CONTROLLER=1" in self.message:
                self.start_scc_daemon()

        self.load_config()

        protonpath = next((part.split('=')[1] for part in self.message.split() if part.startswith("PROTONPATH=")), None)
        if protonpath and protonpath != "GE-Proton":
            protonpath_path = f'{share_dir}/Steam/compatibilitytools.d/{protonpath}'
            if not os.path.isdir(protonpath_path):
                self.show_error_dialog(protonpath)

        if self.default_runner == "UMU-Proton Latest":
            self.default_runner = ""
        if self.default_runner == "GE-Proton Latest (default)":
            self.default_runner = "GE-Proton"
        if "WINEPREFIX" not in self.message:
            if self.default_runner:
                self.message = f'WINEPREFIX={self.default_prefix}/default PROTONPATH={self.default_runner} {self.message}'
            else:
                self.message = f'WINEPREFIX={self.default_prefix}/default {self.message}'
        print(self.message)

        self.process = subprocess.Popen(["/bin/bash", "-c", self.message], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)

        if command == "winetricks":
            self.show_log_window()

        self.show_warning_dialog()

        GLib.io_add_watch(self.process.stdout, GLib.IO_IN, self.on_output)
        GLib.io_add_watch(self.process.stderr, GLib.IO_IN, self.on_output)

        GLib.child_watch_add(self.process.pid, self.on_process_exit)

    def load_config(self):
        config_file = config_file_dir

        if os.path.isfile(config_file):
            with open(config_file, 'r') as f:
                config_dict = {}
                for line in f.read().splitlines():
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"')
                        config_dict[key] = value

            self.default_runner = config_dict.get('default-runner', '')
            self.default_prefix = config_dict.get('default-prefix', '')
        else:
            self.save_config(False, '', "False", "False", "False", "GE-Proton Latest (default)")
            self.default_runner = "GE-Proton Latest (default)"

    def save_config(self, checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state,
                    default_runner):
        config_file = config_file_dir

        config_path = faugus_launcher_dir
        if not os.path.exists(config_path):
            os.makedirs(config_path)

        default_prefix = prefixes_dir
        self.default_prefix = prefixes_dir

        default_runner = (f'"{default_runner}"')

        config = {}

        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                for line in f:
                    key, value = line.strip().split('=', 1)
                    config[key] = value.strip('"')

        config['close-onlaunch'] = checkbox_state
        config['default-prefix'] = default_prefix
        config['mangohud'] = mangohud_state
        config['gamemode'] = gamemode_state
        config['sc-controller'] = sc_controller_state
        config['default-runner'] = default_runner

        with open(config_file, 'w') as f:
            for key, value in config.items():
                if key == 'default-prefix':
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f'{key}={value}\n')

    def start_scc_daemon(self):
        working_directory = faugus_launcher_dir
        try:
            subprocess.run(["scc-daemon", "controller.sccprofile", "start"], check=True, cwd=working_directory)
        except subprocess.CalledProcessError as e:
            print(f"Failed to start scc-daemon: {e}")

    def show_warning_dialog(self):
        self.warning_dialog = Gtk.Window(title="Faugus Launcher")
        self.warning_dialog.set_decorated(False)
        self.warning_dialog.set_resizable(False)
        self.warning_dialog.set_default_size(280, -1)

        frame = Gtk.Frame()
        frame.set_label_align(0.5, 0.5)
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        grid = Gtk.Grid()
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_valign(Gtk.Align.CENTER)
        frame.add(grid)

        image_path = "/usr/share/icons/faugus-launcher.png"
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)

        pixbuf = pixbuf.scale_simple(75, 75, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_margin_top(20)
        image.set_margin_start(20)
        image.set_margin_end(20)
        image.set_margin_bottom(20)
        grid.attach(image, 0, 0, 1, 1)

        protonpath = next((part.split('=')[1] for part in self.message.split() if part.startswith("PROTONPATH=")), None)
        if protonpath == "Using UMU-Proton":
            protonpath = "UMU-Proton Latest"
        if not protonpath:
            protonpath = "Using UMU-Proton Latest"
        else:
            protonpath = f"Using {protonpath}"
        print(protonpath)

        self.label = Gtk.Label(label=protonpath)
        self.label.set_margin_start(20)
        self.label.set_margin_end(20)

        self.label2 = Gtk.Label()
        self.label2.set_margin_bottom(20)
        self.label2.set_margin_start(20)
        self.label2.set_margin_end(20)

        grid.attach(self.label, 0, 1, 1, 1)
        grid.attach(self.label2, 0, 2, 1, 1)

        self.warning_dialog.add(frame)

        self.warning_dialog.show_all()

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

    def on_output(self, source, condition):
        if line := source.readline():
            clean_line = remove_ansi_escape(line).strip()
            self.check_game_output(clean_line)
            if "winetricks" in self.message:
                self.append_to_text_view(clean_line)
            else:
                print(line, end='')
        return True


    def check_game_output(self, clean_line):
        if "Downloading GE-Proton" in clean_line:
            self.label.set_text("Downloading GE-Proton...")
        if "Downloading UMU-Proton" in clean_line:
            self.label.set_text("Downloading UMU-Proton...")
        if "Downloading latest steamrt sniper" in clean_line:
            self.label2.set_text("Downloading Steam Runtime...")
        if "SteamLinuxRuntime_sniper.tar.xz" in clean_line:
            self.label2.set_text("Extracting Steam Runtime...")
        if "Extracting GE-Proton" in clean_line:
            self.label.set_text("Extracting GE-Proton...")
        if "Extracting UMU-Proton" in clean_line:
            self.label.set_text("Extracting UMU-Proton...")
        if "GE-Proton is up to date" in clean_line:
            self.label.set_text("GE-Proton is up to date")
        if "UMU-Proton is up to date" in clean_line:
            self.label.set_text("UMU-Proton is up to date")
        if "steamrt is up to date" in clean_line:
            self.label2.set_text("Steam Runtime is up to date")
        if "->" in clean_line and "GE-Proton" in clean_line:
            self.label.set_text("GE-Proton is up to date")
        if "->" in clean_line and "UMU-Proton" in clean_line:
            self.label.set_text("UMU-Proton is up to date")
        if "mtree is OK" in clean_line:
            self.label2.set_text("Steam Runtime is up to date")


        if "ProtonFixes" in clean_line:
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

                self.grid = Gtk.Grid()
                self.grid.set_row_spacing(20)
                self.grid.set_column_spacing(0)
                self.grid.set_margin_start(10)
                self.grid.set_margin_end(10)
                self.grid.set_margin_top(10)
                self.grid.set_margin_bottom(10)

                self.label = Gtk.Label(label="The keys and values were successfully added to the registry.")

                self.button_ok = Gtk.Button(label="Ok")
                self.button_ok.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
                self.button_ok.set_size_request(150, -1)
                self.button_ok.set_halign(Gtk.Align.CENTER)

                self.grid.attach(self.label, 0, 0, 1, 1)
                self.grid.attach(self.button_ok, 0, 1, 1, 1)

                dialog.get_content_area().add(self.grid)

                dialog.show_all()
                dialog.run()
                dialog.destroy()

    def on_process_exit(self, pid, condition):
        if self.process.poll() is not None:
            GLib.idle_add(self.close_warning_dialog)
            GLib.idle_add(self.close_log_window)
            GLib.idle_add(self.show_exit_warning)
            GLib.idle_add(Gtk.main_quit)
        return False


def handle_command(message, command=None):
    updater = FaugusRun(message)
    updater.start_process(command)

    Gtk.main()
    updater.process.wait()
    sys.exit(0)


def stop_scc_daemon():
    try:
        subprocess.run(["scc-daemon", "stop"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop scc-daemon: {e}")


def main():
    parser = argparse.ArgumentParser(description="Faugus Run")
    parser.add_argument("message", help="The message to be processed")
    parser.add_argument("command", nargs='?', default=None, help="The command to be executed (optional)")

    args = parser.parse_args()

    sc_controller_installed = os.path.exists("/usr/bin/sc-controller") or os.path.exists("/usr/local/bin/sc-controller")
    if sc_controller_installed:
        if "SC_CONTROLLER=1" in args.message:
            atexit.register(stop_scc_daemon)

    handle_command(args.message, args.command)


if __name__ == "__main__":
    main()
