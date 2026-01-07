#!/usr/bin/python3

import os
import requests
import tarfile
import shutil


UMU_URL_TEMPLATE = "https://github.com/Faugus/umu-launcher/releases/download/{}/umu-run"
UMU_VERSION_API = "https://api.github.com/repos/Faugus/umu-launcher/releases"
xdg_data_home = os.getenv("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
UMU_INSTALL_DIR = os.path.join(xdg_data_home, "faugus-launcher")
UMU_VERSION_FILE = os.path.join(UMU_INSTALL_DIR, "version.txt")
UMU_BIN_PATH = os.path.join(UMU_INSTALL_DIR, "umu-run")

def get_latest_umu_version():
    try:
        r = requests.get(UMU_VERSION_API, timeout=5)
        if r.status_code == 200:
            releases = r.json()
            if releases:
                return releases[0]["tag_name"]
    except Exception:
        return None

def get_installed_umu_version():
    if os.path.exists(UMU_VERSION_FILE):
        with open(UMU_VERSION_FILE) as f:
            return f.read().strip()
    return None

def download_umu_run(version):
    try:
        os.makedirs(UMU_INSTALL_DIR, exist_ok=True)
        url = UMU_URL_TEMPLATE.format(version)
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            return

        with open(UMU_BIN_PATH, "wb") as f:
            f.write(r.content)

        os.chmod(UMU_BIN_PATH, 0o755)

        with open(UMU_VERSION_FILE, "w") as f:
            f.write(version)

        print("Updating UMU-Launcher...", version, flush=True)
    except Exception:
        return

def update_umu():
    latest = get_latest_umu_version()
    current = get_installed_umu_version()

    if latest is None:
        return

    if latest != current or not os.path.exists(UMU_BIN_PATH):
        download_umu_run(latest)
    else:
        print("UMU-Launcher is up to date.", flush=True)


config_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))

BE_URL = "https://github.com/Faugus/components/releases/download/{}/be.tar.gz"
EAC_URL = "https://github.com/Faugus/components/releases/download/{}/eac.tar.gz"
DOWNLOAD_DIR = f"{config_dir}/faugus-launcher/components"
REPO_URL = "https://api.github.com/repos/Faugus/components/releases/latest"
VERSION_FILE = f"{DOWNLOAD_DIR}/version.txt"

def get_latest_version():
    try:
        response = requests.get(REPO_URL, timeout=5)
        if response.status_code == 200:
            release_info = response.json()
            return release_info['tag_name']
    except Exception:
        return None

def get_installed_version():
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    return None

def download_and_extract(url, download_dir):
    try:
        file_name = url.split('/')[-1]
        download_path = os.path.join(download_dir, file_name)

        response = requests.get(url, stream=True, timeout=15)
        if response.status_code != 200:
            return

        with open(download_path, "wb") as f:
            f.write(response.content)

        with tarfile.open(download_path, "r:gz") as tar:
            tar.extractall(path=download_dir, filter=lambda tarinfo, path: tarinfo)

        os.remove(download_path)
    except Exception:
        return

def check_for_updates():
    latest_version = get_latest_version()
    installed_version = get_installed_version()

    if latest_version:
        if latest_version != installed_version:
            be_url = BE_URL.format(latest_version)
            eac_url = EAC_URL.format(latest_version)

            if os.path.exists(DOWNLOAD_DIR):
                shutil.rmtree(DOWNLOAD_DIR)
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            print("Updating BattlEye...", flush=True)
            download_and_extract(be_url, DOWNLOAD_DIR)
            print("Updating Easy Anti-Cheat...", flush=True)
            download_and_extract(eac_url, DOWNLOAD_DIR)

            with open(VERSION_FILE, "w") as f:
                f.write(latest_version)
        else:
            print("Components are up to date.", flush=True)


def main():
    update_umu()
    check_for_updates()

if __name__ == "__main__":
    main()
