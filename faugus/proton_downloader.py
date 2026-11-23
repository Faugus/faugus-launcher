

import json
import platform
import tarfile
import urllib.error
import urllib.request
import shutil
import argparse

from faugus.path_manager import COMPATIBILITY_DIR
from faugus.core import github_api_headers

CONFIGS = {
    "ge": {
        "label": "GE-Proton",
        "dir": "Proton-GE Latest",
        "api": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest",
        "archive_ext": ".tar.gz",
    },
    "cachyos": {
        "label": "Proton-CachyOS",
        "dir": "Proton-CachyOS Latest",
        "api": "https://api.github.com/repos/CachyOS/proton-cachyos/releases/latest",
        "archive_ext": "x86_64.tar.xz",
    },
    "dw": {
        "label": "DW-Proton",
        "dir": "DW-Proton Latest",
        "api": "https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases/latest",
        "archive_ext": "x86_64.tar.xz",
    },
    "wineland": {
        "label": "Proton-Wineland",
        "dir": "Proton-Wineland Latest",
        "api": "https://api.github.com/repos/nanomatters/proton-cachyos/releases/latest",
        "archive_ext": "x86_64.tar.xz",
    },
}

FOREIGN_ARCH_TOKENS = {
    "x86_64": ("aarch64", "arm64"),
    "aarch64": ("x86_64", "amd64"),
    "arm64": ("x86_64", "amd64"),
}


def select_asset(assets, archive_exts):
    foreign_tokens = FOREIGN_ARCH_TOKENS.get(platform.machine(), ())

    return next(
        (
            a for a in assets
            if a["name"].endswith(archive_exts)
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


USER_AGENT = "faugus-launcher"


class ProgressPrinter:
    def __init__(self):
        self.last_percent = -1

    def __call__(self, fraction):
        percent = int(fraction * 100)
        if percent != self.last_percent:
            self.last_percent = percent
            print(f"PROGRESS {fraction:.2f}", flush=True)


class StreamProgress:
    def __init__(self, raw, total_size, progress_callback):
        self.raw = raw
        self.total_size = total_size
        self.progress_callback = progress_callback
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = self.raw.read(size)
        self.bytes_read += len(chunk)
        if self.total_size > 0:
            self.progress_callback(self.bytes_read / self.total_size)
        return chunk

    def close(self):
        self.raw.close()


class ReleaseApiError(Exception):
    def __init__(self, message, rate_limited=False, reset_time=None):
        super().__init__(message)
        self.rate_limited = rate_limited
        # Unix time at which an exhausted GitHub rate limit resets, if known.
        self.reset_time = reset_time


def raise_for_api_status(status, headers):
    if status == 200:
        return
    if status in (403, 429) and headers.get("X-RateLimit-Remaining") == "0":
        reset = headers.get("X-RateLimit-Reset", "")
        raise ReleaseApiError(
            "API rate limit exceeded",
            rate_limited=True,
            reset_time=int(reset) if reset.isdigit() else None,
        )
    raise ReleaseApiError(f"HTTP {status}")


def get_latest_tag_and_url(api, archive_ext):
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT, **github_api_headers(api)})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise_for_api_status(e.code, e.headers)
        raise
    except (OSError, ValueError) as e:
        raise ReleaseApiError(str(e)) from e

    asset = select_asset(data.get("assets", []), archive_ext)
    if not asset:
        raise ReleaseApiError("the latest release has no matching archive")

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
         .replace("cachyos-wineland-", "")
         .replace("wineland-", "")
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


def install_proton_latest(proton_dir, url, asset_name, label, progress=None):
    tmp = COMPATIBILITY_DIR / "__proton_tmp__"

    try:
        print(f"Downloading & extracting {label}...", flush=True)
        tmp.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        response = urllib.request.urlopen(req, timeout=30)
        if progress:
            response = StreamProgress(response, int(response.headers.get("Content-Length", 0)), progress)

        with tarfile.open(fileobj=response, mode=get_tar_mode(asset_name)) as tar:
            tar.extractall(tmp, filter="tar")
    except Exception as e:
        print(f"Error downloading/extracting {label}: {e}", flush=True)
        if tmp.exists():
            shutil.rmtree(tmp)
        raise

    extracted = next(tmp.iterdir())

    if proton_dir.exists():
        shutil.rmtree(proton_dir)

    extracted.rename(proton_dir)
    shutil.rmtree(tmp)


def ensure_latest(kind, progress=None):
    cfg = CONFIGS[kind]

    proton_dir = COMPATIBILITY_DIR / cfg["dir"]
    proton_dir.parent.mkdir(parents=True, exist_ok=True)

    try:
        latest_tag, url, asset_name = get_latest_tag_and_url(cfg["api"], cfg["archive_ext"])
    except ReleaseApiError:
        print(f"Could not determine the latest {cfg['label']} release.", flush=True)
        raise

    installed = get_installed_version(proton_dir)

    if installed and normalize_version(installed) == normalize_version(latest_tag):
        print(f"{cfg['label']} is up to date.", flush=True)
        return

    install_proton_latest(proton_dir, url, asset_name, cfg["label"], progress)
    rewrite_compatibilitytool_vdf(proton_dir, cfg["dir"])


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    for kind in CONFIGS:
        group.add_argument(f"--{kind}", action="store_true")
    args = parser.parse_args()

    for key in vars(args):
        if getattr(args, key):
            try:
                ensure_latest(key, ProgressPrinter())
            except Exception:
                # ensure_latest has already printed the error for the runner's log.
                pass


if __name__ == "__main__":
    main()
