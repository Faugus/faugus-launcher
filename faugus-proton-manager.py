#!/usr/bin/env python3

import requests
import gi
import os
import tarfile
import shutil

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

GITHUB_API_URL = "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases"
STEAM_COMPATIBILITY_PATH = os.path.expanduser("~/.local/share/Steam/compatibilitytools.d")

class ProtonDownloader(Gtk.Window):
    def __init__(self):
        super().__init__(title="Faugus GE-Proton Manager")
        self.set_resizable(False)
        self.set_modal(True)

        self.set_border_width(10)
        self.set_default_size(400, 395)

        vbox = Gtk.VBox(spacing=5)
        self.add(vbox)

        # Scrolled window to hold the Grid
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_vexpand(True)
        vbox.pack_start(self.scrolled_window, True, True, 0)

        # Grid for releases
        self.grid = Gtk.Grid()
        self.scrolled_window.add(self.grid)

        # Set row and column spacing
        self.grid.set_row_spacing(5)
        self.grid.set_column_spacing(10)

        # Fetch and populate releases in the Grid
        self.releases = []
        self.get_releases()

    def filter_releases(self):
        # Filter releases up to "GE-Proton7-1"
        filtered_releases = []
        for release in self.releases:
            filtered_releases.append(release)
            if release["tag_name"] == "GE-Proton7-1":
                break
        return filtered_releases

    def get_releases(self):
        # Fetch all releases using pagination
        page = 1
        headers = {"Authorization": "token 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"}  # Your token here
        while True:
            response = requests.get(GITHUB_API_URL, headers=headers, params={"page": page, "per_page": 100})
            if response.status_code == 200:
                releases = response.json()
                if not releases:
                    break
                self.releases.extend(releases)
                page += 1
            else:
                print("Error fetching releases:", response.status_code)
                break

        # Filter the releases
        self.releases = self.filter_releases()

        # Add filtered releases to the Grid in the correct order
        for release in self.releases:
            self.add_release_to_grid(release)

    def add_release_to_grid(self, release):
        row_index = len(self.grid.get_children()) // 2  # Calculate row index based on number of rows

        label = Gtk.Label(label=release["tag_name"], xalign=0)
        label.set_halign(Gtk.Align.START)  # Align label to the start
        label.set_hexpand(True)  # Allow label to expand
        self.grid.attach(label, 0, row_index, 1, 1)  # Column 0 for the label

        # Check if the release is already installed
        version_path = os.path.join(STEAM_COMPATIBILITY_PATH, release["tag_name"])
        button = Gtk.Button(label="Remove" if os.path.exists(version_path) else "Download")
        button.connect("clicked", self.on_button_clicked, release)
        button.set_size_request(120, -1)  # Set a fixed width for the button

        self.grid.attach(button, 1, row_index, 1, 1)  # Column 1 for the button

    def on_button_clicked(self, widget, release):
        version_path = os.path.join(STEAM_COMPATIBILITY_PATH, release["tag_name"])

        if os.path.exists(version_path):
            # Remove the release
            self.on_remove_clicked(widget, release)
        else:
            # Download the release
            self.on_download_clicked(widget, release)

    def on_download_clicked(self, widget, release):
        # Find the first tar.gz asset to download
        for asset in release["assets"]:
            if asset["name"].endswith(".tar.gz"):
                download_url = asset["browser_download_url"]
                self.download_and_extract(download_url, asset["name"], release["tag_name"], widget)
                break

    def download_and_extract(self, url, filename, tag_name, button):
        button.set_label("Downloading...")
        button.set_sensitive(False)  # Disable the button during download

        # Ensure the directory exists
        if not os.path.exists(STEAM_COMPATIBILITY_PATH):
            os.makedirs(STEAM_COMPATIBILITY_PATH)
            print(f"Created directory: {STEAM_COMPATIBILITY_PATH}")

        # Download the tar.gz file
        print(f"Downloading {filename}...")
        response = requests.get(url, stream=True)
        tar_file_path = os.path.join(os.getcwd(), filename)  # Save in the current working directory
        with open(tar_file_path, "wb") as file:
            for data in response.iter_content(1024):
                file.write(data)
                # Update the interface to show "Downloading..."
                Gtk.main_iteration_do(False)

        print(f"Downloaded {filename}")

        # Call the function to extract the file
        self.extract_tar_and_update_button(tar_file_path, tag_name, button)

    def extract_tar_and_update_button(self, tar_file_path, tag_name, button):
        button.set_label("Extracting...")
        Gtk.main_iteration_do(False)

        # Now we extract directly to the STEAM_COMPATIBILITY_PATH
        self.extract_tar(tar_file_path, STEAM_COMPATIBILITY_PATH)

        # Remove the tar.gz after extraction
        os.remove(tar_file_path)
        print(f"Removed {tar_file_path}")

        # Update the button to "Remove"
        self.update_button(button, "Remove")
        button.set_sensitive(True)

    def extract_tar(self, tar_file_path, extract_to):
        print(f"Extracting {tar_file_path} to {extract_to}...")
        try:
            with tarfile.open(tar_file_path, "r:gz") as tar:
                members = tar.getmembers()  # Get the members for extraction
                for member in members:
                    tar.extract(member, path=extract_to)
                    # Update the interface to ensure the button text is displayed
                    Gtk.main_iteration_do(False)
            print("Extraction completed successfully.")
        except Exception as e:
            print(f"Failed to extract {tar_file_path}: {e}")

    def on_remove_clicked(self, widget, release):
        version_path = os.path.join(STEAM_COMPATIBILITY_PATH, release["tag_name"])
        if os.path.exists(version_path):
            try:
                shutil.rmtree(version_path)
                print(f"Removed {version_path}")
                # Update button to "Download"
                self.update_button(widget, "Download")
            except Exception as e:
                print(f"Failed to remove {version_path}: {e}")

    def update_button(self, button, new_label):
        button.set_label(new_label)  # Update the button label

# Initialize GTK application
win = ProtonDownloader()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
