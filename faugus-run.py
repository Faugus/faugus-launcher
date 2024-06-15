#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk
import sys
import subprocess
import argparse
from threading import Thread, Lock
import re


def remove_ansi_escape(text):
    # Regular expression to remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


class UMUProtonUpdater:
    def __init__(self, message):
        self.message = message
        self.process = None
        self.warning_dialog = None
        self.log_window = None
        self.text_view = None
        self.stdout_pipe = None
        self.stderr_pipe = None
        self.lock = Lock()

    def start_process(self, command):
        # Start the subprocess
        self.process = subprocess.Popen(["/bin/bash", "-c", self.message], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)

        if command == "winetricks":
            # Show log window for winetricks command
            self.show_log_window()

        # Display the warning message
        self.show_warning_dialog()

        # Start threads to capture and display output
        self.stdout_pipe = self.capture_output(self.process.stdout, self.check_game_output)
        self.stderr_pipe = self.capture_output(self.process.stderr, self.check_game_output)

        # Monitor the subprocess
        GLib.child_watch_add(self.process.pid, self.on_process_exit)

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
        text_buffer = self.text_view.get_buffer()

        scrolled_window.add(self.text_view)
        self.log_window.add(scrolled_window)

        self.log_window.connect("delete-event", self.on_log_window_delete_event)
        self.log_window.show_all()

    def capture_output(self, stream, callback):
        def read_stream(stream, callback):
            for line in iter(stream.readline, ''):
                GLib.idle_add(callback, line)
            stream.close()

        thread = Thread(target=read_stream, args=(stream, callback))
        thread.daemon = True
        thread.start()
        return thread

    def check_game_output(self, line):
        # Ignore lines containing "zenity", "Gtk-WARNING" or empty lines
        clean_line = remove_ansi_escape(line).strip()
        if "zenity" in clean_line or "Gtk-WARNING" in clean_line or "pixbuf" in clean_line or not clean_line:
            return

        # Check if the desired message was found in UMU-Run output
        if "Using UMU-Proton" in clean_line or "UMU-Proton is up to date" in clean_line:
            # Close the warning dialog after a short delay
            GLib.timeout_add_seconds(1, self.close_warning_dialog)
        else:
            # Append the line to the log window
            self.append_to_text_view(clean_line + '\n')

    def append_to_text_view(self, line):
        if self.text_view:
            clean_line = remove_ansi_escape(line)
            self.lock.acquire()
            end_iter = self.text_view.get_buffer().get_end_iter()
            self.text_view.get_buffer().insert(end_iter, clean_line)
            adj = self.text_view.get_parent().get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())
            self.lock.release()

    def close_warning_dialog(self):
        if self.warning_dialog:
            self.warning_dialog.destroy()
            self.warning_dialog = None

    def close_log_window(self):
        if self.log_window:
            self.log_window.destroy()
            self.log_window = None

    def on_log_window_delete_event(self, widget, event):
        # Prevent the user from manually closing the log window
        return True

    def on_process_exit(self, pid, condition):
        if self.process.poll() is not None:
            GLib.idle_add(self.close_warning_dialog)
            GLib.idle_add(self.close_log_window)
            GLib.idle_add(Gtk.main_quit)  # Ensure Gtk main loop quits
        return False


def handle_command(message, command=None):
    updater = UMUProtonUpdater(message)
    updater.start_process(command)

    Gtk.main()
    updater.process.wait()
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="UMU-Proton Updater")
    parser.add_argument("message", help="The message to be processed")
    parser.add_argument("command", nargs='?', default=None, help="The command to be executed (optional)")

    args = parser.parse_args()

    handle_command(args.message, args.command)


if __name__ == "__main__":
    main()
