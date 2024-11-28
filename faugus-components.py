#!/usr/bin/python3

import os
import requests
import tarfile
import shutil

config_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))

# URLs for .tar.gz files
BE_URL = "https://github.com/Faugus/components/releases/download/{}/be.tar.gz"
EAC_URL = "https://github.com/Faugus/components/releases/download/{}/eac.tar.gz"
DOWNLOAD_DIR = f"{config_dir}/faugus-launcher/components"
REPO_URL = "https://api.github.com/repos/Faugus/components/releases/latest"
VERSION_FILE = f"{DOWNLOAD_DIR}/version.txt"

# Function to get the latest version from GitHub releases
def get_latest_version():
    response = requests.get(REPO_URL)
    if response.status_code == 200:
        release_info = response.json()
        return release_info['tag_name']  # Returns the latest tag name
    else:
        print(f"Failed to access {REPO_URL}. Status code: {response.status_code}", flush=True)
        return None

# Function to get the installed version from a local file
def get_installed_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

# Function to download and extract the tar.gz file
def download_and_extract(url, download_dir):
    file_name = url.split('/')[-1]
    download_path = os.path.join(download_dir, file_name)

    # Download the file
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(download_path, "wb") as f:
            f.write(response.content)

        # Extract the file with a filter to avoid deprecation warning
        with tarfile.open(download_path, "r:gz") as tar:
            # The filter function now accepts two arguments: tarinfo and path
            tar.extractall(path=download_dir, filter=lambda tarinfo, path: tarinfo)

        # Remove the .tar.gz file after extraction
        os.remove(download_path)
        print("Done!", flush=True)
    else:
        print(f"Failed to download {file_name}. Status code: {response.status_code}", flush=True)

# Function to check for updates
def check_for_updates():
    # Get the latest version from GitHub
    latest_version = get_latest_version()
    installed_version = get_installed_version()

    if latest_version:

        # Compare the latest version with the installed version
        if latest_version != installed_version:

            # URLs for the files with the latest version
            be_url = BE_URL.format(latest_version)
            eac_url = EAC_URL.format(latest_version)

            # Remove old directories if they exist
            if os.path.exists(DOWNLOAD_DIR):
                shutil.rmtree(DOWNLOAD_DIR)  # Remove old files
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            # Download and extract the files
            print("Updating BattlEye...", flush=True)
            download_and_extract(be_url, DOWNLOAD_DIR)
            print("Updating Easy Anti-Cheat...", flush=True)
            download_and_extract(eac_url, DOWNLOAD_DIR)

            # Update the version file with the latest version
            with open(VERSION_FILE, "w") as f:
                f.write(latest_version)
        else:
            print("Components are up to date.", flush=True)

# Execute the update check
check_for_updates()
