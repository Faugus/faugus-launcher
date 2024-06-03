#!/usr/bin/env python3

import os
import re
import shutil
import signal
import subprocess

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib


class Main(Gtk.Window):
    def __init__(self):
        # Initialize the main window with title and default size
        Gtk.Window.__init__(self, title="Faugus Launcher")
        self.set_default_size(580, 580)

        self.game_running = None

        # Define the configuration path
        config_path = os.path.expanduser("~/.config/faugus-launcher/")
        # Create the configuration directory if it doesn't exist
        if not os.path.exists(config_path):
            os.makedirs(config_path)
        self.working_directory = config_path
        os.chdir(self.working_directory)

        self.games = []

        # Create main box and its components
        box_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box_left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box_right.set_border_width(10)
        box_bottom = Gtk.Box()

        # Create buttons for adding, editing, and deleting games
        self.button_add = Gtk.Button(label="New")
        self.button_add.connect("clicked", self.on_button_add_clicked)
        self.button_add.set_size_request(50, 50)
        self.button_add.set_margin_top(10)
        self.button_add.set_margin_start(10)
        self.button_add.set_margin_end(10)

        self.button_edit = Gtk.Button(label="Edit")
        self.button_edit.connect("clicked", self.on_button_edit_clicked)
        self.button_edit.set_size_request(50, 50)
        self.button_edit.set_margin_top(10)
        self.button_edit.set_margin_start(10)
        self.button_edit.set_margin_end(10)

        self.button_delete = Gtk.Button(label="Del")
        self.button_delete.connect("clicked", self.on_button_delete_clicked)
        self.button_delete.set_size_request(50, 50)
        self.button_delete.set_margin_top(10)
        self.button_delete.set_margin_start(10)
        self.button_delete.set_margin_end(10)

        # Create checkbox for 'Close after launch' option
        self.checkbox_close_after_launch = Gtk.CheckButton(label="Close after launch")
        self.checkbox_close_after_launch.set_margin_top(10)
        self.checkbox_close_after_launch.set_margin_end(10)
        self.checkbox_close_after_launch.set_margin_bottom(10)
        self.checkbox_close_after_launch.set_active(False)
        self.checkbox_close_after_launch.set_active(self.load_config())
        self.checkbox_close_after_launch.connect("toggled", self.on_checkbox_toggled)

        # Create button for killing processes
        button_kill = Gtk.Button(label="Kill")
        button_kill.connect("clicked", self.on_button_kill_clicked)
        button_kill.set_size_request(50, 50)
        button_kill.set_margin_top(10)
        button_kill.set_margin_end(10)
        button_kill.set_margin_bottom(10)

        # Create button for launching games
        self.button_play = Gtk.Button()
        self.button_play.connect("clicked", self.on_button_play_clicked)
        self.button_play.set_size_request(150, 50)
        self.button_play.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))
        self.button_play.set_border_width(10)

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
        scroll_box.add(self.game_list)
        self.load_games()

        # Pack buttons and other components into the bottom box
        box_bottom.pack_start(self.button_play, False, False, 0)
        box_bottom.pack_end(button_kill, False, False, 0)
        box_bottom.pack_end(self.checkbox_close_after_launch, False, False, 0)

        # Pack buttons into the left box
        box_left.pack_start(self.button_add, False, False, 0)
        box_left.pack_start(self.button_edit, False, False, 0)
        box_left.pack_start(self.button_delete, False, False, 0)

        # Pack left and scrolled box into the top box
        box_top.pack_start(box_left, False, True, 0)
        box_top.pack_start(scroll_box, True, True, 0)

        # Pack top and bottom boxes into the main box
        box_main.pack_start(box_top, True, True, 0)
        box_main.pack_end(box_bottom, False, True, 0)
        self.add(box_main)

        # Set signal handler for child process termination
        signal.signal(signal.SIGCHLD, self.on_child_process_closed)

    def on_button_play_clicked(self, widget):
        # Handle play button click event
        listbox_row = self.game_list.get_selected_row()
        if listbox_row:
            # Get the selected game's title
            hbox = listbox_row.get_child()
            game_label = hbox.get_children()[0]
            title = game_label.get_text()
            # Find the selected game object
            game = next((j for j in self.games if j.title == title), None)
            if game and self.game_running is None:
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

                # Determine if gamemode is enabled
                gamemode = ""
                gamemode_enabled = os.path.exists("/usr/bin/gamemoderun")
                if gamemode_enabled:
                    gamemode = game.gamemode

                # Construct the command for game launch
                command = (f'{mangohud} '
                           f'WINEPREFIX={prefix} '
                           f'GAMEID={title_formatted} '
                           f'{launch_arguments} '
                           f'{gamemode} '
                           f'"/usr/bin/umu-run" "{path}" "{game_arguments}"')

                print(command)

                # Launch the game with subprocess
                if self.checkbox_close_after_launch.get_active():
                    subprocess.Popen(["/bin/bash", "-c", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    import sys
                    sys.exit()
                else:
                    self.game_running = subprocess.Popen(["/bin/bash", "-c", command])
                    self.button_play.set_image(
                        Gtk.Image.new_from_icon_name("media-playback-stop-symbolic", Gtk.IconSize.BUTTON))

                self.button_play.set_sensitive(False)

    def on_button_kill_clicked(self, widget):
        # Handle kill button click event
        if self.game_running is not None:
            subprocess.run(r"ls -l /proc/*/exe 2>/dev/null | grep -E 'wine(64)?-preloader|wineserver' | perl "
                           r"-pe 's;^.*/proc/(\d+)/exe.*$;$1;g;' | xargs -n 1 kill | killall -s9 winedevice.exe tee",
                           shell=True)
            self.game_running.wait()
            self.game_running = None
        else:
            subprocess.run(r"ls -l /proc/*/exe 2>/dev/null | grep -E 'wine(64)?-preloader|wineserver' | perl "
                           r"-pe 's;^.*/proc/(\d+)/exe.*$;$1;g;' | xargs -n 1 kill | killall -s9 winedevice.exe tee",
                           shell=True)
        self.button_play.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))

    def on_button_add_clicked(self, widget):
        # Handle add button click event
        add_game_dialog = AddGame(self)
        add_game_dialog.connect("response", self.on_dialog_response, add_game_dialog)

        add_game_dialog.show()

    def on_button_edit_clicked(self, widget):
        # Handle edit button click event
        listbox_row = self.game_list.get_selected_row()
        if listbox_row:
            hbox = listbox_row.get_child()
            game_label = hbox.get_children()[0]
            title = game_label.get_text()
            game = next((j for j in self.games if j.title == title), None)
            if game:
                edit_game_dialog = AddGame(self)
                edit_game_dialog.connect("response", self.on_edit_dialog_response, edit_game_dialog, game)
                edit_game_dialog.entry_title.set_text(game.title)
                edit_game_dialog.entry_path.set_text(game.path)
                edit_game_dialog.entry_prefix.set_text(game.prefix)
                edit_game_dialog.entry_launch_arguments.set_text(game.launch_arguments)
                edit_game_dialog.entry_game_arguments.set_text(game.game_arguments)

                mangohud_status = False
                gamemode_status = False
                with open("games.txt", "r") as file:
                    for line in file:
                        fields = line.strip().split(";")
                        if len(fields) >= 7 and fields[0] == game.title:
                            mangohud_status = fields[5] == "MANGOHUD=1"
                            gamemode_status = fields[6] == "gamemoderun"

                edit_game_dialog.checkbox_mangohud.set_active(mangohud_status)
                edit_game_dialog.checkbox_gamemode.set_active(gamemode_status)
                edit_game_dialog.check_existing_shortcut()

                image = self.set_image_shortcut_icon(game.title)
                edit_game_dialog.button_shortcut_icon.set_image(image)

                edit_game_dialog.show()

    def set_image_shortcut_icon(self, title):

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        # Check if the icon file exists
        icons_path = os.path.expanduser(f"~/.config/faugus-launcher/icons/")
        new_icon_path = os.path.join(icons_path, f"{title_formatted}.ico")

        if os.path.exists(new_icon_path):
            image_path = f"{icons_path}{title_formatted}.ico"

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

            image = Gtk.Image.new_from_file(image_path)
            image.set_from_pixbuf(scaled_pixbuf)

        if not os.path.exists(new_icon_path):
            image_path = "/usr/share/icons/faugus-launcher.png"

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

            image = Gtk.Image.new_from_file(image_path)
            image.set_from_pixbuf(scaled_pixbuf)

        return image

    def on_button_delete_clicked(self, widget):
        # Handle delete button click event
        listbox_row = self.game_list.get_selected_row()
        if listbox_row:
            # Retrieve the selected game's title
            hbox = listbox_row.get_child()
            game_label = hbox.get_children()[0]
            title = game_label.get_text()
            # Find the selected game object
            game = next((j for j in self.games if j.title == title), None)
            if game:
                # Display confirmation dialog
                confirmation_dialog = ConfirmationDialog(self)
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

                confirmation_dialog.destroy()

    def on_dialog_response(self, dialog, response_id, add_game_dialog):
        # Handle dialog response
        if response_id == Gtk.ResponseType.OK:
            # Check if fields are validated
            if not add_game_dialog.validate_fields():
                # If fields are not validated, return and keep the dialog open
                return True
            else:
                # Proceed with adding the game
                # Get game information from dialog fields
                title = add_game_dialog.entry_title.get_text()
                path = add_game_dialog.entry_path.get_text()
                launch_arguments = add_game_dialog.entry_launch_arguments.get_text()
                game_arguments = add_game_dialog.entry_game_arguments.get_text()
                prefix = add_game_dialog.entry_prefix.get_text()

                # Concatenate game information
                game_info = (f"{title};{path};{prefix};{launch_arguments};{game_arguments}")

                # Determine mangohud and gamemode status
                mangohud = "MANGOHUD=1" if add_game_dialog.checkbox_mangohud.get_active() else ""
                gamemode = "gamemoderun" if add_game_dialog.checkbox_gamemode.get_active() else ""

                game_info += f";{mangohud};{gamemode}\n"

                # Write game info to file
                with open("games.txt", "a") as file:
                    file.write(game_info)

                # Create Game object and update UI
                game = Game(title, path, prefix, launch_arguments, game_arguments, mangohud, gamemode)
                self.games.append(game)
                self.add_item_list(game)
                self.update_list()

                # Determine the state of the shortcut checkbox
                shortcut_state = add_game_dialog.checkbox_shortcut.get_active()

                # Call add_remove_shortcut method
                self.add_shortcut(game, shortcut_state)
        else:
            add_game_dialog.destroy()

        # Ensure the dialog is destroyed when canceled
        add_game_dialog.destroy()

    def on_edit_dialog_response(self, dialog, response_id, edit_game_dialog, game):
        # Handle edit dialog response
        if response_id == Gtk.ResponseType.OK:
            # Check if fields are validated
            if not edit_game_dialog.validate_fields():
                # If fields are not validated, return and keep the dialog open
                return True
            else:
                # Update game object with new information
                game.title = edit_game_dialog.entry_title.get_text()
                game.path = edit_game_dialog.entry_path.get_text()
                game.prefix = edit_game_dialog.entry_prefix.get_text()
                game.launch_arguments = edit_game_dialog.entry_launch_arguments.get_text()
                game.game_arguments = edit_game_dialog.entry_game_arguments.get_text()
                game.mangohud = edit_game_dialog.checkbox_mangohud.get_active()
                game.gamemode = edit_game_dialog.checkbox_gamemode.get_active()

                # Save changes and update UI
                self.save_games()
                self.update_list()

                # Determine the state of the shortcut checkbox
                shortcut_state = edit_game_dialog.checkbox_shortcut.get_active()

                # Call add_remove_shortcut method
                self.add_shortcut(game, shortcut_state)

        edit_game_dialog.destroy()

    def add_shortcut(self, game, shortcut_state):
        # Check if the shortcut checkbox is checked
        if not shortcut_state:
            # Remove existing shortcut if it exists
            self.remove_shortcut(game)
            return

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        prefix = game.prefix
        path = game.path
        launch_arguments = game.launch_arguments
        game_arguments = game.game_arguments

        mangohud = ""
        if game.mangohud:
            mangohud = "MANGOHUD=1"

        gamemode = ""
        if game.gamemode:
            gamemode = "gamemoderun"

        # Check if the icon file exists
        icons_path = os.path.expanduser(f"~/.config/faugus-launcher/icons/")
        new_icon_path = os.path.join(icons_path, f"{title_formatted}.ico")
        if not os.path.exists(new_icon_path):
            new_icon_path = "/usr/share/icons/faugus-launcher.png"

        command = (f'{mangohud} '
                   f'WINEPREFIX={prefix} '
                   f'GAMEID={title_formatted} '
                   f'{launch_arguments} '
                   f'{gamemode} '
                   f'"/usr/bin/umu-run" "{path}" "{game_arguments}"')

        # Create a .desktop file
        desktop_file_content = f"""[Desktop Entry]
    Name={game.title}
    Exec=sh -c '{command}'
    Icon={new_icon_path}
    Type=Application
    Categories=Game;
    Path={os.path.expanduser("~/.config/faugus-launcher/")}
    """

        # Check if the destination directory exists and create if it doesn't
        desktop_directory = os.path.expanduser("~/.local/share/applications/")
        if not os.path.exists(desktop_directory):
            os.makedirs(desktop_directory)

        desktop_file_path = os.path.expanduser(f"~/.local/share/applications/{title_formatted}.desktop")

        with open(desktop_file_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        # Make the .desktop file executable
        os.chmod(desktop_file_path, 0o755)

        # Copy the shortcut to Desktop
        desktop_shortcut_path = os.path.expanduser(f"~/Desktop/{title_formatted}.desktop")
        shutil.copy(desktop_file_path, desktop_shortcut_path)

    def update_preview(self, dialog):
        # Updates the preview widget with the selected image's thumbnail
        file_path = dialog.get_preview_filename()
        if file_path:
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

        desktop_file_path = os.path.expanduser(f"~/.local/share/applications/{title_formatted}.desktop")

        if os.path.exists(desktop_file_path):
            os.remove(desktop_file_path)

        # Remove shortcut from Desktop if exists
        desktop_shortcut_path = os.path.expanduser(f"~/Desktop/{title_formatted}.desktop")
        if os.path.exists(desktop_shortcut_path):
            os.remove(desktop_shortcut_path)

        # Remove icon file
        icon_file_path = os.path.expanduser(f"~/.config/faugus-launcher/icons/{title_formatted}.ico")
        if os.path.exists(icon_file_path):
            os.remove(icon_file_path)

    def create_desktop_entry(self, game, shortcut_state):
        # Create the .desktop file in ~/.local/share/applications/
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', game.title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        prefix = game.prefix
        path = game.path
        launch_arguments = game.launch_arguments
        game_arguments = game.game_arguments

        mangohud = ""
        if game.mangohud:
            mangohud = "MANGOHUD=1"

        gamemode = ""
        if game.gamemode:
            gamemode = "gamemoderun"

        command = (f'{mangohud} '
                   f'WINEPREFIX={prefix} '
                   f'GAMEID={title_formatted} '
                   f'{launch_arguments} '
                   f'{gamemode} '
                   f'"/usr/bin/umu-run" "{path}" "{game_arguments}"')

        desktop_file_content = f"""[Desktop Entry]
                                Name={game.title}
                                Exec=sh -c '{command}'
                                Icon=application-x-executable
                                Type=Application
                                Categories=Game;
                                """

        desktop_directory = os.path.expanduser("~/.local/share/applications/")
        if not os.path.exists(desktop_directory):
            os.makedirs(desktop_directory)

        desktop_file_path = os.path.expanduser(f"~/.local/share/applications/{game.title}.desktop")

        with open(desktop_file_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        os.chmod(desktop_file_path, 0o755)

    def remove_desktop_entry(self, game):
        # Remove the .desktop file from ~/.local/share/applications/
        desktop_file_path = os.path.expanduser(f"~/.local/share/applications/{game.title}.desktop")

        if os.path.exists(desktop_file_path):
            os.remove(desktop_file_path)

    def remove_shortcut_from_desktop(self, game):
        # Remove the shortcut from the desktop if it exists
        desktop_link_path = os.path.expanduser(f"~/Desktop/{game.title}.desktop")

        if os.path.exists(desktop_link_path):
            os.remove(desktop_link_path)

    def add_item_list(self, game):
        # Add a game item to the list
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox.set_border_width(10)
        hbox.set_size_request(500, -1)

        game_label = Gtk.Label.new(game.title)
        hbox.pack_start(game_label, True, True, 0)

        listbox_row = Gtk.ListBoxRow()
        listbox_row.add(hbox)
        listbox_row.set_activatable(False)
        listbox_row.set_can_focus(False)
        listbox_row.set_selectable(True)
        self.game_list.add(listbox_row)

        hbox.set_halign(Gtk.Align.CENTER)
        listbox_row.set_valign(Gtk.Align.START)

        self.button_edit.set_sensitive(False)
        self.button_delete.set_sensitive(False)
        self.button_play.set_sensitive(False)

    def update_list(self):
        # Update the game list
        for row in self.game_list.get_children():
            self.game_list.remove(row)

        self.games.clear()
        self.load_games()
        self.show_all()

    def on_child_process_closed(self, signum, frame):
        # Handle child process closing
        if self.game_running and self.game_running.poll() is not None:
            self.game_running = None
        self.button_play.set_sensitive(True)
        self.button_play.set_image(Gtk.Image.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.BUTTON))

    def load_games(self):
        # Load games from file
        try:
            with open("games.txt", "r") as file:
                for line in file:
                    data = line.strip().split(";")
                    if len(data) >= 5:
                        title, path, prefix, launch_arguments, game_arguments = data[:5]
                        if len(data) >= 7:
                            mangohud = data[5]
                            gamemode = data[6]
                        else:
                            mangohud = ""
                            gamemode = ""
                        game = Game(title, path, prefix, launch_arguments, game_arguments, mangohud, gamemode)
                        self.games.append(game)
                self.games = sorted(self.games, key=lambda x: x.title.lower())
                self.game_list.foreach(Gtk.Widget.destroy)
                for game in self.games:
                    self.add_item_list(game)
        except FileNotFoundError:
            pass

    def save_games(self):
        # Save game information to file
        with open("games.txt", "w") as file:
            for game in self.games:
                # Determine mangohud and gamemode values
                mangohud_value = "MANGOHUD=1" if game.mangohud else ""
                gamemode_value = "gamemoderun" if game.gamemode else ""
                # Construct line with game information
                line = (f"{game.title};{game.path};{game.prefix};{game.launch_arguments};{game.game_arguments};"
                        f"{mangohud_value};{gamemode_value}\n")
                file.write(line)

    def show_warning_message(self, message):
        # Show a warning message dialog
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.OK, text=message, )
        dialog.run()
        dialog.destroy()

    def on_checkbox_toggled(self, widget):
        # Handle checkbox toggling event
        checkbox_state = widget.get_active()
        self.save_config(checkbox_state)

    def load_config(self):
        # Load configuration from file
        config_file = os.path.join(self.working_directory, 'config.ini')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return f.read().strip() == 'close-onlaunch=true'
        else:
            # Save default configuration if file does not exist
            self.save_config(False)
            return False

    def save_config(self, checkbox_state):
        # Save configuration to file
        value = 'close-onlaunch=true' if checkbox_state else 'close-onlaunch=false'
        config_file = os.path.join(self.working_directory, 'config.ini')
        with open(config_file, 'w') as f:
            f.write(value)

    def on_button_release_event(self, listbox, event):
        # Handle button release event
        if event.type == Gdk.EventType.BUTTON_RELEASE and event.button == Gdk.BUTTON_PRIMARY:
            current_row = listbox.get_row_at_y(event.y)
            current_time = event.time
            if current_row == self.last_clicked_row and current_time - self.last_click_time < 500:
                # Double-click detected, trigger play button click event
                widget = self.button_play
                self.on_button_play_clicked(widget)
            else:
                # Single-click, update last click details and enable buttons
                self.last_clicked_row = current_row
                self.last_click_time = current_time

                self.button_edit.set_sensitive(True)
                self.button_delete.set_sensitive(True)
                self.button_play.set_sensitive(True)


class Game:
    def __init__(self, title, path, prefix, launch_arguments, game_arguments, mangohud, gamemode):
        # Initialize a Game object with various attributes
        self.title = title  # Title of the game
        self.path = path  # Path to the game executable
        self.launch_arguments = launch_arguments  # Arguments to launch the game
        self.game_arguments = game_arguments  # Arguments specific to the game
        self.mangohud = mangohud  # Boolean indicating whether Mangohud is enabled
        self.gamemode = gamemode  # Boolean indicating whether Gamemode is enabled
        self.prefix = prefix  # Prefix for Wine games


class ConfirmationDialog(Gtk.Dialog):
    def __init__(self, parent):
        # Initialize the ConfirmationDialog
        Gtk.Dialog.__init__(self, title="Remove Game", parent=parent, modal=True)

        # Configure dialog properties
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(300, 100)

        # Create a grid layout for the dialog
        grid = Gtk.Grid()
        grid.set_column_homogeneous(True)
        grid.set_row_homogeneous(True)
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_border_width(10)

        # Add grid to dialog's content area
        self.get_content_area().add(grid)

        # Create a label
        label = Gtk.Label()
        label.set_label("Are you sure?")
        label.set_halign(Gtk.Align.CENTER)
        grid.attach(label, 0, 0, 2, 1)

        # Create "No" button
        button_no = Gtk.Button(label="Cancel")
        button_no.connect("clicked", lambda x: self.response(Gtk.ResponseType.NO))
        grid.attach(button_no, 0, 1, 1, 1)

        # Create "Yes" button
        button_yes = Gtk.Button(label="Confirm")
        button_yes.connect("clicked", lambda x: self.response(Gtk.ResponseType.YES))
        grid.attach(button_yes, 1, 1, 1, 1)

        # Create a checkbox to optionally remove the prefix
        self.checkbox = Gtk.CheckButton(label="Also remove the prefix")
        self.checkbox.set_halign(Gtk.Align.CENTER)
        grid.attach(self.checkbox, 0, 2, 2, 1)

        # Display all widgets
        self.show_all()

    def get_remove_prefix_state(self):
        # Get the state of the checkbox
        return self.checkbox.get_active()


class AddGame(Gtk.Dialog):
    def __init__(self, parent):
        # Initialize the AddGame dialog
        super().__init__(title="Add/Edit Game", parent=parent)
        # self.set_default_size(500, -1)
        self.set_resizable(False)
        self.set_modal(True)

        # Create the content area
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
        grid2.set_margin_bottom(10)

        grid3 = Gtk.Grid()
        grid3.set_row_spacing(10)
        grid3.set_column_spacing(10)
        grid3.set_margin_start(10)
        grid3.set_margin_end(10)
        grid3.set_margin_top(10)
        grid3.set_margin_bottom(10)

        # Widgets for title
        self.label_title = Gtk.Label(label="Title")
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.set_tooltip_text("Game Title")

        # Widgets for path
        self.label_path = Gtk.Label(label="Path")
        self.label_path.set_halign(Gtk.Align.START)
        self.entry_path = Gtk.Entry()
        self.entry_path.set_tooltip_text("/path/to/the/exe")
        self.button_search = Gtk.Button()
        self.button_search.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search.connect("clicked", self.on_button_search_clicked)

        # Widgets for prefix
        self.label_prefix = Gtk.Label(label="Prefix")
        self.label_prefix.set_halign(Gtk.Align.START)
        self.entry_prefix = Gtk.Entry()
        self.entry_prefix.set_tooltip_text("/path/to/the/prefix")

        # Widgets for launch arguments
        self.label_launch_arguments = Gtk.Label(label="Launch Arguments")
        self.label_launch_arguments.set_halign(Gtk.Align.START)
        self.entry_launch_arguments = Gtk.Entry()
        self.entry_launch_arguments.set_tooltip_text("e.g.: PROTON_USE_WINED3D=1 gamescope -W 2560 -H 1440")

        # Widgets for game arguments
        self.label_game_arguments = Gtk.Label(label="Game's Arguments")
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text("e.g.: -d3d11 -fullscreen")

        # Checkboxes for optional features
        self.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
        self.checkbox_gamemode = Gtk.CheckButton(label="GameMode")

        # Button for Winecfg
        self.button_winecfg = Gtk.Button(label="Winecfg")
        self.button_winecfg.set_size_request(120, -1)
        self.button_winecfg.connect("clicked", self.on_button_winecfg_clicked)

        # Button for Winetricks
        self.button_winetricks = Gtk.Button(label="Winetricks")
        self.button_winetricks.set_size_request(120, -1)
        self.button_winetricks.connect("clicked", self.on_button_winetricks_clicked)

        # Button for creating shortcut
        self.checkbox_shortcut = Gtk.CheckButton(label="Create Shortcut")
        self.checkbox_shortcut.connect("toggled", self.on_checkbox_toggled)


        # Button for selection shortcut icon
        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)
        self.button_shortcut_icon.set_tooltip_text("Select an icon for the shortcut")
        self.button_shortcut_icon.set_sensitive(False)  # Initially disable the button

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

        # Add vertical space
        space_label = Gtk.Label()

        # Event handlers
        self.entry_title.connect("changed", self.update_prefix_entry)

        # Attach widgets to the grid layout
        grid.attach(self.label_title, 0, 0, 4, 1)
        grid.attach(self.entry_title, 0, 1, 4, 1)

        grid.attach(self.label_path, 0, 2, 4, 1)
        grid.attach(self.entry_path, 0, 3, 3, 1)
        self.entry_path.set_hexpand(True)
        grid.attach(self.button_search, 3, 3, 1, 1)

        grid.attach(self.label_prefix, 0, 4, 4, 1)
        grid.attach(self.entry_prefix, 0, 5, 4, 1)

        grid.attach(self.label_launch_arguments, 0, 6, 4, 1)
        grid.attach(self.entry_launch_arguments, 0, 7, 4, 1)

        grid.attach(self.label_game_arguments, 0, 8, 4, 1)
        grid.attach(self.entry_game_arguments, 0, 9, 4, 1)

        self.box.add(grid)

        grid2.attach(self.checkbox_mangohud, 0, 0, 1, 1)
        self.checkbox_mangohud.set_hexpand(True)
        grid2.attach(self.checkbox_gamemode, 0, 1, 1, 1)

        grid2.attach(self.button_winecfg, 2, 0, 1, 1)
        grid2.attach(self.button_winetricks, 2, 1, 1, 1)

        grid2.attach(space_label, 0, 2, 1, 1)

        grid2.attach(self.button_shortcut_icon, 2, 3, 1, 1)
        grid2.attach(self.checkbox_shortcut, 0, 3, 1, 1)

        self.box.add(grid2)

        grid3.attach(self.button_cancel, 1, 1, 1, 1)
        grid3.attach(self.button_ok, 2, 1, 1, 1)

        self.box.add(grid3)

        # Check if optional features are available and enable/disable accordingly
        mangohud_enabled = os.path.exists("/usr/bin/mangohud")
        if not mangohud_enabled:
            self.checkbox_mangohud.set_sensitive(False)
            self.checkbox_mangohud.set_active(False)

        self.gamemode_enabled = os.path.exists("/usr/bin/gamemoderun")
        if not self.gamemode_enabled:
            self.checkbox_gamemode.set_sensitive(False)
            self.checkbox_gamemode.set_active(False)

        # self.create_remove_shortcut(self)
        self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())
        self.show_all()

    def on_checkbox_toggled(self, checkbox):
        # Enable or disable the button based on the checkbox state
        self.button_shortcut_icon.set_sensitive(checkbox.get_active())

    def set_image_shortcut_icon(self):

        image_path = "/usr/share/icons/faugus-launcher.png"

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
        scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_file(image_path)
        image.set_from_pixbuf(scaled_pixbuf)

        return image

    def on_button_shortcut_icon_clicked(self, widget):

        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields()
        if not validation_result:
            return

        title = self.entry_title.get_text()
        path = self.entry_path.get_text()

        # Handle the click event of the Create Shortcut button
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        # Check if the icon file exists
        icons_path = os.path.expanduser(f"~/.config/faugus-launcher/icons/")

        # Check if the icon directory exists and create if it doesn't
        icon_directory = os.path.expanduser(f"~/.config/faugus-launcher/icons/{title_formatted}/")
        if not os.path.exists(icon_directory):
            os.makedirs(icon_directory)

        # Execute 7z command to extract icon
        os.system(f'7z e "{path}" -o{icon_directory} -r -aoa')

        # Open file dialog to select .ico file
        dialog = Gtk.FileChooserDialog(title="Select an icon for the shortcut", action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        # Add a filter to limit selection to .ico files
        filter_ico = Gtk.FileFilter()
        filter_ico.set_name("Image files")
        filter_ico.add_mime_type("image/*")  # Other image formats
        dialog.add_filter(filter_ico)

        # Set the initial directory to the icon directory
        dialog.set_current_folder(icon_directory)

        # Connect signal to update preview widget when file selection changes
        dialog.connect("update-preview", self.update_preview)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            file_path = dialog.get_filename()
            # Move and rename the icon file
            shutil.move(file_path, os.path.expanduser(f"{icons_path}{title_formatted}.ico"))

            image_path = f"{icons_path}{title_formatted}.ico"

            pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
            scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

            image = Gtk.Image.new_from_file(image_path)
            image.set_from_pixbuf(scaled_pixbuf)

            self.button_shortcut_icon.set_image(image)

            # Delete the folder after the icon is moved
            shutil.rmtree(icon_directory)
            dialog.destroy()

        else:
            # Delete the folder
            shutil.rmtree(icon_directory)
            dialog.destroy()
            return

    def update_preview(self, dialog):
        # Updates the preview widget with the selected image's thumbnail
        file_path = dialog.get_preview_filename()
        if file_path:
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
        desktop_file_path = os.path.expanduser(f"~/.local/share/applications/{title_formatted}.desktop")

        # Check if the shortcut file exists
        shortcut_exists = os.path.exists(desktop_file_path)

        # Mark the checkbox if the shortcut exists
        self.checkbox_shortcut.set_active(shortcut_exists)

    def update_prefix_entry(self, widget):
        # Update the prefix entry based on the title
        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', self.entry_title.get_text())
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())
        prefix = os.path.expanduser("~/.config/faugus-launcher/prefixes/") + title_formatted
        self.entry_prefix.set_text(prefix)

    def load_checkboxes_state(self, mangohud, gamemode):
        # Set the state of the MangoHud and Feral Game Mode checkboxes
        self.checkbox_mangohud.set_active(mangohud)
        self.checkbox_gamemode.set_active(gamemode)

    def on_button_winecfg_clicked(self, widget):
        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields()
        if not validation_result:
            return

        title = self.entry_title.get_text()
        prefix = self.entry_prefix.get_text()

        title_formatted = re.sub(r'[^a-zA-Z0-9\s]', '', title)
        title_formatted = title_formatted.replace(' ', '-')
        title_formatted = '-'.join(title_formatted.lower().split())

        # Open Winetricks for the specified Wine prefix
        winecfg_command = (f'WINEPREFIX={prefix} '
                           f'GAMEID={title_formatted} '
                           f'"/usr/bin/umu-run" "winecfg"')
        subprocess.Popen(["/bin/bash", "-c", winecfg_command])
        print(winecfg_command)

    def on_button_winetricks_clicked(self, widget):
        # Handle the click event of the Winetricks button
        validation_result = self.validate_fields()
        if not validation_result:
            return

        prefix = self.entry_prefix.get_text()

        # Open Winetricks for the specified Wine prefix
        winetricks_command = (f'WINEPREFIX={prefix} '
                              f'GAMEID=winetricks-gui '
                              f'STORE="none" '
                              f'"/usr/bin/umu-run" ""')
        subprocess.Popen(["/bin/bash", "-c", winetricks_command])
        print(winetricks_command)

    def on_button_search_clicked(self, widget):
        # Handle the click event of the search button to select the game's .exe
        dialog = Gtk.FileChooserDialog(title="Select the game's .exe", parent=self, action=Gtk.FileChooserAction.OPEN)
        dialog.set_current_folder(os.path.expanduser("~/"))
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.entry_path.set_text(dialog.get_filename())

        dialog.destroy()

    def validate_fields(self):
        # Validate the input fields for title and path
        title = self.entry_title.get_text()
        path = self.entry_path.get_text()

        if not title or not path:
            # Show a warning message if title or path is empty
            self.show_warning_message("Title and Path need to be filled")
            return False

        return True

    def show_warning_message(self, message):
        # Display a warning message dialog
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.WARNING,
                                   buttons=Gtk.ButtonsType.OK, text=message)
        dialog.run()
        dialog.destroy()


if __name__ == "__main__":
    app = Main()
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()
