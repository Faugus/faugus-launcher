#!/usr/bin/python3

import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('AppIndicator3', '0.1')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, AppIndicator3
from PIL import Image

config_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
faugus_launcher_dir = f'{config_dir}/faugus-launcher'
prefixes_dir = f'{faugus_launcher_dir}/prefixes'
icons_dir = f'{faugus_launcher_dir}/icons'
config_file_dir = f'{faugus_launcher_dir}/config.ini'
share_dir = os.getenv('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
app_dir = f'{share_dir}/applications'
faugus_png = "/usr/share/icons/faugus-launcher.png"
tray_icon = "/usr/share/icons/faugus-launcher.png"
faugus_run = "/usr/bin/faugus-run"
faugus_proton_manager = "/usr/bin/faugus-proton-manager"
umu_run = "/usr/bin/umu-run"
mangohud_dir = "/usr/bin/mangohud"
gamemoderun = "/usr/bin/gamemoderun"
latest_games = f'{faugus_launcher_dir}/latest-games.txt'

lock_file_path = os.path.join(share_dir, "faugus-launcher/faugus_launcher.lock")
lock_file = None

def is_already_running():
    current_pid = str(os.getpid())

    if os.path.exists(lock_file_path):
        with open(lock_file_path, 'r') as lock_file:
            lock_pid = lock_file.read().strip()
            try:
                os.kill(int(lock_pid), 0)
                return True
            except OSError:
                pass

    with open(lock_file_path, 'w') as lock_file:
        lock_file.write(current_pid)
    return False

def get_desktop_dir():
    try:
        # Run the command and capture its output
        desktop_dir = subprocess.check_output(['xdg-user-dir', 'DESKTOP'], text=True).strip()
        return desktop_dir
    except FileNotFoundError:
        print("xdg-user-dir not found; falling back to ~/Desktop")
        # xdg-user-dir is not installed, fallback to ~/Desktop
        return os.path.expanduser('~/Desktop')
    except subprocess.CalledProcessError:
        print("Error running xdg-user-dir; falling back to ~/Desktop")
        # xdg-user-dir command failed for some other reason
        return os.path.expanduser('~/Desktop')

desktop_dir = get_desktop_dir()


class Main(Gtk.Window):
    def __init__(self):
        # Initialize the main window with title and default size
        Gtk.Window.__init__(self, title="Faugus Launcher")
        self.set_default_size(400, 620)
        self.set_resizable(False)
        self.set_icon_from_file(faugus_png)

        self.game_running = None
        self.system_tray = False
        self.start_boot = False

        self.games = []
        self.processos = {}

        # Define the configuration path
        config_path = faugus_launcher_dir
        # Create the configuration directory if it doesn't exist
        if not os.path.exists(config_path):
            os.makedirs(config_path)
        self.working_directory = config_path
        os.chdir(self.working_directory)

        config_file = config_file_dir
        if not os.path.exists(config_file):
            self.save_config("False", prefixes_dir, "False", "False", "False", "GE-Proton", "True", "False", "False", "False")

        self.games = []

        # Create main box and its components
        box_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_bottom = Gtk.Box()

        # Create buttons for adding, editing, and deleting games
        self.button_add = Gtk.Button()
        self.button_add.connect("clicked", self.on_button_add_clicked)
        self.button_add.set_can_focus(False)
        self.button_add.set_size_request(50, 50)
        self.button_add.set_margin_top(10)
        self.button_add.set_margin_start(10)
        self.button_add.set_margin_end(10)

        label_add = Gtk.Label(label="New")
        label_add.set_margin_start(0)
        label_add.set_margin_end(0)
        label_add.set_margin_top(0)
        label_add.set_margin_bottom(0)

        self.button_add.add(label_add)

        self.button_edit = Gtk.Button()
        self.button_edit.connect("clicked", self.on_button_edit_clicked)
        self.button_edit.set_can_focus(False)
        self.button_edit.set_size_request(50, 50)
        self.button_edit.set_margin_top(10)
        self.button_edit.set_margin_start(10)
        self.button_edit.set_margin_end(10)

        label_edit = Gtk.Label(label="Edit")
        label_edit.set_margin_start(0)
        label_edit.set_margin_end(0)
        label_edit.set_margin_top(0)
        label_edit.set_margin_bottom(0)

        self.button_edit.add(label_edit)

        self.button_delete = Gtk.Button()
        self.button_delete.connect("clicked", self.on_button_delete_clicked)
        self.button_delete.set_can_focus(False)
        self.button_delete.set_size_request(50, 50)
        self.button_delete.set_margin_top(10)
        self.button_delete.set_margin_start(10)
        self.button_delete.set_margin_end(10)

        label_delete = Gtk.Label(label="Del")
        label_delete.set_margin_start(0)
        label_delete.set_margin_end(0)
        label_delete.set_margin_top(0)
        label_delete.set_margin_bottom(0)

        self.button_delete.add(label_delete)

        # Create button for killing processes
        button_kill = Gtk.Button()
        button_kill.connect("clicked", self.on_button_kill_clicked)
        button_kill.set_can_focus(False)
        button_kill.set_tooltip_text("Force close all running games")
        button_kill.set_size_request(50, 50)
        button_kill.set_margin_top(10)
        button_kill.set_margin_end(10)
        button_kill.set_margin_bottom(10)

        label_kill = Gtk.Label(label="Kill")
        label_kill.set_margin_start(0)
        label_kill.set_margin_end(0)
        label_kill.set_margin_top(0)
        label_kill.set_margin_bottom(0)

        button_kill.add(label_kill)

        # Create button for settings
        button_settings = Gtk.Button()
        button_settings.connect("clicked", self.on_button_settings_clicked)
        button_settings.set_can_focus(False)
        button_settings.set_size_request(50, 50)
        button_settings.set_image(Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON))
        button_settings.set_margin_top(10)
        button_settings.set_margin_start(10)
        button_settings.set_margin_bottom(10)

        # Create button for launching games
        self.button_play = Gtk.Button()
        self.button_play.connect("clicked", self.on_button_play_clicked)
        self.button_play.set_can_focus(False)
        self.button_play.set_size_request(150, 50)
        self.button_play.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))
        self.button_play.set_margin_top(10)
        self.button_play.set_margin_end(10)
        self.button_play.set_margin_bottom(10)

        self.entry_search = Gtk.Entry()
        self.entry_search.set_placeholder_text("Search...")
        self.entry_search.connect("changed", self.on_search_changed)
        self.entry_search.set_size_request(-1, 50)
        self.entry_search.set_margin_top(10)
        self.entry_search.set_margin_start(10)
        self.entry_search.set_margin_bottom(10)
        self.entry_search.set_margin_end(10)

        # Create scrolled window for game list
        scroll_box = Gtk.ScrolledWindow()
        scroll_box.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll_box.set_margin_top(10)
        scroll_box.set_margin_end(10)

        self.last_clicked_row = None
        self.last_click_time = 0

        # Create list box for displaying games
        self.game_list = Gtk.ListBox(halign=Gtk.Align.START, valign=Gtk.Align.START)
        self.game_list.connect("button-release-event", self.on_button_release_event)

        self.connect("key-press-event", self.on_key_press_event)

        scroll_box.add(self.game_list)
        self.load_games()

        # Pack left and scrolled box into the top box
        box_top.pack_start(box_left, False, True, 0)
        box_top.pack_start(box_right, True, True, 0)

        # Pack buttons into the left box
        box_left.pack_start(self.button_add, False, False, 0)
        box_left.pack_start(self.button_edit, False, False, 0)
        box_left.pack_start(self.button_delete, False, False, 0)

        box_right.pack_start(scroll_box, True, True, 0)

        # Pack buttons and other components into the bottom box
        box_bottom.pack_start(button_settings, False, False, 0)
        box_bottom.pack_start(self.entry_search, True, True, 0)
        box_bottom.pack_end(self.button_play, False, False, 0)
        box_bottom.pack_end(button_kill, False, False, 0)

        # Pack top and bottom boxes into the main box
        box_main.pack_start(box_top, True, True, 0)
        box_main.pack_end(box_bottom, False, True, 0)
        self.add(box_main)

        self.button_edit.set_sensitive(False)
        self.button_delete.set_sensitive(False)
        self.button_play.set_sensitive(False)

        self.game_running2 = False

        self.game_list.select_row(self.game_list.get_row_at_index(0))
        self.update_button_sensitivity(self.game_list.get_selected_row())

        # Set signal handler for child process termination
        signal.signal(signal.SIGCHLD, self.on_child_process_closed)


        self.load_config()
        # Create the tray indicator
        self.indicator = AppIndicator3.Indicator.new(
            "Faugus Launcher",  # Application name
            tray_icon,         # Path to the icon
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_menu(self.create_tray_menu())  # Tray menu
        self.indicator.set_title("Faugus Launcher")  # Change the tooltip text

        if self.system_tray:
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.connect("delete-event", self.on_window_delete_event)

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

            self.system_tray = config_dict.get('system-tray', 'False') == 'True'
            self.start_boot = config_dict.get('start-boot', 'False') == 'True'
        else:
            self.save_config(False, '', "False", "False", "False", "GE-Proton", "True", "False", "False", "False")

    def create_tray_menu(self):
        # Create the tray menu
        menu = Gtk.Menu()

        # Add game items from latest-games.txt
        games_file_path = latest_games
        if os.path.exists(games_file_path):
            with open(games_file_path, "r") as games_file:
                for line in games_file:
                    game_name = line.strip()
                    if game_name:
                        game_item = Gtk.MenuItem(label=game_name)
                        game_item.connect("activate", self.on_game_selected, game_name)
                        menu.append(game_item)

        # Add a separator between game items and the other menu items
        separator = Gtk.SeparatorMenuItem()
        menu.append(separator)

        # Item to restore the window
        restore_item = Gtk.MenuItem(label="Open Faugus Launcher")
        restore_item.connect("activate", self.restore_window)
        menu.append(restore_item)

        # Item to quit the application
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit_activate)
        menu.append(quit_item)

        menu.show_all()
        return menu

    def on_game_selected(self, widget, game_name):
        # Find the game in the list by name and select it
        for row in self.game_list.get_children():
            hbox = row.get_child()
            game_label = hbox.get_children()[1]
            if game_label.get_text() == game_name:
                self.game_list.select_row(row)
                break
        # Call the function to run the selected game
        self.on_button_play_clicked(widget)

    def on_window_delete_event(self, widget, event):
        # Only prevent closing when system tray is active
        self.load_config()
        if self.system_tray:
            self.hide()  # Minimize the window instead of closing
            return True  # Stop the event to keep the app running
        return False  # Allow the window to close

    def restore_window(self, widget):
        # Restore the window when clicking the tray icon
        self.show_all()
        self.present()

    def on_quit_activate(self, widget):
        if os.path.exists(lock_file_path):
                os.remove(lock_file_path)

        # Quit the application
        Gtk.main_quit()

    def load_games(self):
        # Load games from file
        try:
            with open("games.txt", "r") as file:
                for line in file:
                    data = line.strip().split(";")
                    if len(data) >= 5:
                        title, path, prefix, launch_arguments, game_arguments = data[:5]
                        if len(data) >= 10:
                            mangohud = data[5]
                            gamemode = data[6]
                            sc_controller = data[7]
                            protonfix = data[8]
                            runner = data[9]
                        else:
                            mangohud = ""
                            gamemode = ""
                            sc_controller = ""
                            protonfix = ""
                            runner = ""
                        game = Game(title, path, prefix, launch_arguments, game_arguments, mangohud, gamemode,
                                    sc_controller, protonfix, runner)
                        self.games.append(game)
                self.games = sorted(self.games, key=lambda x: x.title.lower())
                self.filtered_games = self.games[:]  # Initialize filtered_games
                self.game_list.foreach(Gtk.Widget.destroy)
                for game in self.filtered_games:
                    self.add_item_list(game)
        except FileNotFoundError:
            pass

    def add_item_list(self, game):
        # Add a game item to the list
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_border_width(5)
        hbox.set_size_request(400, -1)

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        game_icon = f'{icons_dir}/{title_formatted}.ico'

        game_label = Gtk.Label.new(game.title)

        if os.path.isfile(game_icon):
            pass
        else:
            game_icon = faugus_png

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(game_icon)
        scaled_pixbuf = pixbuf.scale_simple(40, 40, GdkPixbuf.InterpType.BILINEAR)
        image = Gtk.Image.new_from_file(game_icon)
        image.set_from_pixbuf(scaled_pixbuf)
        image.set_margin_end(10)

        #self.button_shortcut_icon.set_image(image)

        hbox.pack_start(image, False, False, 0)
        hbox.pack_start(game_label, False, False, 0)

        listbox_row = Gtk.ListBoxRow()
        listbox_row.add(hbox)
        listbox_row.set_activatable(False)
        listbox_row.set_can_focus(False)
        listbox_row.set_selectable(True)
        self.game_list.add(listbox_row)

        hbox.set_halign(Gtk.Align.CENTER)
        listbox_row.set_valign(Gtk.Align.START)

    def on_search_changed(self, entry):
        search_text = entry.get_text().lower()
        # Filter games based on the search text
        self.filtered_games = [game for game in self.games if search_text in game.title.lower()]

        self.game_list.foreach(Gtk.Widget.destroy)  # Clear the current list

        if self.filtered_games:  # If there are filtered games, add them
            for game in self.filtered_games:
                self.add_item_list(game)

            # Select the first item in the list
            self.game_list.select_row(self.game_list.get_row_at_index(0))
        else:  # If there are no games, add a message or leave the list empty
            pass

        self.game_list.show_all()  # Show all items in the list, including the message
        self.update_button_sensitivity(self.game_list.get_selected_row())

    def on_key_press_event(self, listbox, event):
        # Check for arrow key press
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            # Grab focus on the ListBox to ensure navigation works
            self.game_list.grab_focus()

            # Get the list of rows in the ListBox
            rows = self.game_list.get_children()
            selected_row = self.game_list.get_selected_row()

            # Handle Up arrow key
            if event.keyval == Gdk.KEY_Up:
                if selected_row:
                    current_index = rows.index(selected_row)
                    if current_index > 0:
                        self.game_list.select_row(rows[current_index - 1])
                        self.update_button_sensitivity(rows[current_index - 1])
            # Handle Down arrow key
            elif event.keyval == Gdk.KEY_Down:
                if selected_row:
                    current_index = rows.index(selected_row)
                    if current_index < len(rows) - 1:
                        self.game_list.select_row(rows[current_index + 1])
                        self.update_button_sensitivity(rows[current_index + 1])

        # Check for Enter key press
        if event.keyval == Gdk.KEY_Return:
            selected_row = self.game_list.get_selected_row()
            if selected_row:
                # Simulate double-click behavior
                hbox = selected_row.get_child()
                game_label = hbox.get_children()[1]
                title = game_label.get_text()

                # Check if the game is already running
                if title not in self.processos:
                    widget = self.button_play
                    self.on_button_play_clicked(widget)
                else:
                    dialog = Gtk.MessageDialog(title=title, text=f"'{title}' is already running.",
                                               buttons=Gtk.ButtonsType.OK, parent=self)
                    dialog.set_resizable(False)
                    dialog.set_modal(True)
                    dialog.set_icon_from_file(faugus_png)
                    dialog.run()
                    dialog.destroy()

        # Check for Delete key press
        if event.keyval == Gdk.KEY_Delete:
            selected_row = self.game_list.get_selected_row()
            if selected_row:
                self.on_button_delete_clicked(self.button_delete)

            # Stop further event propagation
            return True

    def on_button_release_event(self, listbox, event):
        # Handle button release event

        if event.type == Gdk.EventType.BUTTON_RELEASE and event.button == Gdk.BUTTON_PRIMARY:
            current_row = listbox.get_row_at_y(event.y)
            current_time = event.time
            if current_row == self.last_clicked_row and current_time - self.last_click_time < 500:
                # Double-click detected
                if current_row:
                    hbox = current_row.get_child()
                    game_label = hbox.get_children()[1]
                    title = game_label.get_text()

                    # Check if the game is already running
                    if title not in self.processos:
                        widget = self.button_play
                        self.on_button_play_clicked(widget)
                    else:
                        dialog = Gtk.MessageDialog(title=title, text=f"'{title}' is already running.",
                                                   buttons=Gtk.ButtonsType.OK, parent=self)
                        dialog.set_resizable(False)
                        dialog.set_modal(True)
                        dialog.set_icon_from_file(faugus_png)
                        dialog.run()
                        dialog.destroy()
            else:
                # Single-click, update last click details and enable buttons
                self.last_clicked_row = current_row
                self.last_click_time = current_time
                self.update_button_sensitivity(current_row)

    def update_button_sensitivity(self, row):
        # Enable buttons based on the selected row
        if row:
            hbox = row.get_child()
            game_label = hbox.get_children()[1]
            title = game_label.get_text()

            self.button_edit.set_sensitive(True)
            self.button_delete.set_sensitive(True)

            if title in self.processos:
                self.button_play.set_sensitive(False)
                self.button_play.set_image(
                    Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", Gtk.IconSize.BUTTON))
            else:
                self.button_play.set_sensitive(True)
                self.button_play.set_image(
                    Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))
        else:
            # Disable buttons if no row is selected
            self.button_edit.set_sensitive(False)
            self.button_delete.set_sensitive(False)
            self.button_play.set_sensitive(False)

    def load_close_onlaunch(self):
        config_file = config_file_dir
        close_onlaunch = False
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_data = f.read().splitlines()
            config_dict = dict(line.split('=') for line in config_data)
            close_onlaunch_value = config_dict.get('close-onlaunch', '').strip('"')
            if close_onlaunch_value.lower() == 'true':
                close_onlaunch = True
        return close_onlaunch

    def on_button_settings_clicked(self, widget):
        # Handle add button click event
        settings_dialog = Settings(self)
        settings_dialog.connect("response", self.on_settings_dialog_response, settings_dialog)

        settings_dialog.show()

    def on_settings_dialog_response(self, dialog, response_id, settings_dialog):
        self.checkbox_discrete_gpu = settings_dialog.checkbox_discrete_gpu
        self.checkbox_close_after_launch = settings_dialog.checkbox_close_after_launch
        self.checkbox_splash_disable = settings_dialog.checkbox_splash_disable
        self.checkbox_system_tray = settings_dialog.checkbox_system_tray
        self.checkbox_start_boot = settings_dialog.checkbox_start_boot
        self.entry_default_prefix = settings_dialog.entry_default_prefix

        self.checkbox_mangohud = settings_dialog.checkbox_mangohud
        self.checkbox_gamemode = settings_dialog.checkbox_gamemode
        self.checkbox_sc_controller = settings_dialog.checkbox_sc_controller
        self.combo_box_runner = settings_dialog.combo_box_runner

        checkbox_state = self.checkbox_close_after_launch.get_active()
        checkbox_discrete_gpu_state = self.checkbox_discrete_gpu.get_active()
        checkbox_splash_disable = self.checkbox_splash_disable.get_active()
        checkbox_system_tray = self.checkbox_system_tray.get_active()
        checkbox_start_boot = self.checkbox_start_boot.get_active()
        default_prefix = self.entry_default_prefix.get_text()

        mangohud_state = self.checkbox_mangohud.get_active()
        gamemode_state = self.checkbox_gamemode.get_active()
        sc_controller_state = self.checkbox_sc_controller.get_active()
        default_runner = self.combo_box_runner.get_active_text()

        if default_runner == "UMU-Proton Latest":
            default_runner = ""
        if default_runner == "GE-Proton Latest (default)":
            default_runner = "GE-Proton"

        # Handle dialog response
        if response_id == Gtk.ResponseType.OK:
            if default_prefix == "":
                settings_dialog.entry_default_prefix.get_style_context().add_class("entry")
            else:
                self.save_config(checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot)
                self.manage_autostart_file(checkbox_start_boot)
                if checkbox_system_tray:
                    self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                    if not hasattr(self, "window_delete_event_connected") or not self.window_delete_event_connected:
                        self.connect("delete-event", self.on_window_delete_event)
                        self.window_delete_event_connected = True
                    self.indicator.set_menu(self.create_tray_menu())
                else:
                    self.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
                    if hasattr(self, "window_delete_event_connected") and self.window_delete_event_connected:
                        self.disconnect_by_func(self.on_window_delete_event)
                        self.window_delete_event_connected = False

                settings_dialog.destroy()

        else:
            settings_dialog.destroy()

    def manage_autostart_file(self, checkbox_start_boot):
        # Define the path for the autostart file
        autostart_path = os.path.expanduser('~/.config/autostart/faugus-launcher.desktop')
        autostart_dir = os.path.dirname(autostart_path)

        # Ensure the autostart directory exists
        if not os.path.exists(autostart_dir):
            os.makedirs(autostart_dir)

        if checkbox_start_boot:
            # Create the autostart file if it does not exist
            if not os.path.exists(autostart_path):
                with open(autostart_path, "w") as f:
                    f.write("""[Desktop Entry]
    Categories=Utility;
    Exec=faugus-launcher %f hide
    Icon=faugus-launcher
    MimeType=application/x-ms-dos-executable;application/x-msi;application/x-ms-shortcut;application/x-bat;text/x-ms-regedit
    Name=Faugus Launcher
    Type=Application
    """)
        else:
            # Delete the autostart file if it exists
            if os.path.exists(autostart_path):
                os.remove(autostart_path)

    def on_button_play_clicked(self, widget):
        if not (listbox_row := self.game_list.get_selected_row()):
            return
        # Get the selected game's title
        hbox = listbox_row.get_child()
        game_label = hbox.get_children()[1]
        title = game_label.get_text()
        # Find the selected game object
        game = next((j for j in self.games if j.title == title), None)
        if game:
            # Format the title for command execution
            title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
            title_formatted = title_formatted.replace(' ', '-')
            title_formatted = '-'.join(title_formatted.lower().split())

            # Extract game launch information
            launch_arguments = game.launch_arguments
            path = game.path
            prefix = game.prefix
            game_arguments = game.game_arguments
            mangohud = game.mangohud
            sc_controller = game.sc_controller
            protonfix = game.protonfix
            runner = game.runner

            gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
            gamemode = game.gamemode if gamemode_enabled else ""

            # Get the directory containing the executable
            game_directory = os.path.dirname(path)

            command_parts = []

            # Add command parts if they are not empty
            if mangohud:
                command_parts.append(mangohud)
            if sc_controller:
                command_parts.append(sc_controller)
            if prefix:
                command_parts.append(f'WINEPREFIX={prefix}')
            if protonfix:
                command_parts.append(f'GAMEID={protonfix}')
            else:
                command_parts.append(f'GAMEID={title_formatted}')
            if runner:
                command_parts.append(f'PROTONPATH={runner}')
            if gamemode:
                command_parts.append(gamemode)
            if launch_arguments:
                command_parts.append(launch_arguments)

            # Add the fixed command and remaining arguments
            command_parts.append(f'"{umu_run}"')
            if path:
                command_parts.append(f'"{path}"')
            if game_arguments:
                command_parts.append(f'"{game_arguments}"')

            # Join all parts into a single command
            command = ' '.join(command_parts)
            print(command)

            # faugus-run path
            faugus_run_path = faugus_run

            # Save the game title to the latest_games.txt file
            self.update_latest_games_file(title)

            if os.path.exists(lock_file_path):
                    os.remove(lock_file_path)

            # Launch the game with subprocess
            if self.load_close_onlaunch():
                subprocess.Popen([sys.executable, faugus_run_path, command], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, cwd=game_directory)
                sys.exit()
            else:
                processo = subprocess.Popen([sys.executable, faugus_run_path, command], cwd=game_directory)
                self.processos[title] = processo
                self.button_play.set_sensitive(False)
                self.button_play.set_image(
                    Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", Gtk.IconSize.BUTTON))

    def update_latest_games_file(self, title):
        # Read the existing games from the file, if it exists
        try:
            with open(latest_games, 'r') as f:
                games = f.read().splitlines()
        except FileNotFoundError:
            games = []

        # Remove the game if it already exists in the list and add it to the top
        if title in games:
            games.remove(title)
        games.insert(0, title)

        # Keep only the 5 most recent games
        games = games[:5]

        # Write the updated list back to the file
        with open(latest_games, 'w') as f:
            f.write('\n'.join(games))
        self.indicator.set_menu(self.create_tray_menu())

    def on_button_kill_clicked(self, widget):
        # Handle kill button click event
        subprocess.run(r"""
    for pid in $(ls -l /proc/*/exe 2>/dev/null | grep -E 'wine(64)?-preloader|wineserver|winedevice.exe' | awk -F'/' '{print $3}'); do
        kill -9 "$pid"
    done
""", shell=True)
        self.game_running = None
        self.game_running2 = False

    def on_button_add_clicked(self, widget):
        file_path=""
        # Handle add button click event
        add_game_dialog = AddGame(self, self.game_running2, file_path)
        add_game_dialog.connect("response", self.on_dialog_response, add_game_dialog)

        add_game_dialog.show()

    def on_button_edit_clicked(self, widget):
        file_path=""
        if not (listbox_row := self.game_list.get_selected_row()):
            return
        hbox = listbox_row.get_child()
        game_label = hbox.get_children()[1]
        title = game_label.get_text()
        if game := next((j for j in self.games if j.title == title), None):
            if game.title in self.processos:
                self.game_running2 = True
            else:
                self.game_running2 = False
            edit_game_dialog = AddGame(self, self.game_running2, file_path)
            edit_game_dialog.connect("response", self.on_edit_dialog_response, edit_game_dialog, game)
            edit_game_dialog.entry_title.set_text(game.title)
            edit_game_dialog.entry_path.set_text(game.path)
            edit_game_dialog.entry_prefix.set_text(game.prefix)
            edit_game_dialog.entry_launch_arguments.set_text(game.launch_arguments)
            edit_game_dialog.entry_game_arguments.set_text(game.game_arguments)
            edit_game_dialog.set_title(f"Edit {game.title}")
            edit_game_dialog.entry_protonfix.set_text(game.protonfix)

            model = edit_game_dialog.combo_box_runner.get_model()
            index_to_activate = 0
            game_runner = game.runner

            if game.runner == "GE-Proton":
                game_runner = "GE-Proton Latest (default)"
            if game.runner == "":
                game_runner = "UMU-Proton Latest"

            for i, row in enumerate(model):
                if row[0] == game_runner:
                    index_to_activate = i
                    break
            if not game_runner:
                index_to_activate = 1
            edit_game_dialog.combo_box_runner.set_active(index_to_activate)

            mangohud_status = False
            gamemode_status = False
            sc_controller_status = False
            with open("games.txt", "r") as file:
                for line in file:
                    fields = line.strip().split(";")
                    if len(fields) >= 8 and fields[0] == game.title:
                        mangohud_status = fields[5] == "MANGOHUD=1"
                        gamemode_status = fields[6] == "gamemoderun"
                        sc_controller_status = fields[7] == "SC_CONTROLLER=1"

            mangohud_enabled = os.path.exists(mangohud_dir)
            if mangohud_enabled:
                edit_game_dialog.checkbox_mangohud.set_active(mangohud_status)
            gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
            if gamemode_enabled:
                edit_game_dialog.checkbox_gamemode.set_active(gamemode_status)
            sc_controller_enabled = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
                "/usr/local/bin/sc-controller")
            if sc_controller_enabled:
                edit_game_dialog.checkbox_sc_controller.set_active(sc_controller_status)
            edit_game_dialog.check_existing_shortcut()

            image = self.set_image_shortcut_icon(game.title, edit_game_dialog.icons_path, edit_game_dialog.icon_temp)
            edit_game_dialog.button_shortcut_icon.set_image(image)
            edit_game_dialog.entry_title.set_sensitive(False)

            if self.game_running2:
                edit_game_dialog.button_winecfg.set_sensitive(False)
                edit_game_dialog.button_winecfg.set_tooltip_text(f'{game.title} is running. Please close it first.')
                edit_game_dialog.button_winetricks.set_sensitive(False)
                edit_game_dialog.button_winetricks.set_tooltip_text(f'{game.title} is running. Please close it first.')
                edit_game_dialog.button_run.set_sensitive(False)
                edit_game_dialog.button_run.set_tooltip_text(f'{game.title} is running. Please close it first.')

            edit_game_dialog.show()

    def set_image_shortcut_icon(self, title, icons_path, icon_temp):

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        # Check if the icon file exists
        icon_path = os.path.join(icons_path, f"{title_formatted}.ico")

        if os.path.exists(icon_path):
            shutil.copy(icon_path, icon_temp)
        if not os.path.exists(icon_path):
            icon_temp = faugus_png

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_temp)
        scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_file(icon_temp)
        image.set_from_pixbuf(scaled_pixbuf)

        return image

    def on_button_delete_clicked(self, widget):
        if not (listbox_row := self.game_list.get_selected_row()):
            return
        # Retrieve the selected game's title
        hbox = listbox_row.get_child()
        game_label = hbox.get_children()[1]
        title = game_label.get_text()
        if game := next((j for j in self.games if j.title == title), None):
            # Display confirmation dialog
            confirmation_dialog = ConfirmationDialog(self, title)
            response = confirmation_dialog.run()

            if response == Gtk.ResponseType.YES:
                # Remove game and associated files if required
                if confirmation_dialog.get_remove_prefix_state():
                    game_prefix = game.prefix
                    prefix_path = os.path.expanduser(game_prefix)
                    try:
                        shutil.rmtree(prefix_path)
                    except FileNotFoundError:
                        pass

                # Remove the shortcut
                self.remove_shortcut(game)

                self.games.remove(game)
                self.save_games()
                self.update_list()

                self.button_edit.set_sensitive(False)
                self.button_delete.set_sensitive(False)
                self.button_play.set_sensitive(False)

                # Remove the game from the latest-games file if it exists
                self.remove_game_from_latest_games(title)

            confirmation_dialog.destroy()

    def remove_game_from_latest_games(self, title):
        try:
            # Read the current list of recent games
            with open(latest_games, 'r') as f:
                recent_games = f.read().splitlines()

            # Remove the game title if it exists in the list
            if title in recent_games:
                recent_games.remove(title)

                # Write the updated list back, maintaining max 5 entries
                with open(latest_games, 'w') as f:
                    f.write("\n".join(recent_games[:5]))
            self.indicator.set_menu(self.create_tray_menu())

        except FileNotFoundError:
            pass  # Ignore if the file doesn't exist yet

    def on_dialog_response(self, dialog, response_id, add_game_dialog):
        # Handle dialog response
        if response_id == Gtk.ResponseType.OK:
            if not add_game_dialog.validate_fields(entry="path+prefix"):
                # If fields are not validated, return and keep the dialog open
                return True
            # Proceed with adding the game
            # Get game information from dialog fields
            title = add_game_dialog.entry_title.get_text()
            path = add_game_dialog.entry_path.get_text()
            launch_arguments = add_game_dialog.entry_launch_arguments.get_text()
            game_arguments = add_game_dialog.entry_game_arguments.get_text()
            prefix = add_game_dialog.entry_prefix.get_text()
            protonfix = add_game_dialog.entry_protonfix.get_text()
            runner = add_game_dialog.combo_box_runner.get_active_text()

            title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
            title_formatted = title_formatted.replace(' ', '-')
            title_formatted = '-'.join(title_formatted.lower().split())

            # Concatenate game information
            game_info = (f"{title};{path};{prefix};{launch_arguments};{game_arguments}")

            # Determine mangohud and gamemode status
            mangohud = "MANGOHUD=1" if add_game_dialog.checkbox_mangohud.get_active() else ""
            gamemode = "gamemoderun" if add_game_dialog.checkbox_gamemode.get_active() else ""
            sc_controller = "SC_CONTROLLER=1" if add_game_dialog.checkbox_sc_controller.get_active() else ""

            if runner == "UMU-Proton Latest":
                runner = ""
            if runner == "GE-Proton Latest (default)":
                runner = "GE-Proton"

            game_info += f";{mangohud};{gamemode};{sc_controller};{protonfix};{runner}\n"

            # Write game info to file
            with open("games.txt", "a") as file:
                file.write(game_info)

            # Create Game object and update UI
            game = Game(title, path, prefix, launch_arguments, game_arguments, mangohud, gamemode, sc_controller, protonfix, runner)
            self.games.append(game)

            # Determine the state of the shortcut checkbox
            shortcut_state = add_game_dialog.checkbox_shortcut.get_active()

            icon_temp = os.path.expanduser(add_game_dialog.icon_temp)
            icon_final = f'{add_game_dialog.icons_path}/{title_formatted}.ico'

            # Call add_remove_shortcut method
            self.add_shortcut(game, shortcut_state, icon_temp, icon_final)

            self.add_item_list(game)
            self.update_list()

            # Select the added game
            self.select_game_by_title(title)

        else:
            if os.path.isfile(add_game_dialog.icon_temp):
                os.remove(add_game_dialog.icon_temp)
            if os.path.isdir(add_game_dialog.icon_directory):
                shutil.rmtree(add_game_dialog.icon_directory)
            add_game_dialog.destroy()

        # Ensure the dialog is destroyed when canceled
        add_game_dialog.destroy()

    def select_game_by_title(self, title):
        # Select an item from the list based on title
        for row in self.game_list.get_children():
            hbox = row.get_child()
            game_label = hbox.get_children()[1]
            if game_label.get_text() == title:
                self.game_list.select_row(row)
                break
        self.button_edit.set_sensitive(True)
        self.button_delete.set_sensitive(True)
        self.button_play.set_sensitive(True)
        self.button_play.set_image(
            Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))

    def on_edit_dialog_response(self, dialog, response_id, edit_game_dialog, game):
        # Handle edit dialog response
        if response_id == Gtk.ResponseType.OK:
            if not edit_game_dialog.validate_fields(entry="path+prefix"):
                # If fields are not validated, return and keep the dialog open
                return True
            # Update game object with new information
            game.title = edit_game_dialog.entry_title.get_text()
            game.path = edit_game_dialog.entry_path.get_text()
            game.prefix = edit_game_dialog.entry_prefix.get_text()
            game.launch_arguments = edit_game_dialog.entry_launch_arguments.get_text()
            game.game_arguments = edit_game_dialog.entry_game_arguments.get_text()
            game.mangohud = edit_game_dialog.checkbox_mangohud.get_active()
            game.gamemode = edit_game_dialog.checkbox_gamemode.get_active()
            game.sc_controller = edit_game_dialog.checkbox_sc_controller.get_active()
            game.protonfix = edit_game_dialog.entry_protonfix.get_text()
            game.runner = edit_game_dialog.combo_box_runner.get_active_text()

            # Handle the click event of the Create Shortcut button
            title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
            title_formatted = title_formatted.replace(' ', '-')
            title_formatted = '-'.join(title_formatted.lower().split())

            if game.runner == "UMU-Proton Latest":
                game.runner = ""
            if game.runner == "GE-Proton Latest (default)":
                game.runner = "GE-Proton"

            icon_temp = os.path.expanduser(edit_game_dialog.icon_temp)
            icon_final = f'{edit_game_dialog.icons_path}/{title_formatted}.ico'

            # Determine the state of the shortcut checkbox
            shortcut_state = edit_game_dialog.checkbox_shortcut.get_active()

            # Call add_remove_shortcut method
            self.add_shortcut(game, shortcut_state, icon_temp, icon_final)

            # Save changes and update UI
            self.save_games()
            self.update_list()

            # Select the game that was edited
            self.select_game_by_title(game.title)
        else:
            if os.path.isfile(edit_game_dialog.icon_temp):
                os.remove(edit_game_dialog.icon_temp)

        if os.path.isdir(edit_game_dialog.icon_directory):
            shutil.rmtree(edit_game_dialog.icon_directory)

        edit_game_dialog.destroy()

    def add_shortcut(self, game, shortcut_state, icon_temp, icon_final):

        # Check if the shortcut checkbox is checked
        if not shortcut_state:
            # Remove existing shortcut if it exists
            self.remove_shortcut(game)
            if os.path.isfile(os.path.expanduser(icon_temp)):
                os.rename(os.path.expanduser(icon_temp), icon_final)
            return

        if os.path.isfile(os.path.expanduser(icon_temp)):
            os.rename(os.path.expanduser(icon_temp), icon_final)

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        prefix = game.prefix
        path = game.path
        launch_arguments = game.launch_arguments
        game_arguments = game.game_arguments
        protonfix = game.protonfix
        runner = game.runner

        mangohud = "MANGOHUD=1" if game.mangohud else ""
        gamemode = "gamemoderun" if game.gamemode else ""
        sc_controller = "SC_CONTROLLER=1" if game.sc_controller else ""
        # Check if the icon file exists
        icons_path = icons_dir
        new_icon_path = f"{icons_dir}/{title_formatted}.ico"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        # Get the directory containing the executable
        game_directory = os.path.dirname(path)

        command_parts = []

        # Add command parts if they are not empty
        if mangohud:
            command_parts.append(mangohud)
        if sc_controller:
            command_parts.append(sc_controller)
        if prefix:
            command_parts.append(f'WINEPREFIX={prefix}')
        if protonfix:
            command_parts.append(f'GAMEID={protonfix}')
        else:
            command_parts.append(f'GAMEID={title_formatted}')
        if runner:
            command_parts.append(f'PROTONPATH={runner}')
        if gamemode:
            command_parts.append(gamemode)
        if launch_arguments:
            command_parts.append(launch_arguments)

        # Add the fixed command and remaining arguments
        command_parts.append(f"'{umu_run}'")
        if path:
            command_parts.append(f"'{path}'")
        if game_arguments:
            command_parts.append(f"'{game_arguments}'")

        # Join all parts into a single command
        command = ' '.join(command_parts)

        # Create a .desktop file
        desktop_file_content = f"""[Desktop Entry]
    Name={game.title}
    Exec={faugus_run} "{command}"
    Icon={new_icon_path}
    Type=Application
    Categories=Game;
    Path={game_directory}
    """

        # Check if the destination directory exists and create if it doesn't
        applications_directory = app_dir
        if not os.path.exists(applications_directory):
            os.makedirs(applications_directory)

        desktop_directory = desktop_dir
        if not os.path.exists(desktop_directory):
            os.makedirs(desktop_directory)

        applications_shortcut_path = f"{app_dir}/{title_formatted}.desktop"

        with open(applications_shortcut_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        # Make the .desktop file executable
        os.chmod(applications_shortcut_path, 0o755)

        # Copy the shortcut to Desktop
        desktop_shortcut_path = f"{desktop_dir}/{title_formatted}.desktop"
        shutil.copy(applications_shortcut_path, desktop_shortcut_path)

    def update_preview(self, dialog):
        if file_path := dialog.get_preview_filename():
            try:
                # Create an image widget for the thumbnail
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)

                # Resize the thumbnail if it's too large, maintaining the aspect ratio
                max_width = 400
                max_height = 400
                width = pixbuf.get_width()
                height = pixbuf.get_height()

                if width > max_width or height > max_height:
                    # Calculate the new width and height while maintaining the aspect ratio
                    ratio = min(max_width / width, max_height / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)

                image = Gtk.Image.new_from_pixbuf(pixbuf)
                dialog.set_preview_widget(image)
                dialog.set_preview_widget_active(True)
                dialog.get_preview_widget().set_size_request(max_width, max_height)
            except GLib.Error:
                dialog.set_preview_widget_active(False)
        else:
            dialog.set_preview_widget_active(False)

    def remove_shortcut(self, game):
        # Remove existing shortcut if it exists
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        desktop_file_path = f"{app_dir}/{title_formatted}.desktop"

        if os.path.exists(desktop_file_path):
            os.remove(desktop_file_path)

        # Remove shortcut from Desktop if exists
        desktop_shortcut_path = f"{desktop_dir}/{title_formatted}.desktop"
        if os.path.exists(desktop_shortcut_path):
            os.remove(desktop_shortcut_path)

        # Remove icon file
        icon_file_path = f"{icons_dir}/{title_formatted}.ico"
        if os.path.exists(icon_file_path):
            os.remove(icon_file_path)

    def remove_desktop_entry(self, game):
        # Remove the .desktop file from ~/.local/share/applications/
        desktop_file_path = f"{app_dir}/{game.title}.desktop"

        if os.path.exists(desktop_file_path):
            os.remove(desktop_file_path)

    def remove_shortcut_from_desktop(self, game):
        # Remove the shortcut from the desktop if it exists
        desktop_link_path = f"{desktop_dir}/{game.title}.desktop"

        if os.path.exists(desktop_link_path):
            os.remove(desktop_link_path)

    def update_list(self):
        # Update the game list
        for row in self.game_list.get_children():
            self.game_list.remove(row)

        self.games.clear()
        self.load_games()
        self.entry_search.set_text("")
        self.show_all()

    def on_child_process_closed(self, signum, frame):
        for title, processo in list(self.processos.items()):
            retcode = processo.poll()
            if retcode is not None:
                del self.processos[title]

                listbox_row = self.game_list.get_selected_row()
                if listbox_row:
                    hbox = listbox_row.get_child()
                    game_label = hbox.get_children()[1]
                    selected_title = game_label.get_text()

                    if selected_title not in self.processos:
                        self.button_play.set_sensitive(True)
                        self.button_play.set_image(
                            Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))
                    else:
                        self.button_play.set_sensitive(False)
                        self.button_play.set_image(
                            Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", Gtk.IconSize.BUTTON))

    def save_games(self):
        # Save game information to file
        with open("games.txt", "w") as file:
            for game in self.games:
                # Determine mangohud and gamemode values
                mangohud_value = "MANGOHUD=1" if game.mangohud else ""
                gamemode_value = "gamemoderun" if game.gamemode else ""
                sc_controller_value = "SC_CONTROLLER=1" if game.sc_controller else ""
                # Construct line with game information
                line = (f"{game.title};{game.path};{game.prefix};{game.launch_arguments};{game.game_arguments};"
                        f"{mangohud_value};{gamemode_value};{sc_controller_value};{game.protonfix};{game.runner}\n")
                file.write(line)

    def show_warning_message(self, message):
        # Show a warning message dialog
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.OK, text=message, )
        dialog.set_icon_from_file(faugus_png)
        dialog.run()
        dialog.destroy()

    def save_config(self, checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot):
        # Path to the configuration file
        config_file = os.path.join(self.working_directory, 'config.ini')

        # Dictionary to store existing configurations
        config = {}

        # Read the existing configuration file
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                for line in f:
                    key, value = line.strip().split('=', 1)
                    config[key] = value.strip('"')

        default_runner = (f'"{default_runner}"')

        # Update configurations with new values
        config['close-onlaunch'] = checkbox_state
        config['default-prefix'] = default_prefix
        config['mangohud'] = mangohud_state
        config['gamemode'] = gamemode_state
        config['sc-controller'] = sc_controller_state
        config['default-runner'] = default_runner
        config['discrete-gpu'] = checkbox_discrete_gpu_state
        config['splash-disable'] = checkbox_splash_disable
        config['system-tray'] = checkbox_system_tray
        config['start-boot'] = checkbox_start_boot

        # Write configurations back to the file
        with open(config_file, 'w') as f:
            for key, value in config.items():
                if key == 'default-prefix':
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f'{key}={value}\n')


class Settings(Gtk.Dialog):
    def __init__(self, parent):
        # Initialize the Settings dialog
        super().__init__(title="Settings", parent=parent)
        self.set_resizable(False)
        self.set_modal(True)
        self.parent = parent
        self.set_icon_from_file(faugus_png)

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        .paypal {
            color: black;
            background: white;
        }
        .kofi {
            color: white;
            background: #1AC0FF;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        # Widgets for prefix
        self.label_default_prefix = Gtk.Label(label="Default prefixes location")
        self.label_default_prefix.set_halign(Gtk.Align.START)

        self.entry_default_prefix = Gtk.Entry()
        self.entry_default_prefix.set_tooltip_text("/path/to/the/prefix")
        self.entry_default_prefix.connect("changed", self.on_entry_changed, self.entry_default_prefix)

        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        self.label_default_prefix_tools = Gtk.Label(label="Default prefix tools")
        self.label_default_prefix_tools.set_halign(Gtk.Align.START)

        # Widgets for runner
        self.label_runner = Gtk.Label(label="Default Runner")
        self.label_runner.set_halign(Gtk.Align.START)
        self.combo_box_runner = Gtk.ComboBoxText()

        self.button_proton_manager = Gtk.Button(label="GE-Proton Manager")
        self.button_proton_manager.connect("clicked", self.on_button_proton_manager_clicked)

        # Create checkbox for 'Use discrete GPU' option
        self.checkbox_discrete_gpu = Gtk.CheckButton(label="Use discrete GPU")
        self.checkbox_discrete_gpu.set_active(False)

        # Create checkbox for 'Close after launch' option
        self.checkbox_close_after_launch = Gtk.CheckButton(label="Close when running a game")
        self.checkbox_close_after_launch.set_active(False)

        # Create checkbox for 'System tray' option
        self.checkbox_system_tray = Gtk.CheckButton(label="System tray icon")
        self.checkbox_system_tray.set_active(False)
        self.checkbox_system_tray.connect("toggled", self.on_checkbox_system_tray_toggled)

        # Create checkbox for 'Start on boot' option
        self.checkbox_start_boot = Gtk.CheckButton(label="Start on boot")
        self.checkbox_start_boot.set_active(False)
        self.checkbox_start_boot.set_sensitive(False)

        # Create checkbox for 'Splash screen' option
        self.checkbox_splash_disable = Gtk.CheckButton(label="Disable splash window")
        self.checkbox_splash_disable.set_active(False)

        # Button Winetricks
        self.button_winetricks_default = Gtk.Button(label="Winetricks")
        self.button_winetricks_default.connect("clicked", self.on_button_winetricks_default_clicked)
        self.button_winetricks_default.set_size_request(120, -1)

        # Button Winecfg
        self.button_winecfg_default = Gtk.Button(label="Winecfg")
        self.button_winecfg_default.connect("clicked", self.on_button_winecfg_default_clicked)
        self.button_winecfg_default.set_size_request(120, -1)

        # Button for Run
        self.button_run_default = Gtk.Button(label="Run")
        self.button_run_default.set_size_request(120, -1)
        self.button_run_default.connect("clicked", self.on_button_run_default_clicked)
        self.button_run_default.set_tooltip_text("Run a file inside the prefix")

        # Checkboxes for optional features
        self.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
        self.checkbox_mangohud.set_tooltip_text(
            "Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more.")
        self.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
        self.checkbox_gamemode.set_tooltip_text("Tweaks your system to improve performance.")
        self.checkbox_sc_controller = Gtk.CheckButton(label="SC Controller")
        self.checkbox_sc_controller.set_tooltip_text(
            "Emulates a Xbox controller if the game doesn't support yours. Put the profile at ~/.config/faugus-launcher/controller.sccprofile.")

        self.label_support = Gtk.Label(label="Support the project")
        self.label_support.set_halign(Gtk.Align.START)

        button_kofi = Gtk.Button(label="Buy me a Coffee")
        button_kofi.set_size_request(150, -1)
        button_kofi.connect("clicked", self.on_button_kofi_clicked)
        button_kofi.get_style_context().add_class("kofi")
        button_kofi.set_halign(Gtk.Align.CENTER)

        button_paypal = Gtk.Button(label="PayPal Donation")
        button_paypal.set_size_request(150, -1)
        button_paypal.connect("clicked", self.on_button_paypal_clicked)
        button_paypal.get_style_context().add_class("paypal")
        button_paypal.set_halign(Gtk.Align.CENTER)

        # Button Cancel
        self.button_cancel = Gtk.Button(label="Cancel")
        self.button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        self.button_cancel.set_size_request(150, -1)
        self.button_cancel.set_halign(Gtk.Align.CENTER)

        # Button Ok
        self.button_ok = Gtk.Button(label="Ok")
        self.button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        self.button_ok.set_size_request(150, -1)
        self.button_ok.set_halign(Gtk.Align.CENTER)

        self.box = self.get_content_area()

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)

        grid2 = Gtk.Grid()
        grid2.set_row_spacing(10)
        grid2.set_column_spacing(10)
        grid2.set_margin_start(10)
        grid2.set_margin_end(10)
        grid2.set_margin_top(10)

        grid3 = Gtk.Grid()
        grid3.set_row_spacing(10)
        grid3.set_column_spacing(10)
        grid3.set_margin_start(10)
        grid3.set_margin_end(10)
        grid3.set_margin_top(10)
        grid3.set_margin_bottom(10)

        grid4 = Gtk.Grid()
        grid4.set_row_spacing(10)
        grid4.set_column_spacing(10)
        grid4.set_margin_start(10)
        grid4.set_margin_end(10)
        grid4.set_margin_top(10)
        grid4.set_margin_bottom(10)

        grid5 = Gtk.Grid()
        grid5.set_row_spacing(10)
        grid5.set_column_spacing(10)
        grid5.set_margin_start(10)
        grid5.set_margin_end(10)
        grid5.set_margin_top(10)
        grid5.set_margin_bottom(10)

        grid6 = Gtk.Grid()
        grid6.set_row_spacing(10)
        grid6.set_column_spacing(10)
        grid6.set_margin_start(10)
        grid6.set_margin_end(10)
        grid6.set_margin_top(10)
        grid6.set_margin_bottom(10)

        grid7 = Gtk.Grid()
        grid7.set_row_spacing(10)
        grid7.set_column_spacing(10)
        grid7.set_margin_start(10)
        grid7.set_margin_end(10)
        grid7.set_margin_top(10)
        grid7.set_margin_bottom(10)


        # Create a frame
        frame = Gtk.Frame()
        frame.set_label_align(0.5, 0.5)
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        # Add grid to frame
        frame.add(grid3)

        # Attach widgets to the grid layout
        grid.attach(self.label_default_prefix, 0, 0, 1, 1)
        grid.attach(self.entry_default_prefix, 0, 1, 3, 1)
        self.entry_default_prefix.set_hexpand(True)
        grid.attach(self.button_search_prefix, 3, 1, 1, 1)

        grid6.attach(self.label_runner, 0, 6, 1, 1)
        grid6.attach(self.combo_box_runner, 0, 7, 1, 1)
        grid6.attach(self.button_proton_manager, 0, 8, 1, 1)
        self.combo_box_runner.set_hexpand(True)
        self.button_proton_manager.set_hexpand(True)

        grid7.attach(self.checkbox_discrete_gpu, 0, 2, 4, 1)
        grid7.attach(self.checkbox_splash_disable, 0, 3, 4, 1)
        grid7.attach(self.checkbox_system_tray, 0, 4, 4, 1)
        grid7.attach(self.checkbox_start_boot, 0, 5, 4, 1)
        grid7.attach(self.checkbox_close_after_launch, 0, 6, 4, 1)

        grid2.attach(self.label_default_prefix_tools, 0, 0, 1, 1)

        grid3.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        grid3.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        grid3.attach(self.checkbox_sc_controller, 0, 2, 1, 1)
        grid3.attach(self.button_winetricks_default, 1, 0, 1, 1)
        grid3.attach(self.button_winecfg_default, 1, 1, 1, 1)
        grid3.attach(self.button_run_default, 1, 2, 1, 1)

        grid4.attach(self.label_support, 0, 0, 1, 1)
        grid4.attach(button_kofi, 0, 1, 1, 1)
        grid4.attach(button_paypal, 1, 1, 1, 1)
        grid4.set_halign(Gtk.Align.CENTER)

        grid5.attach(self.button_cancel, 0, 0, 1, 1)
        grid5.attach(self.button_ok, 1, 0, 1, 1)
        grid5.set_halign(Gtk.Align.CENTER)

        self.populate_combobox_with_runners()
        self.load_config()

        # Check if optional features are available and enable/disable accordingly
        self.mangohud_enabled = os.path.exists(mangohud_dir)
        if not self.mangohud_enabled:
            self.checkbox_mangohud.set_sensitive(False)
            self.checkbox_mangohud.set_active(False)
            self.checkbox_mangohud.set_tooltip_text(
                "Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more. NOT INSTALLED.")

        self.gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
        if not self.gamemode_enabled:
            self.checkbox_gamemode.set_sensitive(False)
            self.checkbox_gamemode.set_active(False)
            self.checkbox_gamemode.set_tooltip_text("Tweaks your system to improve performance. NOT INSTALLED.")

        self.sc_controller_enabled = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
            "/usr/local/bin/sc-controller")
        if not self.sc_controller_enabled:
            self.checkbox_sc_controller.set_sensitive(False)
            self.checkbox_sc_controller.set_active(False)
            self.checkbox_sc_controller.set_tooltip_text(
                "Emulates a Xbox controller if the game doesn't support yours. Put the profile at ~/.config/faugus-launcher/controller.sccprofile. NOT INSTALLED.")

        self.box.add(grid)
        self.box.add(grid6)
        self.box.add(grid2)
        self.box.add(frame)
        self.box.add(grid7)
        self.box.add(grid4)
        self.box.add(grid5)

        self.show_all()

    def on_checkbox_system_tray_toggled(self, widget):
        if not widget.get_active():
            self.checkbox_start_boot.set_active(False)
            self.checkbox_start_boot.set_sensitive(False)
        else:
            self.checkbox_start_boot.set_sensitive(True)

    def on_button_proton_manager_clicked(self, widget):
        self.set_sensitive(False)

        proton_manager = faugus_proton_manager
        def run_command():
            process = subprocess.Popen([sys.executable, proton_manager])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent.set_sensitive, True)
            GLib.idle_add(self.blocking_window.destroy)

            GLib.idle_add(lambda: self.combo_box_runner.remove_all())
            GLib.idle_add(self.populate_combobox_with_runners)

        self.blocking_window = Gtk.Window()
        self.blocking_window.set_transient_for(self.parent)
        self.blocking_window.set_decorated(False)
        self.blocking_window.set_modal(True)

        command_thread = threading.Thread(target=run_command)
        command_thread.start()

    def populate_combobox_with_runners(self):
        # List of default entries
        self.combo_box_runner.append_text("GE-Proton Latest (default)")
        self.combo_box_runner.append_text("UMU-Proton Latest")

        # Path to the directory containing the folders
        runner_path = f'{share_dir}/Steam/compatibilitytools.d/'

        try:
            # Check if the directory exists
            if os.path.exists(runner_path):
                # List to hold version directories
                versions = []
                # Iterate over the folders in the directory
                for entry in os.listdir(runner_path):
                    entry_path = os.path.join(runner_path, entry)
                    # Add to list only if it's a directory and not "UMU-Latest"
                    if os.path.isdir(entry_path) and entry != "UMU-Latest":
                        versions.append(entry)

                # Sort versions in descending order
                def version_key(v):
                    # Remove 'GE-Proton' and split the remaining part into segments of digits and non-digits
                    v_parts = re.split(r'(\d+)', v.replace('GE-Proton', ''))
                    # Convert numeric parts to integers for proper sorting
                    return [int(part) if part.isdigit() else part for part in v_parts]

                versions.sort(key=version_key, reverse=True)

                # Add sorted versions to ComboBox
                for version in versions:
                    self.combo_box_runner.append_text(version)

        except Exception as e:
            print(f"Error accessing the directory: {e}")

        # Set the active item, if desired
        self.combo_box_runner.set_active(0)

    def on_entry_changed(self, widget, entry):
        if entry.get_text():
            entry.get_style_context().remove_class("entry")

    def on_button_run_default_clicked(self, widget):
        if self.entry_default_prefix.get_text() == "":
            self.entry_default_prefix.get_style_context().add_class("entry")
        else:
            checkbox_state = self.checkbox_close_after_launch.get_active()
            default_prefix = self.entry_default_prefix.get_text()
            checkbox_discrete_gpu_state = self.checkbox_discrete_gpu.get_active()
            checkbox_splash_disable = self.checkbox_splash_disable.get_active()
            checkbox_start_boot = self.checkbox_start_boot.get_active()
            checkbox_system_tray = self.checkbox_system_tray.get_active()

            mangohud_state = self.checkbox_mangohud.get_active()
            gamemode_state = self.checkbox_gamemode.get_active()
            sc_controller_state = self.checkbox_sc_controller.get_active()
            default_runner = self.combo_box_runner.get_active_text()

            if default_runner == "UMU-Proton Latest":
                default_runner = ""
            if default_runner == "GE-Proton Latest (default)":
                default_runner = "GE-Proton"

            self.parent.save_config(checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot)
            self.set_sensitive(False)

            self.parent.manage_autostart_file(checkbox_start_boot)
            if checkbox_system_tray:
                self.parent.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                if not hasattr(self, "window_delete_event_connected") or not self.window_delete_event_connected:
                    self.connect("delete-event", self.parent.on_window_delete_event)
                    self.parent.window_delete_event_connected = True
                self.parent.indicator.set_menu(self.parent.create_tray_menu())
            else:
                self.parent.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
                if hasattr(self, "window_delete_event_connected") and self.window_delete_event_connected:
                    self.disconnect_by_func(self.parent.on_window_delete_event)
                    self.parent.window_delete_event_connected = False

            dialog = Gtk.FileChooserDialog(title="Select a file to run inside the prefix",
                                        action=Gtk.FileChooserAction.OPEN)
            dialog.set_current_folder(os.path.expanduser("~/"))
            dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

            # Windows files filter
            windows_filter = Gtk.FileFilter()
            windows_filter.set_name("Windows files")
            windows_filter.add_pattern("*.exe")
            windows_filter.add_pattern("*.msi")
            windows_filter.add_pattern("*.bat")
            windows_filter.add_pattern("*.lnk")
            windows_filter.add_pattern("*.reg")
            dialog.add_filter(windows_filter)

            # All files filter
            all_files_filter = Gtk.FileFilter()
            all_files_filter.set_name("All files")
            all_files_filter.add_pattern("*")
            dialog.add_filter(all_files_filter)

            response = dialog.run()
            if response == Gtk.ResponseType.OK:

                command_parts = []
                file_run = dialog.get_filename()
                if not file_run.endswith(".reg"):
                    if file_run:
                        command_parts.append(f'GAMEID=default')
                    if default_runner:
                        command_parts.append(f'PROTONPATH={default_runner}')
                    command_parts.append(f'"{umu_run}" "{file_run}"')
                else:
                    if file_run:
                        command_parts.append(f'GAMEID=default')
                    if default_runner:
                        command_parts.append(f'PROTONPATH={default_runner}')
                    command_parts.append(f'"{umu_run}" regedit "{file_run}"')

                # Join all parts into a single command
                command = ' '.join(command_parts)

                print(command)

                # faugus-run path
                faugus_run_path = faugus_run

                def run_command():
                    process = subprocess.Popen([sys.executable, faugus_run_path, command])
                    process.wait()
                    GLib.idle_add(self.set_sensitive, True)
                    GLib.idle_add(self.parent.set_sensitive, True)
                    GLib.idle_add(self.blocking_window.destroy)

                self.blocking_window = Gtk.Window()
                self.blocking_window.set_transient_for(self.parent)
                self.blocking_window.set_decorated(False)
                self.blocking_window.set_modal(True)

                command_thread = threading.Thread(target=run_command)
                command_thread.start()

            else:
                self.set_sensitive(True)
            dialog.destroy()

    def on_button_winecfg_default_clicked(self, widget):

        if self.entry_default_prefix.get_text() == "":
            self.entry_default_prefix.get_style_context().add_class("entry")
        else:
            checkbox_state = self.checkbox_close_after_launch.get_active()
            default_prefix = self.entry_default_prefix.get_text()
            checkbox_discrete_gpu_state = self.checkbox_discrete_gpu.get_active()
            checkbox_splash_disable = self.checkbox_splash_disable.get_active()
            checkbox_start_boot = self.checkbox_start_boot.get_active()
            checkbox_system_tray = self.checkbox_system_tray.get_active()

            mangohud_state = self.checkbox_mangohud.get_active()
            gamemode_state = self.checkbox_gamemode.get_active()
            sc_controller_state = self.checkbox_sc_controller.get_active()
            default_runner = self.combo_box_runner.get_active_text()

            if default_runner == "UMU-Proton Latest":
                default_runner = ""
            if default_runner == "GE-Proton Latest (default)":
                default_runner = "GE-Proton"

            self.parent.save_config(checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot)
            self.set_sensitive(False)

            self.parent.manage_autostart_file(checkbox_start_boot)
            if checkbox_system_tray:
                self.parent.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                if not hasattr(self, "window_delete_event_connected") or not self.window_delete_event_connected:
                    self.connect("delete-event", self.parent.on_window_delete_event)
                    self.parent.window_delete_event_connected = True
                self.parent.indicator.set_menu(self.parent.create_tray_menu())
            else:
                self.parent.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
                if hasattr(self, "window_delete_event_connected") and self.window_delete_event_connected:
                    self.disconnect_by_func(self.parent.on_window_delete_event)
                    self.parent.window_delete_event_connected = False

            command_parts = []

            # Add command parts if they are not empty

            command_parts.append(f'GAMEID=default')
            if default_runner:
                command_parts.append(f'PROTONPATH={default_runner}')

            # Add the fixed command and remaining arguments
            command_parts.append(f'"{umu_run}"')
            command_parts.append('"winecfg"')

            # Join all parts into a single command
            command = ' '.join(command_parts)

            print(command)

            # faugus-run path
            faugus_run_path = faugus_run

            def run_command():
                process = subprocess.Popen([sys.executable, faugus_run_path, command])
                process.wait()
                GLib.idle_add(self.set_sensitive, True)
                GLib.idle_add(self.parent.set_sensitive, True)
                GLib.idle_add(self.blocking_window.destroy)

            self.blocking_window = Gtk.Window()
            self.blocking_window.set_transient_for(self.parent)
            self.blocking_window.set_decorated(False)
            self.blocking_window.set_modal(True)

            command_thread = threading.Thread(target=run_command)
            command_thread.start()

    def on_button_winetricks_default_clicked(self, widget):
        if self.entry_default_prefix.get_text() == "":
            self.entry_default_prefix.get_style_context().add_class("entry")
        else:
            checkbox_state = self.checkbox_close_after_launch.get_active()
            default_prefix = self.entry_default_prefix.get_text()
            checkbox_discrete_gpu_state = self.checkbox_discrete_gpu.get_active()
            checkbox_splash_disable = self.checkbox_splash_disable.get_active()
            checkbox_start_boot = self.checkbox_start_boot.get_active()
            checkbox_system_tray = self.checkbox_system_tray.get_active()

            mangohud_state = self.checkbox_mangohud.get_active()
            gamemode_state = self.checkbox_gamemode.get_active()
            sc_controller_state = self.checkbox_sc_controller.get_active()
            default_runner = self.combo_box_runner.get_active_text()

            if default_runner == "UMU-Proton Latest":
                default_runner = ""
            if default_runner == "GE-Proton Latest (default)":
                default_runner = "GE-Proton"

            self.parent.save_config(checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot)
            self.set_sensitive(False)

            self.parent.manage_autostart_file(checkbox_start_boot)
            if checkbox_system_tray:
                self.parent.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
                if not hasattr(self, "window_delete_event_connected") or not self.window_delete_event_connected:
                    self.connect("delete-event", self.parent.on_window_delete_event)
                    self.parent.window_delete_event_connected = True
                self.parent.indicator.set_menu(self.parent.create_tray_menu())
            else:
                self.parent.indicator.set_status(AppIndicator3.IndicatorStatus.PASSIVE)
                if hasattr(self, "window_delete_event_connected") and self.window_delete_event_connected:
                    self.disconnect_by_func(self.parent.on_window_delete_event)
                    self.parent.window_delete_event_connected = False

            command_parts = []

            # Add command parts if they are not empty

            command_parts.append(f'GAMEID=winetricks-gui')
            command_parts.append(f'STORE=none')
            if default_runner:
                command_parts.append(f'PROTONPATH={default_runner}')

            # Add the fixed command and remaining arguments
            command_parts.append(f'"{umu_run}"')
            command_parts.append('""')

            # Join all parts into a single command
            command = ' '.join(command_parts)

            print(command)

            # faugus-run path
            faugus_run_path = faugus_run

            def run_command():
                process = subprocess.Popen([sys.executable, faugus_run_path, command, "winetricks"])
                process.wait()
                GLib.idle_add(self.set_sensitive, True)
                GLib.idle_add(self.parent.set_sensitive, True)
                GLib.idle_add(self.blocking_window.destroy)

            self.blocking_window = Gtk.Window()
            self.blocking_window.set_transient_for(self.parent)
            self.blocking_window.set_decorated(False)
            self.blocking_window.set_modal(True)

            command_thread = threading.Thread(target=run_command)
            command_thread.start()

    def on_button_kofi_clicked(self, widget):
        webbrowser.open("https://ko-fi.com/K3K210EMDU")

    def on_button_paypal_clicked(self, widget):
        webbrowser.open("https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD")

    def on_button_search_prefix_clicked(self, widget):
        # Handle the click event of the search button to select the game's .exe
        dialog = Gtk.FileChooserDialog(title="Select a prefix location", parent=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.set_current_folder(os.path.expanduser(self.default_prefix))
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.entry_default_prefix.set_text(dialog.get_filename())

        dialog.destroy()

    def load_config(self):
        # Load configuration from file
        config_file = os.path.join(self.parent.working_directory, 'config.ini')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_data = f.read().splitlines()
            config_dict = dict(line.split('=') for line in config_data)
            close_on_launch = config_dict.get('close-onlaunch', 'False') == 'True'
            discrete_gpu = config_dict.get('discrete-gpu', 'False') == 'True'
            splash_disable = config_dict.get('splash-disable', 'False') == 'True'
            system_tray = config_dict.get('system-tray', 'False') == 'True'
            start_boot = config_dict.get('start-boot', 'False') == 'True'
            self.default_prefix = config_dict.get('default-prefix', '').strip('"')

            mangohud = config_dict.get('mangohud', 'False') == 'True'
            gamemode = config_dict.get('gamemode', 'False') == 'True'
            sc_controller = config_dict.get('sc-controller', 'False') == 'True'
            self.default_runner = config_dict.get('default-runner', '').strip('"')

            self.checkbox_discrete_gpu.set_active(discrete_gpu)
            self.checkbox_close_after_launch.set_active(close_on_launch)
            self.checkbox_splash_disable.set_active(splash_disable)
            self.checkbox_start_boot.set_active(start_boot)
            self.checkbox_system_tray.set_active(system_tray)

            self.entry_default_prefix.set_text(self.default_prefix)
            self.checkbox_mangohud.set_active(mangohud)
            self.checkbox_gamemode.set_active(gamemode)
            self.checkbox_sc_controller.set_active(sc_controller)

            if self.default_runner == "":
                self.default_runner = "UMU-Proton Latest"

            model = self.combo_box_runner.get_model()
            index_to_activate = 0
            for i, row in enumerate(model):
                if row[0] == self.default_runner:
                    index_to_activate = i
                    break
            self.combo_box_runner.set_active(index_to_activate)

        else:
            # Save default configuration if file does not exist
            print("else")
            self.parent.save_config(False, '', "False", "False", "False", "GE-Proton", "True", "False", "False", "False")


class Game:
    def __init__(self, title, path, prefix, launch_arguments, game_arguments, mangohud, gamemode, sc_controller, protonfix, runner):
        # Initialize a Game object with various attributes
        self.title = title  # Title of the game
        self.path = path  # Path to the game executable
        self.launch_arguments = launch_arguments  # Arguments to launch the game
        self.game_arguments = game_arguments  # Arguments specific to the game
        self.mangohud = mangohud  # Boolean indicating whether Mangohud is enabled
        self.gamemode = gamemode  # Boolean indicating whether Gamemode is enabled
        self.prefix = prefix  # Prefix for Wine games
        self.sc_controller = sc_controller  # Boolean indicating whether SC Controller is enabled
        self.protonfix = protonfix
        self.runner = runner


class ConfirmationDialog(Gtk.Dialog):
    def __init__(self, parent, title):
        # Initialize the ConfirmationDialog
        Gtk.Dialog.__init__(self, title=f"Delete {title}", parent=parent, modal=True)
        self.set_icon_from_file(faugus_png)

        # Configure dialog properties
        self.set_resizable(False)

        # Create a grid layout for the dialog content area
        grid = Gtk.Grid()
        grid.set_row_spacing(20)
        grid.set_column_spacing(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)

        # Add grid to dialog's content area
        content_area = self.get_content_area()
        content_area.set_border_width(0)
        content_area.add(grid)

        # Create a label
        label = Gtk.Label()
        label.set_label(f"Are you sure you want to delete {title}?")
        label.set_halign(Gtk.Align.CENTER)
        grid.attach(label, 0, 0, 2, 1)

        # Create "No" button
        button_no = Gtk.Button(label="Cancel")
        button_no.set_size_request(150, -1)
        button_no.connect("clicked", lambda x: self.response(Gtk.ResponseType.NO))
        grid.attach(button_no, 0, 2, 1, 1)

        # Create "Yes" button
        button_yes = Gtk.Button(label="Confirm")
        button_yes.set_size_request(150, -1)
        button_yes.connect("clicked", lambda x: self.response(Gtk.ResponseType.YES))
        grid.attach(button_yes, 1, 2, 1, 1)

        # Create a checkbox to optionally remove the prefix
        self.checkbox = Gtk.CheckButton(label="Also remove the prefix")
        self.checkbox.set_halign(Gtk.Align.CENTER)
        grid.attach(self.checkbox, 0, 1, 2, 1)

        # Display all widgets
        self.show_all()

    def get_remove_prefix_state(self):
        # Get the state of the checkbox
        return self.checkbox.get_active()


class AddGame(Gtk.Dialog):
    def __init__(self, parent, game_running2, file_path):
        # Initialize the AddGame dialog
        super().__init__(title="New Game", parent=parent)
        self.set_resizable(False)
        self.set_modal(True)
        self.parent_window = parent
        self.set_icon_from_file(faugus_png)

        self.icon_directory = f"{icons_dir}/icon_temp/"

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        self.icons_path = icons_dir
        self.icon_extracted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.ico')
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.ico'

        self.box = self.get_content_area()
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)

        grid2 = Gtk.Grid()

        grid2.set_row_spacing(10)
        grid2.set_column_spacing(10)
        grid2.set_margin_start(10)
        grid2.set_margin_end(10)
        grid2.set_margin_top(10)
        grid2.set_margin_bottom(10)

        grid3 = Gtk.Grid()
        grid3.set_row_spacing(10)
        grid3.set_column_spacing(10)
        grid3.set_margin_start(10)
        grid3.set_margin_end(10)
        grid3.set_margin_top(10)
        grid3.set_margin_bottom(10)

        grid4 = Gtk.Grid()
        grid4.set_row_spacing(10)
        grid4.set_column_spacing(10)
        grid4.set_margin_start(10)
        grid4.set_margin_end(10)

        grid5 = Gtk.Grid()
        grid5.set_row_spacing(10)
        grid5.set_column_spacing(10)
        grid5.set_margin_start(10)
        grid5.set_margin_end(10)


        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        # Widgets for title
        self.label_title = Gtk.Label(label="Title")
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", self.on_entry_changed, self.entry_title)
        self.entry_title.set_tooltip_text("Game Title")

        # Widgets for path
        self.label_path = Gtk.Label(label="Path")
        self.label_path.set_halign(Gtk.Align.START)
        self.entry_path = Gtk.Entry()
        self.entry_path.connect("changed", self.on_entry_changed, self.entry_path)
        if file_path:
            self.entry_path.set_text(file_path)
        self.entry_path.set_tooltip_text("/path/to/the/exe")
        self.button_search = Gtk.Button()
        self.button_search.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search.connect("clicked", self.on_button_search_clicked)
        self.button_search.set_size_request(50, -1)

        # Widgets for prefix
        self.label_prefix = Gtk.Label(label="Prefix")
        self.label_prefix.set_halign(Gtk.Align.START)
        self.entry_prefix = Gtk.Entry()
        self.entry_prefix.connect("changed", self.on_entry_changed, self.entry_prefix)
        self.entry_prefix.set_tooltip_text("/path/to/the/prefix")
        self.button_search_prefix = Gtk.Button()
        self.button_search_prefix.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_prefix.connect("clicked", self.on_button_search_prefix_clicked)
        self.button_search_prefix.set_size_request(50, -1)

        # Widgets for runner
        self.label_runner = Gtk.Label(label="Runner")
        self.label_runner.set_halign(Gtk.Align.START)
        self.combo_box_runner = Gtk.ComboBoxText()

        # Widgets for protonfix
        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_protonfix.connect("clicked", self.on_button_search_protonfix_clicked)
        self.button_search_protonfix.set_size_request(50, -1)

        # Widgets for launch arguments
        self.label_launch_arguments = Gtk.Label(label="Launch Arguments")
        self.label_launch_arguments.set_halign(Gtk.Align.START)
        self.entry_launch_arguments = Gtk.Entry()
        self.entry_launch_arguments.set_tooltip_text("e.g.: PROTON_USE_WINED3D=1 gamescope -W 2560 -H 1440")

        # Widgets for game arguments
        self.label_game_arguments = Gtk.Label(label="Game Arguments")
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text("e.g.: -d3d11 -fullscreen")

        # Checkboxes for optional features
        self.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
        self.checkbox_mangohud.set_tooltip_text(
            "Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more.")
        self.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
        self.checkbox_gamemode.set_tooltip_text("Tweaks your system to improve performance.")
        self.checkbox_sc_controller = Gtk.CheckButton(label="SC Controller")
        self.checkbox_sc_controller.set_tooltip_text(
            "Emulates a Xbox controller if the game doesn't support yours. Put the profile at ~/.config/faugus-launcher/controller.sccprofile.")

        # Button for Winecfg
        self.button_winecfg = Gtk.Button(label="Winecfg")
        self.button_winecfg.set_size_request(120, -1)
        self.button_winecfg.connect("clicked", self.on_button_winecfg_clicked)

        # Button for Winetricks
        self.button_winetricks = Gtk.Button(label="Winetricks")
        self.button_winetricks.set_size_request(120, -1)
        self.button_winetricks.connect("clicked", self.on_button_winetricks_clicked)

        # Button for Run
        self.button_run = Gtk.Button(label="Run")
        self.button_run.set_size_request(120, -1)
        self.button_run.connect("clicked", self.on_button_run_clicked)
        self.button_run.set_tooltip_text("Run a file inside the prefix")

        # Button for creating shortcut
        self.checkbox_shortcut = Gtk.CheckButton(label="Create Shortcut")

        # Button for selection shortcut icon
        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_size_request(120, -1)
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)
        self.button_shortcut_icon.set_tooltip_text("Select an icon for the shortcut")

        # Button Cancel
        self.button_cancel = Gtk.Button(label="Cancel")
        self.button_cancel.connect("clicked", lambda widget: self.response(Gtk.ResponseType.CANCEL))
        self.button_cancel.set_size_request(150, -1)

        # Button Ok
        self.button_ok = Gtk.Button(label="Ok")
        self.button_ok.connect("clicked", lambda widget: self.response(Gtk.ResponseType.OK))
        self.button_ok.set_size_request(150, -1)

        # Event handlers
        self.default_prefix = self.load_default_prefix()
        self.entry_title.connect("changed", self.update_prefix_entry)

        self.default_runner = self.load_default_runner()

        self.notebook = Gtk.Notebook()
        self.box.add(self.notebook)
        self.notebook.set_margin_start(10)
        self.notebook.set_margin_end(10)
        self.notebook.set_margin_top(10)
        self.notebook.set_margin_bottom(10)
        #notebook.set_show_border(False)

        page1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        tab_box1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label1 = Gtk.Label(label="Game")
        tab_box1.pack_start(tab_label1, True, True, 0)
        tab_box1.set_hexpand(True)
        self.notebook.append_page(page1, tab_box1)

        page2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        tab_box2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tab_label2 = Gtk.Label(label="Tools")
        tab_box2.pack_start(tab_label2, True, True, 0)
        tab_box2.set_hexpand(True)
        self.notebook.append_page(page2, tab_box2)

        # Attach widgets to the grid layout
        grid.attach(self.label_title, 0, 0, 4, 1)
        grid.attach(self.entry_title, 0, 1, 4, 1)

        grid.attach(self.label_path, 0, 2, 1, 1)
        grid.attach(self.entry_path, 0, 3, 3, 1)
        self.entry_path.set_hexpand(True)
        grid.attach(self.button_search, 3, 3, 1, 1)

        grid.attach(self.label_prefix, 0, 4, 1, 1)
        grid.attach(self.entry_prefix, 0, 5, 3, 1)
        self.entry_prefix.set_hexpand(True)
        grid.attach(self.button_search_prefix, 3, 5, 1, 1)

        grid5.attach(self.label_runner, 0, 6, 1, 1)
        grid5.attach(self.combo_box_runner, 0, 7, 1, 1)
        self.combo_box_runner.set_hexpand(True)

        page1.add(grid)
        page1.add(grid5)

        grid2.attach(self.button_shortcut_icon, 2, 6, 1, 1)
        grid2.attach(self.checkbox_shortcut, 0, 6, 1, 1)
        self.checkbox_shortcut.set_hexpand(True)

        page1.add(grid2)

        grid3.attach(self.label_protonfix, 0, 0, 1, 1)
        grid3.attach(self.entry_protonfix, 0, 1, 3, 1)
        self.entry_protonfix.set_hexpand(True)
        grid3.attach(self.button_search_protonfix, 3, 1, 1, 1)

        grid3.attach(self.label_launch_arguments, 0, 2, 1, 1)
        grid3.attach(self.entry_launch_arguments, 0, 3, 4, 1)

        grid3.attach(self.label_game_arguments, 0, 4, 1, 1)
        grid3.attach(self.entry_game_arguments, 0, 5, 4, 1)

        page2.add(grid3)

        grid4.attach(self.checkbox_mangohud, 0, 6, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        grid4.attach(self.checkbox_gamemode, 0, 7, 1, 1)
        self.checkbox_gamemode.set_hexpand(True)
        grid4.attach(self.checkbox_sc_controller, 0, 8, 1, 1)
        self.checkbox_sc_controller.set_hexpand(True)

        grid4.attach(self.button_winetricks, 2, 6, 1, 1)
        grid4.attach(self.button_winecfg, 2, 7, 1, 1)
        grid4.attach(self.button_run, 2, 8, 1, 1)

        page2.add(grid4)

        botton_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        botton_box.set_margin_start(10)
        botton_box.set_margin_end(10)
        #botton_box.set_margin_top(10)
        botton_box.set_margin_bottom(10)
        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        botton_box.pack_start(self.button_cancel, True, True, 0)
        botton_box.pack_start(self.button_ok, True, True, 0)

        self.box.add(botton_box)

        self.populate_combobox_with_runners()

        model = self.combo_box_runner.get_model()
        index_to_activate = 0

        if self.default_runner == "":
            self.default_runner = "UMU-Proton Latest"
        if self.default_runner == "GE-Proton":
            self.default_runner = "GE-Proton Latest (default)"

        for i, row in enumerate(model):
            if row[0] == self.default_runner:
                index_to_activate = i
                break
        self.combo_box_runner.set_active(index_to_activate)

        # Check if optional features are available and enable/disable accordingly
        self.mangohud_enabled = os.path.exists(mangohud_dir)
        if not self.mangohud_enabled:
            self.checkbox_mangohud.set_sensitive(False)
            self.checkbox_mangohud.set_active(False)
            self.checkbox_mangohud.set_tooltip_text(
                "Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more. NOT INSTALLED.")

        self.gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
        if not self.gamemode_enabled:
            self.checkbox_gamemode.set_sensitive(False)
            self.checkbox_gamemode.set_active(False)
            self.checkbox_gamemode.set_tooltip_text("Tweaks your system to improve performance. NOT INSTALLED.")

        self.sc_controller_enabled = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
            "/usr/local/bin/sc-controller")
        if not self.sc_controller_enabled:
            self.checkbox_sc_controller.set_sensitive(False)
            self.checkbox_sc_controller.set_active(False)
            self.checkbox_sc_controller.set_tooltip_text(
                "Emulates a Xbox controller if the game doesn't support yours. Put the profile at ~/.config/faugus-launcher/controller.sccprofile. NOT INSTALLED.")

        # self.create_remove_shortcut(self)
        self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())

        self.entry_title.connect("key-press-event", self.on_key_press)
        self.entry_path.connect("key-press-event", self.on_key_press)
        self.entry_prefix.connect("key-press-event", self.on_key_press)
        self.entry_protonfix.connect("key-press-event", self.on_key_press)
        self.entry_launch_arguments.connect("key-press-event", self.on_key_press)
        self.entry_game_arguments.connect("key-press-event", self.on_key_press)

        tab_box1.show_all()
        tab_box2.show_all()
        self.show_all()

    def on_key_press(self, widget, event):
        if event.string in [';']:
            return True
        return False

    def populate_combobox_with_runners(self):
        # List of default entries
        self.combo_box_runner.append_text("GE-Proton Latest (default)")
        self.combo_box_runner.append_text("UMU-Proton Latest")

        # Path to the directory containing the folders
        runner_path = f'{share_dir}/Steam/compatibilitytools.d/'

        try:
            # Check if the directory exists
            if os.path.exists(runner_path):
                # List to hold version directories
                versions = []
                # Iterate over the folders in the directory
                for entry in os.listdir(runner_path):
                    entry_path = os.path.join(runner_path, entry)
                    # Add to list only if it's a directory and not "UMU-Latest"
                    if os.path.isdir(entry_path) and entry != "UMU-Latest":
                        versions.append(entry)

                # Sort versions in descending order
                def version_key(v):
                    # Remove 'GE-Proton' and split the remaining part into segments of digits and non-digits
                    v_parts = re.split(r'(\d+)', v.replace('GE-Proton', ''))
                    # Convert numeric parts to integers for proper sorting
                    return [int(part) if part.isdigit() else part for part in v_parts]

                versions.sort(key=version_key, reverse=True)

                # Add sorted versions to ComboBox
                for version in versions:
                    self.combo_box_runner.append_text(version)

        except Exception as e:
            print(f"Error accessing the directory: {e}")

        # Set the active item, if desired
        self.combo_box_runner.set_active(0)

    def on_entry_changed(self, widget, entry):
        if entry.get_text():
            entry.get_style_context().remove_class("entry")

    def load_default_prefix(self):
        config_file = config_file_dir
        default_prefix = ""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_data = f.read().splitlines()
            config_dict = dict(line.split('=') for line in config_data)
            default_prefix = config_dict.get('default-prefix', '').strip('"')
        return default_prefix

    def load_default_runner(self):
        config_file = config_file_dir
        default_runner = ""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_data = f.read().splitlines()
            config_dict = dict(line.split('=') for line in config_data)
            default_runner = config_dict.get('default-runner', '').strip('"')
        return default_runner

    def on_button_run_clicked(self, widget):
        self.set_sensitive(False)
        # Handle the click event of the Run button
        validation_result = self.validate_fields(entry="prefix")
        if not validation_result:
            self.set_sensitive(True)
            return

        dialog = Gtk.FileChooserDialog(title="Select a file to run inside the prefix",
                                       action=Gtk.FileChooserAction.OPEN)
        dialog.set_current_folder(os.path.expanduser("~/"))
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        # Windows files filter
        windows_filter = Gtk.FileFilter()
        windows_filter.set_name("Windows files")
        windows_filter.add_pattern("*.exe")
        windows_filter.add_pattern("*.msi")
        windows_filter.add_pattern("*.bat")
        windows_filter.add_pattern("*.lnk")
        windows_filter.add_pattern("*.reg")
        dialog.add_filter(windows_filter)

        # All files filter
        all_files_filter = Gtk.FileFilter()
        all_files_filter.set_name("All files")
        all_files_filter.add_pattern("*")
        dialog.add_filter(all_files_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            title = self.entry_title.get_text()
            prefix = self.entry_prefix.get_text()

            title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
            title_formatted = title_formatted.replace(' ', '-')
            title_formatted = '-'.join(title_formatted.lower().split())

            runner = self.combo_box_runner.get_active_text()

            if runner == "UMU-Proton Latest":
                runner = ""
            if runner == "GE-Proton Latest (default)":
                runner = "GE-Proton"

            command_parts = []

            # Add command parts if they are not empty

            file_run = dialog.get_filename()
            if not file_run.endswith(".reg"):
                if prefix:
                    command_parts.append(f'WINEPREFIX={prefix}')
                if title_formatted:
                    command_parts.append(f'GAMEID={title_formatted}')
                if runner:
                    command_parts.append(f'PROTONPATH={runner}')
                command_parts.append(f'"{umu_run}" "{file_run}"')
            else:
                if prefix:
                    command_parts.append(f'WINEPREFIX={prefix}')
                if title_formatted:
                    command_parts.append(f'GAMEID={title_formatted}')
                if runner:
                    command_parts.append(f'PROTONPATH={runner}')
                command_parts.append(f'"{umu_run}" regedit "{file_run}"')

            # Join all parts into a single command
            command = ' '.join(command_parts)

            print(command)

            # faugus-run path
            faugus_run_path = faugus_run

            def run_command():
                process = subprocess.Popen([sys.executable, faugus_run_path, command])
                process.wait()
                GLib.idle_add(self.set_sensitive, True)
                GLib.idle_add(self.parent_window.set_sensitive, True)
                GLib.idle_add(self.blocking_window.destroy)

            self.blocking_window = Gtk.Window()
            self.blocking_window.set_transient_for(self.parent_window)
            self.blocking_window.set_decorated(False)
            self.blocking_window.set_modal(True)

            command_thread = threading.Thread(target=run_command)
            command_thread.start()

        else:
            self.set_sensitive(True)
        dialog.destroy()

    def on_button_search_protonfix_clicked(self, widget):
        webbrowser.open("https://umu.openwinecomponents.org/")

    def set_image_shortcut_icon(self):

        image_path = faugus_png
        shutil.copy(image_path, self.icon_temp)

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
        scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_file(self.icon_temp)
        image.set_from_pixbuf(scaled_pixbuf)

        return image

    def on_button_shortcut_icon_clicked(self, widget):
        self.set_sensitive(False)

        validation_result = self.validate_fields(entry="path")
        if not validation_result:
            self.set_sensitive(True)
            return

        path = self.entry_path.get_text()

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        try:
            # Attempt to extract the icon
            command = f'icoextract "{path}" "{self.icon_extracted}"'
            result = subprocess.run(command, shell=True, text=True, capture_output=True)

            # Check if there was an error in executing the command
            if result.returncode != 0:
                if "NoIconsAvailableError" in result.stderr:
                    print("The file does not contain icons.")
                    self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
                else:
                    print(f"Error extracting icon: {result.stderr}")
            else:
                # Convert the extracted icon to PNG
                command_magick = shutil.which("magick") or shutil.which("convert")
                os.system(f'{command_magick} "{self.icon_extracted}" "{self.icon_converted}"')
                if os.path.isfile(self.icon_extracted):
                    os.remove(self.icon_extracted)

        except Exception as e:
            print(f"An error occurred: {e}")

        # Open file dialog to select .ico file
        dialog = Gtk.FileChooserDialog(title="Select an icon for the shortcut", action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        # Add a filter to limit selection to .ico files
        filter_ico = Gtk.FileFilter()
        filter_ico.set_name("Image files")
        filter_ico.add_mime_type("image/*")  # Other image formats
        dialog.add_filter(filter_ico)

        # Set the initial directory to the icon directory
        dialog.set_current_folder(self.icon_directory)

        # Connect signal to update preview widget when file selection changes
        dialog.connect("update-preview", self.update_preview)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            # Move and rename the icon file
            shutil.copy(file_path, self.icon_temp)

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
            scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_file(self.icon_temp)
            image.set_from_pixbuf(scaled_pixbuf)

            self.button_shortcut_icon.set_image(image)

        # Delete the folder after the icon is moved
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        dialog.destroy()
        self.set_sensitive(True)

    def find_largest_resolution(self, directory):
        largest_image = None
        largest_resolution = (0, 0)  # (width, height)

        # Define a set of valid image extensions
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}

        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                # Check if the file has a valid image extension
                if os.path.splitext(file_name)[1].lower() in valid_image_extensions:
                    try:
                        with Image.open(file_path) as img:
                            width, height = img.size
                            if width * height > largest_resolution[0] * largest_resolution[1]:
                                largest_resolution = (width, height)
                                largest_image = file_path
                    except IOError:
                        print(f'Unable to open {file_path}')

        return largest_image

    def update_preview(self, dialog):
        if file_path := dialog.get_preview_filename():
            try:
                # Create an image widget for the thumbnail
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)

                # Resize the thumbnail if it's too large, maintaining the aspect ratio
                max_width = 400
                max_height = 400
                width = pixbuf.get_width()
                height = pixbuf.get_height()

                if width > max_width or height > max_height:
                    # Calculate the new width and height while maintaining the aspect ratio
                    ratio = min(max_width / width, max_height / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)

                image = Gtk.Image.new_from_pixbuf(pixbuf)
                dialog.set_preview_widget(image)
                dialog.set_preview_widget_active(True)
                dialog.get_preview_widget().set_size_request(max_width, max_height)
            except GLib.Error:
                dialog.set_preview_widget_active(False)
        else:
            dialog.set_preview_widget_active(False)

    def check_existing_shortcut(self):
        # Check if the shortcut already exists and mark or unmark the checkbox
        title = self.entry_title.get_text().strip()
        if not title:
            return  # If there's no title, there's no shortcut to check

        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title).replace(' ', '-').lower()
        desktop_file_path = f"{app_dir}/{title_formatted}.desktop"

        # Check if the shortcut file exists
        shortcut_exists = os.path.exists(desktop_file_path)

        # Mark the checkbox if the shortcut exists
        self.checkbox_shortcut.set_active(shortcut_exists)

    def update_prefix_entry(self, entry):
        # Update the prefix entry based on the title and self.default_prefix
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', entry.get_text())
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())
        self.default_prefix = self.load_default_prefix()
        prefix = os.path.expanduser(self.default_prefix) + "/" + title_formatted
        self.entry_prefix.set_text(prefix)

    def on_button_winecfg_clicked(self, widget):
        self.set_sensitive(False)
        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields(entry="prefix")
        if not validation_result:
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        prefix = self.entry_prefix.get_text()

        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        runner = self.combo_box_runner.get_active_text()

        if runner == "UMU-Proton Latest":
            runner = ""
        if runner == "GE-Proton Latest (default)":
            runner = "GE-Proton"

        command_parts = []

        # Add command parts if they are not empty

        if prefix:
            command_parts.append(f'WINEPREFIX={prefix}')
        if title_formatted:
            command_parts.append(f'GAMEID={title_formatted}')
        if runner:
            command_parts.append(f'PROTONPATH={runner}')

        # Add the fixed command and remaining arguments
        command_parts.append(f'"{umu_run}"')
        command_parts.append('"winecfg"')

        # Join all parts into a single command
        command = ' '.join(command_parts)

        print(command)

        # faugus-run path
        faugus_run_path = faugus_run

        def run_command():
            process = subprocess.Popen([sys.executable, faugus_run_path, command])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent_window.set_sensitive, True)
            GLib.idle_add(self.blocking_window.destroy)

        self.blocking_window = Gtk.Window()
        self.blocking_window.set_transient_for(self.parent_window)
        self.blocking_window.set_decorated(False)
        self.blocking_window.set_modal(True)

        command_thread = threading.Thread(target=run_command)
        command_thread.start()

    def on_button_winetricks_clicked(self, widget):
        self.set_sensitive(False)
        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields(entry="prefix")
        if not validation_result:
            self.set_sensitive(True)
            return

        prefix = self.entry_prefix.get_text()

        runner = self.combo_box_runner.get_active_text()

        if runner == "UMU-Proton Latest":
            runner = ""
        if runner == "GE-Proton Latest (default)":
            runner = "GE-Proton"

        command_parts = []

        # Add command parts if they are not empty

        if prefix:
            command_parts.append(f'WINEPREFIX={prefix}')
        command_parts.append(f'GAMEID=winetricks-gui')
        command_parts.append(f'STORE=none')
        if runner:
            command_parts.append(f'PROTONPATH={runner}')

        # Add the fixed command and remaining arguments
        command_parts.append(f'"{umu_run}"')
        command_parts.append('""')

        # Join all parts into a single command
        command = ' '.join(command_parts)

        print(command)

        # faugus-run path
        faugus_run_path = faugus_run

        def run_command():
            process = subprocess.Popen([sys.executable, faugus_run_path, command, "winetricks"])
            process.wait()
            GLib.idle_add(self.set_sensitive, True)
            GLib.idle_add(self.parent_window.set_sensitive, True)
            GLib.idle_add(self.blocking_window.destroy)

        self.blocking_window = Gtk.Window()
        self.blocking_window.set_transient_for(self.parent_window)
        self.blocking_window.set_decorated(False)
        self.blocking_window.set_modal(True)

        command_thread = threading.Thread(target=run_command)
        command_thread.start()

    def on_button_search_clicked(self, widget):
        # Handle the click event of the search button to select the game's .exe
        dialog = Gtk.FileChooserDialog(title="Select the game's .exe", parent=self, action=Gtk.FileChooserAction.OPEN)
        if not self.entry_path.get_text():
            dialog.set_current_folder(os.path.expanduser("~/"))
        else:
            dialog.set_current_folder(os.path.dirname(self.entry_path.get_text()))
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        # Windows files filter
        windows_filter = Gtk.FileFilter()
        windows_filter.set_name("Windows files")
        windows_filter.add_pattern("*.exe")
        windows_filter.add_pattern("*.msi")
        windows_filter.add_pattern("*.bat")
        windows_filter.add_pattern("*.lnk")
        windows_filter.add_pattern("*.reg")
        dialog.add_filter(windows_filter)

        # All files filter
        all_files_filter = Gtk.FileFilter()
        all_files_filter.set_name("All files")
        all_files_filter.add_pattern("*")
        dialog.add_filter(all_files_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()

            if not os.path.exists(self.icon_directory):
                os.makedirs(self.icon_directory)

            try:
                # Attempt to extract the icon
                command = f'icoextract "{path}" "{self.icon_extracted}"'
                result = subprocess.run(command, shell=True, text=True, capture_output=True)

                # Check if there was an error in executing the command
                if result.returncode != 0:
                    if "NoIconsAvailableError" in result.stderr:
                        print("The file does not contain icons.")
                        self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
                    else:
                        print(f"Error extracting icon: {result.stderr}")
                else:
                    # Convert the extracted icon to PNG
                    command_magick = shutil.which("magick") or shutil.which("convert")
                    os.system(f'{command_magick} "{self.icon_extracted}" "{self.icon_converted}"')
                    if os.path.isfile(self.icon_extracted):
                        os.remove(self.icon_extracted)

                    largest_image = self.find_largest_resolution(self.icon_directory)
                    shutil.move(largest_image, os.path.expanduser(self.icon_temp))

                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
                    scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
                    image = Gtk.Image.new_from_file(self.icon_temp)
                    image.set_from_pixbuf(scaled_pixbuf)

                    self.button_shortcut_icon.set_image(image)

            except Exception as e:
                print(f"An error occurred: {e}")

            self.entry_path.set_text(dialog.get_filename())
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)

        dialog.destroy()

    def on_button_search_prefix_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(title="Select a prefix location", parent=self,
                                       action=Gtk.FileChooserAction.SELECT_FOLDER)

        if not self.entry_prefix.get_text():
            dialog.set_current_folder(os.path.expanduser(self.default_prefix))
        else:
            dialog.set_current_folder(self.entry_prefix.get_text())
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_prefix = dialog.get_filename()
            self.default_prefix = new_prefix
            #self.entry_title.emit("changed")
            self.entry_prefix.set_text(self.default_prefix)

        dialog.destroy()

    def validate_fields(self, entry):
        # Validate the input fields for title, prefix and path
        title = self.entry_title.get_text()
        prefix = self.entry_prefix.get_text()
        path = self.entry_path.get_text()

        self.entry_title.get_style_context().remove_class("entry")
        self.entry_prefix.get_style_context().remove_class("entry")
        self.entry_path.get_style_context().remove_class("entry")

        if entry == "prefix":
            if not title or not prefix:
                if not title:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not prefix:
                    self.entry_prefix.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                return False

        if entry == "path":
            if not title or not path:
                if not title:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not path:
                    self.entry_path.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                return False

        if entry == "path+prefix":
            if not title or not path or not prefix:
                if not title:
                    self.entry_title.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not path:
                    self.entry_path.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                if not prefix:
                    self.entry_prefix.get_style_context().add_class("entry")
                    self.notebook.set_current_page(0)

                return False

        return True

class CreateShortcut(Gtk.Window):
    def __init__(self, file_path):
        super().__init__(title="Faugus Launcher")
        self.file_path = file_path
        self.set_resizable(False)
        self.set_icon_from_file(faugus_png)

        game_title = os.path.basename(file_path)
        self.set_title(game_title)
        print(self.file_path)

        self.icon_directory = f"{icons_dir}/icon_temp/"

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        self.icons_path = icons_dir
        self.icon_extracted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.ico')
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.ico'

        self.default_prefix = ""

        self.label_title = Gtk.Label(label="Title")
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", self.on_entry_changed, self.entry_title)
        self.entry_title.set_tooltip_text("Game Title")

        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_protonfix.connect("clicked", self.on_button_search_protonfix_clicked)
        self.button_search_protonfix.set_size_request(50, -1)

        self.label_launch_arguments = Gtk.Label(label="Launch Arguments")
        self.label_launch_arguments.set_halign(Gtk.Align.START)
        self.entry_launch_arguments = Gtk.Entry()
        self.entry_launch_arguments.set_tooltip_text("e.g.: PROTON_USE_WINED3D=1 gamescope -W 2560 -H 1440")

        self.label_game_arguments = Gtk.Label(label="Game Arguments")
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text("e.g.: -d3d11 -fullscreen")

        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_tooltip_text("Select an icon for the shortcut")
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)

        self.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
        self.checkbox_mangohud.set_tooltip_text(
            "Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more.")
        self.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
        self.checkbox_gamemode.set_tooltip_text("Tweaks your system to improve performance.")
        self.checkbox_sc_controller = Gtk.CheckButton(label="SC Controller")
        self.checkbox_sc_controller.set_tooltip_text(
            "Emulates a Xbox controller if the game doesn't support yours. Put the profile at ~/.config/faugus-launcher/controller.sccprofile.")

        # Button Cancel
        self.button_cancel = Gtk.Button(label="Cancel")
        self.button_cancel.connect("clicked", self.on_cancel_clicked)
        self.button_cancel.set_size_request(120, -1)
        self.button_cancel.set_halign(Gtk.Align.CENTER)

        # Button Ok
        self.button_ok = Gtk.Button(label="Ok")
        self.button_ok.connect("clicked", self.on_ok_clicked)
        self.button_ok.set_size_request(120, -1)
        self.button_ok.set_halign(Gtk.Align.CENTER)

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)

        # Create the Grids
        self.grid1 = Gtk.Grid()
        self.grid1.set_row_spacing(10)
        self.grid1.set_column_spacing(10)
        self.grid1.set_margin_start(10)
        self.grid1.set_margin_end(10)
        self.grid1.set_margin_top(10)
        self.grid1.set_margin_bottom(10)
        self.grid1.set_valign(Gtk.Align.CENTER)

        self.grid2 = Gtk.Grid()
        self.grid2.set_row_spacing(10)
        self.grid2.set_column_spacing(10)
        self.grid2.set_margin_start(10)
        self.grid2.set_margin_end(10)
        self.grid2.set_margin_top(10)
        self.grid2.set_margin_bottom(10)

        self.grid3 = Gtk.Grid()
        self.grid3.set_row_spacing(10)
        self.grid3.set_column_spacing(10)
        self.grid3.set_margin_start(10)
        self.grid3.set_margin_end(10)
        self.grid3.set_margin_top(10)
        self.grid3.set_margin_bottom(10)
        self.grid3.set_valign(Gtk.Align.CENTER)
        self.grid3.set_halign(Gtk.Align.END)

        self.grid4 = Gtk.Grid()
        self.grid4.set_row_spacing(10)
        self.grid4.set_column_spacing(10)
        self.grid4.set_margin_start(10)
        self.grid4.set_margin_end(10)
        self.grid4.set_margin_top(10)
        self.grid4.set_margin_bottom(10)

        self.entry_title.set_hexpand(True)
        self.entry_title.set_valign(Gtk.Align.CENTER)
        self.grid1.attach(self.label_title, 0, 0, 1, 1)
        self.grid1.attach(self.entry_title, 0, 1, 4, 1)

        self.grid1.attach(self.label_protonfix, 0, 2, 1, 1)
        self.grid1.attach(self.entry_protonfix, 0, 3, 3, 1)
        self.entry_protonfix.set_hexpand(True)
        self.grid1.attach(self.button_search_protonfix, 3, 3, 1, 1)
        self.grid1.attach(self.label_launch_arguments, 0, 4, 1, 1)
        self.grid1.attach(self.entry_launch_arguments, 0, 5, 4, 1)
        self.entry_launch_arguments.set_hexpand(True)

        self.grid1.attach(self.label_game_arguments, 0, 6, 1, 1)
        self.grid1.attach(self.entry_game_arguments, 0, 7, 4, 1)
        self.entry_game_arguments.set_hexpand(True)

        self.grid2.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.grid2.attach(self.checkbox_gamemode, 0, 1, 1, 1)
        self.grid2.attach(self.checkbox_sc_controller, 0, 2, 1, 1)

        self.grid3.attach(self.button_shortcut_icon, 0, 0, 1, 1)

        self.grid4.attach(self.button_cancel, 0, 0, 1, 1)
        self.grid4.attach(self.button_ok, 1, 0, 1, 1)

        # Create a main grid to hold the grids
        self.main_grid = Gtk.Grid()

        # Attach grid1 and grid2 to the main grid in the same row
        self.main_grid.attach(self.grid1, 0, 0, 2, 1)
        self.main_grid.attach(self.grid2, 0, 1, 2, 1)
        self.main_grid.attach(self.grid3, 1, 1, 1, 1)

        # Attach grid3 to the main grid in the next row
        self.main_grid.attach(self.grid4, 0, 2, 2, 1)

        self.load_config()

        # Check if optional features are available and enable/disable accordingly
        self.mangohud_enabled = os.path.exists(mangohud_dir)
        if not self.mangohud_enabled:
            self.checkbox_mangohud.set_sensitive(False)
            self.checkbox_mangohud.set_active(False)
            self.checkbox_mangohud.set_tooltip_text(
                "Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more. NOT INSTALLED.")

        self.gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
        if not self.gamemode_enabled:
            self.checkbox_gamemode.set_sensitive(False)
            self.checkbox_gamemode.set_active(False)
            self.checkbox_gamemode.set_tooltip_text("Tweaks your system to improve performance. NOT INSTALLED.")

        self.sc_controller_enabled = os.path.exists("/usr/bin/sc-controller") or os.path.exists(
            "/usr/local/bin/sc-controller")
        if not self.sc_controller_enabled:
            self.checkbox_sc_controller.set_sensitive(False)
            self.checkbox_sc_controller.set_active(False)
            self.checkbox_sc_controller.set_tooltip_text(
                "Emulates a Xbox controller if the game doesn't support yours. Put the profile at ~/.config/faugus-launcher/controller.sccprofile. NOT INSTALLED.")

        # Add the main grid to the window
        self.add(self.main_grid)

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game_title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        try:
            # Attempt to extract the icon
            command = f'icoextract "{file_path}" "{self.icon_extracted}"'
            result = subprocess.run(command, shell=True, text=True, capture_output=True)

            # Check if there was an error in executing the command
            if result.returncode != 0:
                if "NoIconsAvailableError" in result.stderr:
                    print("The file does not contain icons.")
                    self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
                else:
                    print(f"Error extracting icon: {result.stderr}")
            else:
                # Convert the extracted icon to PNG
                command_magick = shutil.which("magick") or shutil.which("convert")
                os.system(f'{command_magick} "{self.icon_extracted}" "{self.icon_converted}"')
                if os.path.isfile(self.icon_extracted):
                    os.remove(self.icon_extracted)

                largest_image = self.find_largest_resolution(self.icon_directory)
                shutil.move(largest_image, os.path.expanduser(self.icon_temp))

                pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
                scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
                image = Gtk.Image.new_from_file(self.icon_temp)
                image.set_from_pixbuf(scaled_pixbuf)

                self.button_shortcut_icon.set_image(image)

        except Exception as e:
            print(f"An error occurred: {e}")

        shutil.rmtree(self.icon_directory)

        # Connect the destroy signal to Gtk.main_quit
        self.connect("destroy", Gtk.main_quit)

    def find_largest_resolution(self, directory):
        largest_image = None
        largest_resolution = (0, 0)  # (width, height)

        # Define a set of valid image extensions
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}

        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                # Check if the file has a valid image extension
                if os.path.splitext(file_name)[1].lower() in valid_image_extensions:
                    try:
                        with Image.open(file_path) as img:
                            width, height = img.size
                            if width * height > largest_resolution[0] * largest_resolution[1]:
                                largest_resolution = (width, height)
                                largest_image = file_path
                    except IOError:
                        print(f'Unable to open {file_path}')

        return largest_image

    def on_button_search_protonfix_clicked(self, widget):
        webbrowser.open("https://umu.openwinecomponents.org/")

    def load_config(self):
        # Load configuration from file
        config_file = config_file_dir
        if os.path.isfile(config_file):
            with open(config_file, 'r') as f:
                config_data = f.read().splitlines()
            config_dict = dict(line.split('=') for line in config_data)
            self.default_prefix = config_dict.get('default-prefix', '').strip('"')

            mangohud = config_dict.get('mangohud', 'False') == 'True'
            gamemode = config_dict.get('gamemode', 'False') == 'True'
            sc_controller = config_dict.get('sc-controller', 'False') == 'True'
            self.default_runner = config_dict.get('default-runner', '').strip('"')

            self.checkbox_mangohud.set_active(mangohud)
            self.checkbox_gamemode.set_active(gamemode)
            self.checkbox_sc_controller.set_active(sc_controller)

        else:
            # Save default configuration if file does not exist
            self.save_config(False, '', "False", "False", "False", "GE-Proton", "True", "False", "False", "False")

    def save_config(self, checkbox_state, default_prefix, mangohud_state, gamemode_state, sc_controller_state, default_runner, checkbox_discrete_gpu_state, checkbox_splash_disable, checkbox_system_tray, checkbox_start_boot):
        # Path to the configuration file
        config_file = config_file_dir

        config_path = faugus_launcher_dir
        # Create the configuration directory if it doesn't exist
        if not os.path.exists(config_path):
            os.makedirs(config_path)

        default_prefix = prefixes_dir
        self.default_prefix = prefixes_dir

        default_runner = (f'"{default_runner}"')

        # Dictionary to store existing configurations
        config = {}

        # Read the existing configuration file
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                for line in f:
                    key, value = line.strip().split('=', 1)
                    config[key] = value.strip('"')

        # Update configurations with new values
        config['close-onlaunch'] = checkbox_state
        config['default-prefix'] = default_prefix
        config['mangohud'] = mangohud_state
        config['gamemode'] = gamemode_state
        config['sc-controller'] = sc_controller_state
        config['default-runner'] = default_runner
        config['discrete-gpu'] = checkbox_discrete_gpu_state
        config['splash-disable'] = checkbox_splash_disable
        config['system-tray'] = checkbox_system_tray
        config['start-boot'] = checkbox_start_boot

        # Write configurations back to the file
        with open(config_file, 'w') as f:
            for key, value in config.items():
                if key == 'default-prefix':
                    f.write(f'{key}="{value}"\n')
                else:
                    f.write(f'{key}={value}\n')


    def on_cancel_clicked(self, widget):
        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.destroy()

    def on_ok_clicked(self, widget):

        validation_result = self.validate_fields()
        if not validation_result:
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        if os.path.isfile(os.path.expanduser(self.icon_temp)):
            os.rename(os.path.expanduser(self.icon_temp),f'{self.icons_path}/{title_formatted}.ico')

        # Check if the icon file exists
        icons_path = icons_dir
        new_icon_path = f"{icons_dir}/{title_formatted}.ico"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        protonfix = self.entry_protonfix.get_text()
        launch_arguments = self.entry_launch_arguments.get_text()
        game_arguments = self.entry_game_arguments.get_text()

        mangohud = "MANGOHUD=1" if self.checkbox_mangohud.get_active() else ""
        gamemode = "gamemoderun" if self.checkbox_gamemode.get_active() else ""
        sc_controller = "SC_CONTROLLER=1" if self.checkbox_sc_controller.get_active() else ""

        # Get the directory containing the executable
        game_directory = os.path.dirname(self.file_path)

        command_parts = []

        # Add command parts if they are not empty
        if mangohud:
            command_parts.append(mangohud)
        if sc_controller:
            command_parts.append(sc_controller)

        #command_parts.append(f'WINEPREFIX={self.default_prefix}/default')

        if protonfix:
            command_parts.append(f'GAMEID={protonfix}')
        else:
            command_parts.append(f'GAMEID={title_formatted}')

        if gamemode:
            command_parts.append(gamemode)
        if launch_arguments:
            command_parts.append(launch_arguments)

        # Add the fixed command and remaining arguments
        command_parts.append(f"'{umu_run}'")
        if self.file_path:
            command_parts.append(f"'{self.file_path}'")
        if game_arguments:
            command_parts.append(f"'{game_arguments}'")

        # Join all parts into a single command
        command = ' '.join(command_parts)

        # Create a .desktop file
        desktop_file_content = f"""[Desktop Entry]
    Name={title}
    Exec={faugus_run} "{command}"
    Icon={new_icon_path}
    Type=Application
    Categories=Game;
    Path={game_directory}
    """

        # Check if the destination directory exists and create if it doesn't
        applications_directory = app_dir
        if not os.path.exists(applications_directory):
            os.makedirs(applications_directory)

        desktop_directory = desktop_dir
        if not os.path.exists(desktop_directory):
            os.makedirs(desktop_directory)

        applications_shortcut_path = f"{app_dir}/{title_formatted}.desktop"

        with open(applications_shortcut_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        # Make the .desktop file executable
        os.chmod(applications_shortcut_path, 0o755)

        # Copy the shortcut to Desktop
        desktop_shortcut_path = f"{desktop_dir}/{title_formatted}.desktop"
        shutil.copy(applications_shortcut_path, desktop_shortcut_path)

        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.destroy()

    def on_entry_changed(self, widget, entry):
        if entry.get_text():
            entry.get_style_context().remove_class("entry")

    def set_image_shortcut_icon(self):
        image_path = faugus_png

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
        scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(scaled_pixbuf)
        return image

    def on_button_shortcut_icon_clicked(self, widget):

        path = self.file_path

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        try:
            # Attempt to extract the icon
            command = f'icoextract "{path}" "{self.icon_extracted}"'
            result = subprocess.run(command, shell=True, text=True, capture_output=True)

            # Check if there was an error in executing the command
            if result.returncode != 0:
                if "NoIconsAvailableError" in result.stderr:
                    print("The file does not contain icons.")
                    self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
                else:
                    print(f"Error extracting icon: {result.stderr}")
            else:
                # Convert the extracted icon to PNG
                command_magick = shutil.which("magick") or shutil.which("convert")
                os.system(f'{command_magick} "{self.icon_extracted}" "{self.icon_converted}"')
                if os.path.isfile(self.icon_extracted):
                    os.remove(self.icon_extracted)

        except Exception as e:
            print(f"An error occurred: {e}")

        # Open file dialog to select .ico file
        dialog = Gtk.FileChooserDialog(title="Select an icon for the shortcut", action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        # Add a filter to limit selection to .ico files
        filter_ico = Gtk.FileFilter()
        filter_ico.set_name("Image files")
        filter_ico.add_mime_type("image/*")  # Other image formats
        dialog.add_filter(filter_ico)

        # Set the initial directory to the icon directory
        dialog.set_current_folder(self.icon_directory)

        # Connect signal to update preview widget when file selection changes
        dialog.connect("update-preview", self.update_preview)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            # Move and rename the icon file
            shutil.copy(file_path, self.icon_temp)

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.icon_temp)
            scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)
            image = Gtk.Image.new_from_file(self.icon_temp)
            image.set_from_pixbuf(scaled_pixbuf)

            self.button_shortcut_icon.set_image(image)

        # Delete the folder after the icon is moved
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        dialog.destroy()
        self.set_sensitive(True)

    def update_preview(self, dialog):
        if file_path := dialog.get_preview_filename():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(file_path)
                max_width = 400
                max_height = 400
                width = pixbuf.get_width()
                height = pixbuf.get_height()

                if width > max_width or height > max_height:
                    ratio = min(max_width / width, max_height / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    pixbuf = pixbuf.scale_simple(new_width, new_height, GdkPixbuf.InterpType.BILINEAR)

                image = Gtk.Image.new_from_pixbuf(pixbuf)
                dialog.set_preview_widget(image)
                dialog.set_preview_widget_active(True)
                dialog.get_preview_widget().set_size_request(max_width, max_height)
            except GLib.Error:
                dialog.set_preview_widget_active(False)
        else:
            dialog.set_preview_widget_active(False)

    def validate_fields(self):

        title = self.entry_title.get_text()

        self.entry_title.get_style_context().remove_class("entry")

        if not title:
            self.entry_title.get_style_context().add_class("entry")
            return False

        return True

def run_file(file_path):
    config_file = config_file_dir
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            config_data = f.read().splitlines()
        config_dict = dict(line.split('=') for line in config_data)
        default_prefix = config_dict.get('default-prefix', '').strip('"')
        mangohud = config_dict.get('mangohud', 'False') == 'True'
        gamemode = config_dict.get('gamemode', 'False') == 'True'
        sc_controller = config_dict.get('sc-controller', 'False') == 'True'
        default_runner = config_dict.get('default-runner', '').strip('"')
    else:
        # Define the configuration path
        config_path = faugus_launcher_dir
        # Create the configuration directory if it doesn't exist
        if not os.path.exists(config_path):
            os.makedirs(config_path)

        default_prefix = prefixes_dir
        mangohud = 'False'
        gamemode = 'False'
        sc_controller = 'False'
        default_runner = 'GE-Proton'

        with open(config_file, 'w') as f:
            f.write(f'close-onlaunch=False\n')
            f.write(f'default-prefix="{default_prefix}"\n')
            f.write(f'mangohud=False\n')
            f.write(f'gamemode=False\n')
            f.write(f'sc-controller=False\n')
            f.write(f'default_runner="GE-Proton"\n')

    if not file_path.endswith(".reg"):
        mangohud = "MANGOHUD=1" if mangohud else ""
        gamemode = "gamemoderun" if gamemode else ""
        sc_controller = "SC_CONTROLLER=1" if sc_controller else ""

    # Get the directory of the file
    file_dir = os.path.dirname(os.path.abspath(file_path))

    # Define paths
    prefix_path = os.path.expanduser(f"{default_prefix}/default")
    faugus_run_path = faugus_run

    if not file_path.endswith(".reg"):
        mangohud_enabled = os.path.exists(mangohud_dir)
        gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
        sc_controller_enabled = os.path.exists("/usr/bin/sc-controller") or os.path.exists("/usr/local/bin/sc-controller")

    if default_runner == "UMU-Proton Latest":
        default_runner = ""
    if default_runner == "GE-Proton Latest (default)":
        default_runner = "GE-Proton"

    command_parts = []

    if not file_path.endswith(".reg"):
        # Add command parts if they are not empty
        if mangohud_enabled and mangohud:
            command_parts.append(mangohud)
        if sc_controller_enabled and sc_controller:
            command_parts.append(sc_controller)
    command_parts.append(os.path.expanduser(f"WINEPREFIX={default_prefix}/default"))
    command_parts.append('GAMEID=default')
    if default_runner:
        command_parts.append(f'PROTONPATH={default_runner}')
    if not file_path.endswith(".reg"):
        if gamemode_enabled and gamemode:
            command_parts.append(gamemode)

    # Add the fixed command and remaining arguments
    command_parts.append(f'"{umu_run}"')
    if file_path.endswith(".reg"):
        command_parts.append(f'regedit "{file_path}"')
    else:
        command_parts.append(f'"{file_path}"')

    # Join all parts into a single command
    command = ' '.join(command_parts)

    # Run the command in the directory of the file
    subprocess.run([faugus_run_path, command], cwd=file_dir)

def main():
    if len(sys.argv) == 1:
        app = Main()
        if is_already_running():
            print("Faugus Launcher is already running.")
            sys.exit(0)
        app.show_all()
        app.connect("destroy", on_app_destroy)
        Gtk.main()
    elif len(sys.argv) == 2 and sys.argv[1] == "hide":
        app = Main()
        if is_already_running():
            print("Faugus Launcher is already running.")
            sys.exit(0)
        app.hide()
        app.connect("destroy", on_app_destroy)
        Gtk.main()
    elif len(sys.argv) == 2:
        run_file(sys.argv[1])
    elif len(sys.argv) == 3 and sys.argv[2] == "shortcut":
        app = CreateShortcut(sys.argv[1])
        app.show_all()
        Gtk.main()
    else:
        print("Invalid arguments")

def on_app_destroy(*args):
    if os.path.exists(lock_file_path):
        os.remove(lock_file_path)
    Gtk.main_quit()

if __name__ == "__main__":
    main()
