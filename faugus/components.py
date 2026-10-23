#!/usr/bin/python3

import os
import requests
import tarfile
import shutil

from faugus.proton_downloader import ProgressPrinter
from faugus.path_manager import FAUGUS_LAUNCHER_SHARE_DIR, DOWNLOAD_DIR, UMU_RUN

UMU_URL_TEMPLATE = "https://github.com/Faugus/umu-launcher/releases/download/{}/umu-run"
UMU_VERSION_API = "https://api.github.com/repos/Faugus/umu-launcher/releases"
UMU_VERSION_FILE = os.path.join(FAUGUS_LAUNCHER_SHARE_DIR, "version.txt")


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


def download_file(url, path, timeout):
    response = requests.get(url, stream=True, timeout=timeout)
    if response.status_code != 200:
        return False

    total = int(response.headers.get("Content-Length", 0))
    progress = ProgressPrinter()
    downloaded = 0

    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                progress(downloaded / total)
    return True


def download_umu_run(version):
    try:
        os.makedirs(FAUGUS_LAUNCHER_SHARE_DIR, exist_ok=True)
        url = UMU_URL_TEMPLATE.format(version)

        print("Updating UMU-Launcher...", version, flush=True)
        if not download_file(url, UMU_RUN, 10):
            return

        os.chmod(UMU_RUN, 0o755)

        with open(UMU_VERSION_FILE, "w") as f:
            f.write(version)
    except Exception:
        return


def update_umu():
    latest = get_latest_umu_version()
    current = get_installed_umu_version()

    if latest is None:
        return

    if latest != current or not os.path.exists(UMU_RUN):
        download_umu_run(latest)
    else:
        print("UMU-Launcher is up to date.", flush=True)


BE_URL = "https://github.com/Faugus/components/releases/download/{}/be.tar.gz"
EAC_URL = "https://github.com/Faugus/components/releases/download/{}/eac.tar.gz"
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

        if not download_file(url, download_path, 15):
            return

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
