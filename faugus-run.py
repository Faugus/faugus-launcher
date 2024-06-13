#!/usr/bin/env python3

import gi

gi.require_version("Gtk", "3.0")  # Ensure the version is specified before importing Gtk
from gi.repository import Gtk, GLib
import sys
import subprocess
import argparse


class UMUProtonUpdater:
    def __init__(self, message):
        self.message = message
        self.process = None

    def start_process(self, command):
        if command == "winetricks":
            self.open_log_window(self.message)
        else:
            # Start the subprocess
            self.process = subprocess.Popen(["/bin/bash", "-c", self.message], stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE, text=True)

            # Display the warning message
            self.show_warning_dialog()

            # Monitor the subprocess output
            GLib.io_add_watch(self.process.stdout, GLib.IO_IN, self.check_game_output)
            GLib.io_add_watch(self.process.stderr, GLib.IO_IN, self.check_game_output)

    def open_log_window(self, command):
        # Create a new window
        log_window = Gtk.Window(title="Winetricks Log")
        log_window.set_default_size(600, 400)

        # Create a TextView to display the log
        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_wrap_mode(Gtk.WrapMode.WORD)

        # Create a ScrolledWindow to hold the TextView
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_vexpand(True)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(textview)

        # Add the ScrolledWindow to the log window
        log_window.add(scrolled_window)

        # Function to update the TextView with new log lines
        def update_textview(fd, condition):
            line = fd.readline()
            if line:
                # Remove ANSI escape characters using regex
                clean_line = remove_ansi_escape(line)
                end_iter = textview.get_buffer().get_end_iter()
                textview.get_buffer().insert(end_iter, clean_line)
                scrolled_window.get_vadjustment().set_value(
                    scrolled_window.get_vadjustment().get_upper())  # Auto-scroll to bottom
                return True
            else:
                return False

        def remove_ansi_escape(s):
            import re
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            return ansi_escape.sub('', s)

        # Run the command and capture the output
        process_winetricks = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                              universal_newlines=True)

        # Attach the stdout to the TextView
        GLib.io_add_watch(process_winetricks.stdout, GLib.IO_IN, update_textview)

        # Function to check if the process has terminated and close the log window
        def check_process():
            if process_winetricks.poll() is None:
                return True
            else:
                log_window.destroy()
                return False

        # Add a timeout to periodically check if the process has terminated
        GLib.timeout_add(100, check_process)

        # Connect the destroy event of the log window to terminate the process
        def on_log_window_destroy(widget):
            if process_winetricks.poll() is None:
                process_winetricks.terminate()

        log_window.connect("destroy", on_log_window_destroy)

        # Show all widgets in the log window
        log_window.show_all()

    def show_warning_dialog(self):
        # Display the warning message while UMU-Run is updating
        self.warning_dialog = Gtk.MessageDialog(flags=0, message_type=Gtk.MessageType.WARNING,
                                                buttons=Gtk.ButtonsType.NONE,
                                                text="UMU-Proton is updating. Please wait...")

        self.warning_dialog.show()

    def check_game_output(self, fd, condition):
        # Read the game process output
        line = fd.readline()
        if not line:
            return False  # Remove the IO watch if no more lines

        # Check if the desired message was found in UMU-Run output
        if "Using UMU-Proton" in line or "UMU-Proton is up to date" in line:
            # Close the warning dialog after a short delay
            GLib.timeout_add_seconds(1, self.close_warning_dialog)
            return False  # Remove the IO watch since we no longer need to monitor the process output

        return True  # Continue monitoring the process output

    def close_warning_dialog(self):
        # Close the warning dialog
        self.warning_dialog.destroy()
        Gtk.main_quit()
        return False  # Stop the timeout function


def handle_command(message, command=None):
    # Create the UMUProtonUpdater instance and start the subprocess
    updater = UMUProtonUpdater(message)
    updater.start_process(command)

    Gtk.main()
    updater.process.wait()  # Wait for the UMU-Run process to finish
    sys.exit(0)  # Exit with success status


def main():
    parser = argparse.ArgumentParser(description="UMU-Proton Updater")
    parser.add_argument("message", help="The message to be processed")
    parser.add_argument("command", nargs='?', default=None, help="The command to be executed (optional)")

    args = parser.parse_args()

    handle_command(args.message, args.command)


if __name__ == "__main__":
    main()
