#!/usr/bin/env python3

import gi
gi.require_version("Gtk", "3.0")  # Certifique-se de especificar a versão antes de importar Gtk
from gi.repository import Gtk, GLib
import sys
import subprocess

class UMUProtonUpdater:
    def __init__(self, message):
        # Inicia o subprocesso
        self.process = subprocess.Popen(
            ["/bin/bash", "-c", message],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Display the warning message
        self.show_warning_dialog()

        # Monitora a saída do subprocesso
        GLib.io_add_watch(self.process.stdout, GLib.IO_IN, self.check_game_output)
        GLib.io_add_watch(self.process.stderr, GLib.IO_IN, self.check_game_output)

    def show_warning_dialog(self):
        # Display the warning message while UMU-Run is updating
        self.warning_dialog = Gtk.MessageDialog(
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="UMU-Proton is updating. Please wait..."
        )

        self.warning_dialog.show()

    def check_game_output(self, fd, condition):
        # Read the game process output
        line = fd.readline()
        if not line:
            return False  # Remove the IO watch if no more lines

        # Check if the desired message was found in UMU-Run output
        if "Using UMU-Proton" in line or "UMU-Proton is up to date" in line:
            # Close the warning dialog after a short delay
            GLib.timeout_add_seconds(2, self.close_warning_dialog)
            return False  # Remove the IO watch since we no longer need to monitor the process output

        return True  # Continue monitoring the process output

    def close_warning_dialog(self):
        # Close the warning dialog
        self.warning_dialog.destroy()
        Gtk.main_quit()
        return False  # Stop the timeout function

def main():
    message = sys.argv[1]

    updater = UMUProtonUpdater(message)
    Gtk.main()
    updater.process.wait()  # Wait for the UMU-Run process to finish
    sys.exit(0)  # Exit with success status

if __name__ == "__main__":
    main()
