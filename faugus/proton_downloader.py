#!/usr/bin/env python3

import json
import tarfile
import urllib.request
import shutil
import argparse
from pathlib import Path


STEAM_COMPAT_DIR = Path.home() / ".local/share/Steam/compatibilitytools.d"

CONFIGS = {
    "ge": {
        "label": "GE-Proton",
        "dir": "Proton-GE Latest",
        "api": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest",
        "archive_ext": ".tar.gz",
    },
    "em": {
        "label": "Proton-EM",
        "dir": "Proton-EM Latest",
        "api": "https://api.github.com/repos/Etaash-mathamsetty/Proton/releases/latest",
        "archive_ext": ".tar.xz",
    },
}


def get_latest_tag_and_url(api, archive_ext):
    try:
        with urllib.request.urlopen(api, timeout=5) as r:
            data = json.loads(r.read())
    except Exception:
        return None, None

    asset = next(
        (a for a in data.get("assets", []) if a["name"].endswith(archive_ext)),
        None,
    )

    if not asset:
        return None, None

    return data["tag_name"], asset["browser_download_url"]


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


def install_proton_latest(proton_dir, url, label):
    archive = STEAM_COMPAT_DIR / url.split("/")[-1]
    tmp = STEAM_COMPAT_DIR / "__proton_tmp__"

    try:
        print(f"Downloading {label}...", flush=True)
        urllib.request.urlretrieve(url, archive)
    except Exception:
        return

    print(f"Extracting {label}...", flush=True)
    tmp.mkdir(exist_ok=True)

    with tarfile.open(archive) as tar:
        tar.extractall(tmp, filter="data")

    archive.unlink()

    extracted = next(tmp.iterdir())

    if proton_dir.exists():
        shutil.rmtree(proton_dir)

    extracted.rename(proton_dir)
    shutil.rmtree(tmp)


def ensure_latest(kind):
    cfg = CONFIGS[kind]

    proton_dir = STEAM_COMPAT_DIR / cfg["dir"]
    proton_dir.parent.mkdir(parents=True, exist_ok=True)

    latest_tag, url = get_latest_tag_and_url(cfg["api"], cfg["archive_ext"])
    if not url:
        return

    installed = get_installed_version(proton_dir)

    if installed and normalize_version(installed) == normalize_version(latest_tag):
        print(f"{cfg['label']} is up to date.", flush=True)
        return

    install_proton_latest(proton_dir, url, cfg["label"])
    rewrite_compatibilitytool_vdf(proton_dir, cfg["dir"])


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ge", action="store_true")
    group.add_argument("--em", action="store_true")
    args = parser.parse_args()

    if args.ge:
        ensure_latest("ge")
    if args.em:
        ensure_latest("em")


if __name__ == "__main__":
    main()
