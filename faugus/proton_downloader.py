#!/usr/bin/env python3

import json
import platform
import tarfile
import urllib.request
import shutil
import argparse

from faugus.path_manager import PathManager, compatibility_dir

CONFIGS = {
    "cachyos": {
        "name": "Proton-CachyOS",
        "tab_label": "Proton-CachyOS",
        "latest_dir": "Proton-CachyOS Latest",
        "api": "https://api.github.com/repos/CachyOS/proton-cachyos/releases/latest",
        "api_url": "https://api.github.com/repos/CachyOS/proton-cachyos/releases",
        "tag_prefix": "cachyos-",
        "archive_ext": ["x86_64.tar.xz"],
        "tag_to_display": lambda tag: f"Proton-CachyOS-{tag.removeprefix('cachyos-')}",
    },
    "ge": {
        "name": "GE-Proton",
        "tab_label": "GE-Proton",
        "latest_dir": "Proton-GE Latest",
        "api": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest",
        "api_url": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases",
        "tag_prefix": "GE-Proton",
        "archive_ext": [".tar.gz", ".tar.xz"],
        "tag_to_display": lambda tag: tag,
        "min_version": (9, 1),
    },
    "em": {
        "name": "Proton-EM",
        "tab_label": "Proton-EM",
        "latest_dir": "Proton-EM Latest",
        "api": "https://api.github.com/repos/Etaash-mathamsetty/Proton/releases/latest",
        "api_url": "https://api.github.com/repos/Etaash-mathamsetty/Proton/releases",
        "tag_prefix": "EM-",
        "archive_ext": [".tar.xz"],
        "tag_to_display": lambda tag: f"proton-{tag}",
    },
    "dw": {
        "name": "DW-Proton",
        "tab_label": "DW-Proton",
        "latest_dir": "DW-Proton Latest",
        "api": "https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases/latest",
        "api_url": "https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases",
        "tag_prefix": "dwproton-",
        "archive_ext": ["x86_64.tar.xz"],
        "tag_to_display": lambda tag: f"DW-Proton-{tag.removeprefix('dwproton-')}",
    },
}

FOREIGN_ARCH_TOKENS = {
    "x86_64": ("aarch64", "arm64"),
    "aarch64": ("x86_64", "amd64"),
    "arm64": ("x86_64", "amd64"),
}

def select_asset(assets, archive_exts):
    foreign_tokens = FOREIGN_ARCH_TOKENS.get(platform.machine(), ())
    if isinstance(archive_exts, str):
        archive_exts = [archive_exts]

    return next(
        (
            a for a in assets
            if any(a["name"].endswith(ext) for ext in archive_exts)
            and not any(token in a["name"] for token in foreign_tokens)
        ),
        None,
    )


def get_tar_mode(name):
    if name.endswith(('.tar.gz', '.tgz')):
        return 'r|gz'
    if name.endswith(('.tar.xz', '.txz')):
        return 'r|xz'
    if name.endswith(('.tar.bz2', '.tbz2')):
        return 'r|bz2'
    return 'r|'


def get_latest_tag_and_url(api, archive_ext):
    try:
        with urllib.request.urlopen(api, timeout=5) as r:
            data = json.loads(r.read())
    except Exception:
        return None, None, None

    asset = select_asset(data.get("assets", []), archive_ext)
    if not asset:
        return None, None, None

    return data["tag_name"], asset["browser_download_url"], asset["name"]

def get_installed_version(proton_dir):
    version_file = proton_dir / "version"
    if not version_file.exists():
        return None

    parts = version_file.read_text().strip().split(maxsplit=1)
    if len(parts) != 2:
        return None

    return parts[1]

def normalize_version(v):
    if not v:
        return None

    return (
        v.lstrip("v")
         .replace("GE-Proton", "")
         .replace("Proton-EM-", "")
         .replace("EM-", "")
         .replace("cachyos-", "")
         .replace("dwproton-", "")
         .replace("DW-Proton-", "")
         .rstrip("+")
         .strip("-")
    )

def rewrite_compatibilitytool_vdf(proton_dir, display_name):
    (proton_dir / "compatibilitytool.vdf").write_text(
        f'''"compatibilitytools"
{{
  "compat_tools"
  {{
    "{display_name}"
    {{
      "install_path" "."
      "display_name" "{display_name}"
      "from_oslist"  "windows"
      "to_oslist"    "linux"
    }}
  }}
}}
'''
    )

def install_proton_latest(proton_dir, url, asset_name, label):
    tmp = compatibility_dir / "__proton_tmp__"

    try:
        print(f"Downloading & extracting {label}...", flush=True)
        tmp.mkdir(parents=True, exist_ok=True)
        response = urllib.request.urlopen(url, timeout=30)

        with tarfile.open(fileobj=response, mode=get_tar_mode(asset_name)) as tar:
            tar.extractall(tmp, filter="data")
    except Exception:
        if tmp.exists():
            shutil.rmtree(tmp)
        return

    extracted = next(tmp.iterdir())

    if proton_dir.exists():
        shutil.rmtree(proton_dir)

    extracted.rename(proton_dir)
    shutil.rmtree(tmp)

def ensure_latest(kind):
    cfg = CONFIGS[kind]

    proton_dir = compatibility_dir / cfg["latest_dir"]
    proton_dir.parent.mkdir(parents=True, exist_ok=True)

    latest_tag, url, asset_name = get_latest_tag_and_url(cfg["api"], cfg["archive_ext"])
    if not url:
        return

    installed = get_installed_version(proton_dir)

    if installed and normalize_version(installed) == normalize_version(latest_tag):
        print(f"{cfg['name']} is up to date.", flush=True)
        return

    install_proton_latest(proton_dir, url, asset_name, cfg["name"])
    rewrite_compatibilitytool_vdf(proton_dir, cfg["latest_dir"])

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ge", action="store_true")
    group.add_argument("--em", action="store_true")
    group.add_argument("--cachyos", action="store_true")
    group.add_argument("--dw", action="store_true")
    args = parser.parse_args()

    for key in vars(args):
        if getattr(args, key):
            ensure_latest(key)

if __name__ == "__main__":
    main()
