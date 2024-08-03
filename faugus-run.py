#!/usr/bin/env python3

import gi
import atexit

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk, GdkPixbuf
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
        sc_controller_installed = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
            "/usr/local/bin/sc-controller")
        if sc_controller_installed:
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
        # Create a new window for the dialog
        self.warning_dialog = Gtk.Window(title="Faugus Launcher")
        self.warning_dialog.set_decorated(False)
        self.warning_dialog.set_resizable(False)

        # Create the Frame with border
        frame = Gtk.Frame()
        frame.set_label_align(0.5, 0.5)
        frame.set_shadow_type(Gtk.ShadowType.ETCHED_IN)

        # Create the Grid
        grid = Gtk.Grid()
        frame.add(grid)

        # Load the image with GdkPixbuf
        image_path = "/usr/share/icons/faugus-launcher.png"
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)

        # Resize the image to 75x75 pixels
        pixbuf = pixbuf.scale_simple(75, 75, GdkPixbuf.InterpType.BILINEAR)

        # Create a Gtk.Image from the GdkPixbuf
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_margin_top(20)
        image.set_margin_start(20)
        image.set_margin_end(20)
        image.set_margin_bottom(20)
        grid.attach(image, 0, 0, 1, 1)

        # Create the Label
        label = Gtk.Label(label="UMU-Proton is updating. Please wait...")
        label.set_margin_bottom(20)
        label.set_margin_start(20)
        label.set_margin_end(20)
        grid.attach(label, 0, 1, 1, 1)

        # Add the frame to the window
        self.warning_dialog.add(frame)

        # Show the window
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

    def append_log_to_window(self, line):
        # Append the log line to the log window
        pass  # Implement your logic here

    def on_output(self, source, condition):
        if line := source.readline():
            self.check_game_output(line)
            # Determine where to show the log
            if "winetricks" in self.message:
                self.append_log_to_window(line)
            else:
                print(line, end='')
        return True  # Continue watching for more output

    def check_game_output(self, line):
        clean_line = remove_ansi_escape(line).strip()
        if any(keyword in clean_line for keyword in {"zenity", "Gtk-WARNING", "Gtk-Message", "pixbuf"}) or not clean_line:
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

    def show_exit_warning(self):
        # Extract the last part of the string
        parts = self.message.split()
        if parts:
            last_part = parts[-1].strip('"')  # Remove any surrounding quotes

            # Check if the file is a .reg file
            if last_part.endswith(".reg"):
                # Create a custom dialog
                dialog = Gtk.Dialog(title="Faugus Launcher", modal=True)
                dialog.set_resizable(False)

                # Create the Grids
                self.grid = Gtk.Grid()
                self.grid.set_row_spacing(20)
                self.grid.set_column_spacing(0)
                self.grid.set_margin_start(10)
                self.grid.set_margin_end(10)
                self.grid.set_margin_top(10)
                self.grid.set_margin_bottom(10)

                self.label = Gtk.Label(label="The keys and values were successfully added to the registry.")

                # Button Ok
                self.button_ok = Gtk.Button(label="Ok")
                self.button_ok.connect("clicked", lambda w: dialog.response(Gtk.ResponseType.OK))
                self.button_ok.set_size_request(150, -1)
                self.button_ok.set_halign(Gtk.Align.CENTER)

                self.grid.attach(self.label, 0, 0, 1, 1)
                self.grid.attach(self.button_ok, 0, 1, 1, 1)

                dialog.get_content_area().add(self.grid)

                # Show the dialog
                dialog.show_all()

                # Run the dialog and wait for response
                dialog.run()

                # Destroy the dialog after response
                dialog.destroy()

    def on_process_exit(self, pid, condition):
        if self.process.poll() is not None:
            GLib.idle_add(self.close_warning_dialog)
            GLib.idle_add(self.close_log_window)
            GLib.idle_add(self.show_exit_warning)
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
    parser = argparse.ArgumentParser(description="UMU-Proton Updater")
    parser.add_argument("message", help="The message to be processed")
    parser.add_argument("command", nargs='?', default=None, help="The command to be executed (optional)")

    args = parser.parse_args()

    sc_controller_installed = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
        "/usr/local/bin/sc-controller")
    if sc_controller_installed:
        if "SC_CONTROLLER=1" in args.message:
            atexit.register(stop_scc_daemon)

    handle_command(args.message, args.command)


if __name__ == "__main__":
    main()
