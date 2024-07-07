#!/usr/bin/env python3

import gi
import atexit

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk
import sys
import subprocess
import argparse
import re
import os

def remove_ansi_escape(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class UMUProtonUpdater:
    def __init__(self, message):
        self.message = message
        self.process = None
        self.warning_dialog = None
        self.log_window = None
        self.text_view = None

    def start_process(self, command):
        # Check if SC_CONTROLLER=1 is in message before starting scc-daemon
        if "SC_CONTROLLER=1" in self.message:
            self.start_scc_daemon()

        # Start the main process
        self.process = subprocess.Popen(["/bin/bash", "-c", self.message], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)

        if command == "winetricks":
            self.show_log_window()

        self.show_warning_dialog()

        GLib.io_add_watch(self.process.stdout, GLib.IO_IN, self.on_output)
        GLib.io_add_watch(self.process.stderr, GLib.IO_IN, self.on_output)

        GLib.child_watch_add(self.process.pid, self.on_process_exit)

    def start_scc_daemon(self):
        working_directory = os.path.expanduser("~/.config/faugus-launcher/")
        try:
            subprocess.run(["scc-daemon", "controller.sccprofile", "start"], check=True, cwd=working_directory)
        except subprocess.CalledProcessError as e:
            print(f"Failed to start scc-daemon: {e}")

    def show_warning_dialog(self):
        self.warning_dialog = Gtk.MessageDialog(flags=0, message_type=Gtk.MessageType.WARNING,
                                                buttons=Gtk.ButtonsType.NONE,
                                                text="UMU-Proton is updating. Please wait...")
        self.warning_dialog.show()

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
            self.check_game_output(line)
        return True

    def check_game_output(self, line):
        clean_line = remove_ansi_escape(line).strip()
        if any(keyword in clean_line for keyword in {"zenity", "Gtk-WARNING", "pixbuf"}) or not clean_line:
            return

        if "Using UMU-Proton" in clean_line or "UMU-Proton is up to date" in clean_line:
            GLib.timeout_add_seconds(1, self.close_warning_dialog)
        else:
            self.append_to_text_view(clean_line + '\n')

    def append_to_text_view(self, line):
        if self.text_view:
            clean_line = remove_ansi_escape(line)
            buffer = self.text_view.get_buffer()
            end_iter = buffer.get_end_iter()
            buffer.insert(end_iter, clean_line)
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

    def on_process_exit(self, pid, condition):
        if self.process.poll() is not None:
            GLib.idle_add(self.close_warning_dialog)
            GLib.idle_add(self.close_log_window)
            GLib.idle_add(Gtk.main_quit)
        return False


def handle_command(message, command=None):
    updater = UMUProtonUpdater(message)
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
    atexit.register(stop_scc_daemon)

    parser = argparse.ArgumentParser(description="UMU-Proton Updater")
    parser.add_argument("message", help="The message to be processed")
    parser.add_argument("command", nargs='?', default=None, help="The command to be executed (optional)")

    args = parser.parse_args()

    handle_command(args.message, args.command)


if __name__ == "__main__":
    main()
