#!/usr/bin/python3

import os
import requests
import tarfile
import re
from pathlib import Path
import threading

STEAM_COMPAT_DIR = Path.home() / ".local/share/Steam/compatibilitytools.d"
GITHUB_API_URL = "https://api.github.com/repos/Etaash-mathamsetty/Proton/releases/latest"
DOWNLOAD_BASE_URL = "https://github.com/Etaash-mathamsetty/Proton/releases/download"

def get_latest_release_tag():
    response = requests.get(GITHUB_API_URL)
    if response.status_code == 200:
        return response.json()["tag_name"]
    else:
        print("Failed to access GitHub API:", response.status_code, flush=True)
        return None

def get_installed_proton_versions():
    if not STEAM_COMPAT_DIR.exists():
        return []
    return sorted([
        entry.name.replace("proton-", "")
        for entry in STEAM_COMPAT_DIR.iterdir()
        if entry.is_dir() and re.match(r"proton-EM-\d+\.\d+-\d+", entry.name)
    ])

def download_and_extract(version_tag):
    tar_name = f"proton-{version_tag}.tar.xz"
    url = f"{DOWNLOAD_BASE_URL}/{version_tag}/{tar_name}"
    tar_path = STEAM_COMPAT_DIR / tar_name

    print(f"Downloading {tar_name}...", flush=True)
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(tar_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
    else:
        print("Failed to download:", response.status_code)
        return

    print("Extracting archive...", flush=True)
    with tarfile.open(tar_path, "r:xz") as tar:
        tar.extractall(path=STEAM_COMPAT_DIR)

    os.remove(tar_path)
    print("Proton installed successfully.", flush=True)

def main():
    latest_version = get_latest_release_tag()
    if not latest_version:
        return

    installed_versions = get_installed_proton_versions()
    print("Latest available version:", latest_version, flush=True)
    print("Installed versions:", ", ".join(installed_versions) or "none", flush=True)

    if latest_version not in installed_versions:
        thread = threading.Thread(target=download_and_extract, args=(latest_version,))
        thread.start()
        thread.join()
    else:
        print("The latest version is already installed.", flush=True)

if __name__ == "__main__":
    main()
