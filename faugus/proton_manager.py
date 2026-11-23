

import os
import re
import requests
import gi
import tarfile
import shutil
import threading
import time
import warnings

from faugus.proton_downloader import (
    CONFIGS, StreamProgress, select_asset, get_tar_mode, ensure_latest,
    ReleaseApiError, raise_for_api_status,
)

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib
from faugus.language_config import *
from faugus.core import github_api_headers
from faugus.utils import play_ui_sound, widget_children, hide_dialog_action_area, run_in_background, idle_add_while_open, IdComboBox, apply_titlebar_preference, get_effective_accent_rgb

GLib.set_prgname("io.github.Faugus.faugus-launcher")

_ = setup_gettext('faugus-launcher')

RELEASES_PER_PAGE = 100

VARIANTS = {
    "cachyos": {
        "tab_label": "Proton-CachyOS",
        "api_url": "https://api.github.com/repos/CachyOS/proton-cachyos/releases",
        "tag_prefix": "cachyos-",
        "archive_ext": ("x86_64.tar.xz",),
        "installed_prefixes": ("proton-cachyos",),
        "tag_to_display": lambda tag: f"Proton-CachyOS-{tag.removeprefix('cachyos-')}",
    },
    "ge": {
        "tab_label": "GE-Proton",
        "api_url": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases",
        "tag_prefix": "GE-Proton",
        "archive_ext": (".tar.gz", ".tar.xz"),
        "installed_prefixes": ("ge-proton",),
        "min_version": (9, 1),
        "tag_to_display": lambda tag: tag,
    },
    "dw": {
        "tab_label": "DW-Proton",
        "api_url": "https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases",
        "tag_prefix": "dwproton-",
        "archive_ext": ("x86_64.tar.xz",),
        "installed_prefixes": ("dwproton", "dw-proton-"),
        "tag_to_display": lambda tag: f"DW-Proton-{tag.removeprefix('dwproton-')}",
    },
    "wineland": {
        "tab_label": "Proton-Wineland",
        "api_url": "https://api.github.com/repos/nanomatters/proton-cachyos/releases",
        "tag_prefix": "",
        "archive_ext": ("x86_64.tar.xz",),
        "installed_prefixes": ("proton-wineland",),
        "tag_to_display": lambda tag: f"Proton-Wineland-{tag.removeprefix('cachyos-wineland-').removeprefix('wineland-')}",
    },
}


class _DownloadCancelled(Exception):
    pass


class ProtonDownloader(Gtk.Dialog):
    def __init__(self):
        super().__init__(title=_("Proton Manager"))
        apply_titlebar_preference(self)
        hide_dialog_action_area(self)
        self.set_resizable(False)
        self.set_modal(True)

        self.closed_event = threading.Event()
        self.fetched_variants = set()
        self.fetching_variants = set()

        self.content_area = self.get_content_area()
        self.content_area.set_halign(Gtk.Align.CENTER)
        self.content_area.set_valign(Gtk.Align.CENTER)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)

        self.view_stack = Gtk.Stack()
        self.view_stack.set_halign(Gtk.Align.FILL)
        self.view_stack.set_valign(Gtk.Align.FILL)
        self.view_stack.set_vhomogeneous(False)
        self.view_stack.set_vexpand(True)
        self.view_stack.set_hexpand(True)

        self.tab_switcher = IdComboBox()
        self.tab_switcher.set_hexpand(True)
        self.tab_switcher.set_margin_top(10)
        self.tab_switcher.set_margin_start(10)
        self.tab_switcher.set_margin_end(10)
        self.tab_switcher.connect("changed", self.on_tab_switcher_changed)

        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        content_scroll.set_size_request(-1, 500)
        content_scroll.set_vexpand(True)
        content_scroll.set_child(self.view_stack)

        box_tabs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box_tabs.append(self.tab_switcher)
        box_tabs.append(content_scroll)

        frame = Gtk.Frame()
        frame.set_margin_top(10)
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_bottom(10)
        frame.set_child(box_tabs)

        self.content_area.append(frame)

        self.grids = {}
        self.status_rows = {}
        for key, variant in VARIANTS.items():
            grid = Gtk.Grid()
            grid.set_hexpand(True)
            grid.set_row_spacing(5)
            grid.set_column_spacing(20)

            page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            page.set_valign(Gtk.Align.START)
            page.set_margin_start(10)
            page.set_margin_end(10)
            page.set_margin_bottom(10)
            page.append(grid)
            page.append(self.build_status_row(key))

            self.view_stack.add_titled(page, key, variant["tab_label"])

            self.tab_switcher.append(key, variant["tab_label"])

            self.grids[key] = grid

        for key in self.grids:
            self.add_latest_row(key)
            for path in self.find_installed(key):
                self.add_installed_row(self.grids[key], path)

        self.tab_switcher.set_active(0)

        self.ensure_releases_fetched(self.tab_switcher.get_active_id())

    def on_tab_switcher_changed(self, combo):
        key = combo.get_active_id()
        self.view_stack.set_visible_child_name(key)
        self.ensure_releases_fetched(key)

    def build_status_row(self, key):
        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)

        label = Gtk.Label()
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)

        retry_button = Gtk.Button(label=_("Retry"))
        retry_button.set_halign(Gtk.Align.CENTER)
        retry_button.connect("clicked", lambda _button: self.fetch_releases(key))

        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        row.set_halign(Gtk.Align.CENTER)
        row.set_margin_top(20)
        row.append(spinner)
        row.append(label)
        row.append(retry_button)
        row.set_visible(False)

        row.spinner = spinner
        row.label = label
        row.retry_button = retry_button
        row.source = None
        self.status_rows[key] = row
        return row

    def show_status(self, key, text, source, loading=False, retry=False, tooltip=None):
        row = self.status_rows[key]
        row.source = source
        row.label.set_label(text)
        row.label.set_tooltip_text(tooltip)
        row.label.set_visible(bool(text))
        row.spinner.set_visible(loading)
        row.spinner.set_spinning(loading)
        row.retry_button.set_visible(retry)
        row.set_visible(True)

    def hide_status(self, key, source):
        row = self.status_rows[key]
        if row.source == source:
            row.spinner.set_spinning(False)
            row.set_visible(False)
            row.source = None

    def show_error(self, key, error, failure, source, retry=False):
        tooltip = None
        if isinstance(error, ReleaseApiError) and error.rate_limited:
            if error.reset_time:
                reset = time.strftime("%H:%M", time.localtime(error.reset_time))
                text = _("GitHub rate limit reached until %s") % reset
            else:
                text = _("GitHub rate limit reached")
            if not os.environ.get("GITHUB_TOKEN", "").strip():
                tooltip = _("Set the GITHUB_TOKEN environment variable to raise the limit")
        elif isinstance(error, (requests.ConnectionError, requests.Timeout)):
            text = _("Could not reach the server")
        else:
            text = failure
            tooltip = str(error)
        self.show_status(key, text, source, retry=retry, tooltip=tooltip)

    def ensure_releases_fetched(self, key):
        if key is None or key in self.fetched_variants or key in self.fetching_variants:
            return
        self.fetch_releases(key)

    def fetch_releases(self, key):
        self.fetching_variants.add(key)
        self.show_status(key, "", "list", loading=True)
        run_in_background(self.fetch_releases_worker, key, self.closed_event)

    def fetch_releases_worker(self, key, closed_event):
        try:
            releases = self.fetch_releases_from_url(VARIANTS[key], closed_event)
        except (ReleaseApiError, requests.RequestException) as e:
            idle_add_while_open(closed_event, self.on_releases_failed, key, e)
        else:
            idle_add_while_open(closed_event, self.on_releases_fetched, key, releases)

    def on_releases_failed(self, key, error):
        self.fetching_variants.discard(key)
        self.show_error(key, error, _("Could not load releases"), "list", retry=True)

    def on_releases_fetched(self, key, releases):
        self.fetching_variants.discard(key)
        self.fetched_variants.add(key)

        grid = self.grids[key]
        variant = VARIANTS[key]

        # Drop the rows shown while loading, keeping the Latest row.
        while len(widget_children(grid)) > 2:
            grid.remove_row(1)

        paths = [self.get_installed_path(release["tag_name"], variant) for release in releases]
        installed = [release for release, path in zip(releases, paths) if path.exists()]
        available = [release for release, path in zip(releases, paths) if not path.exists()]

        for release in installed:
            self.add_release_to_grid(release, grid, variant)
        for path in self.find_installed(key):
            if path not in paths:
                self.add_installed_row(grid, path)
        for release in available:
            self.add_release_to_grid(release, grid, variant)

        self.hide_status(key, "list")

    def fetch_releases_from_url(self, variant, closed_event):
        releases = []
        seen_tags = set()
        url = variant["api_url"]
        params = {"per_page": RELEASES_PER_PAGE}
        prefix = variant["tag_prefix"]

        while url and not closed_event.is_set():
            response = requests.get(url, params=params, headers=github_api_headers(url), timeout=30)
            raise_for_api_status(response.status_code, response.headers)

            for release in response.json():
                tag_name = release["tag_name"]
                if tag_name in seen_tags:
                    continue
                seen_tags.add(tag_name)

                if not tag_name.startswith(prefix):
                    continue

                if "min_version" in variant:
                    try:
                        version_str = tag_name.replace(prefix, "")
                        major, minor = map(int, version_str.split("-"))
                        if (major, minor) < variant["min_version"]:
                            continue
                    except Exception:
                        continue

                assets = release.get("assets", [])
                has_valid_asset = any(asset["name"].endswith(variant["archive_ext"]) for asset in assets)
                if not has_valid_asset:
                    continue

                releases.append(release)

            # Servers may return fewer releases per page than requested
            # (dawn.wine caps pages at 30), so follow the Link header.
            url = response.links.get("next", {}).get("url")
            params = None

        return releases

    def find_installed(self, key):
        prefixes = VARIANTS[key]["installed_prefixes"]
        latest_dirs = {cfg["dir"] for cfg in CONFIGS.values()}

        found = []
        for compat_dir in COMPATIBILITY_DIRS:
            if not compat_dir.is_dir():
                continue
            for folder in compat_dir.iterdir():
                if (folder.is_dir() and folder.name not in latest_dirs
                        and folder.name.lower().startswith(prefixes)):
                    found.append(folder)

        def natural_key(path):
            return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]

        return sorted(found, key=natural_key, reverse=True)

    def add_installed_row(self, grid, path):
        row_index = len(widget_children(grid)) // 2

        label = Gtk.Label(label=path.name, xalign=0)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        grid.attach(label, 0, row_index, 1, 1)

        button = Gtk.Button()
        self.set_button_label(button, _("Remove"))
        button.connect("clicked", self.on_installed_remove_clicked, grid, path)
        button.set_size_request(120, -1)
        grid.attach(button, 1, row_index, 1, 1)

    def on_installed_remove_clicked(self, button, grid, path):
        try:
            shutil.rmtree(path)
        except OSError as e:
            print(f"Error removing {path}: {e}")
            return
        _column, row, _width, _height = grid.query_child(button)
        grid.remove_row(row)
        play_ui_sound("cancel")

    def add_release_to_grid(self, release, grid, variant):
        tag_name = release["tag_name"]
        display_tag_name = variant["tag_to_display"](tag_name)

        row_index = len(widget_children(grid)) // 2

        label = Gtk.Label(label=display_tag_name, xalign=0)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        grid.attach(label, 0, row_index, 1, 1)

        version_path = self.get_installed_path(tag_name, variant)
        is_installed = version_path.exists()

        button = Gtk.Button()
        self.set_button_label(button, _("Remove") if is_installed else _("Download"))
        button.connect("clicked", self.on_button_clicked, release, variant)
        button.set_size_request(120, -1)
        button.download_cancel_event = None
        button.progress_css_provider = None
        grid.attach(button, 1, row_index, 1, 1)

    def add_latest_row(self, kind):
        cfg = CONFIGS[kind]
        grid = self.grids[kind]
        proton_dir = COMPATIBILITY_DIR / cfg["dir"]

        label = Gtk.Label(label=f"{cfg['label']} Latest", xalign=0)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        grid.attach(label, 0, 0, 1, 1)

        button = Gtk.Button()
        self.set_button_label(button, _("Remove") if proton_dir.exists() else _("Download"))
        button.connect("clicked", self.on_latest_clicked, kind)
        button.set_size_request(120, -1)
        button.download_cancel_event = None
        button.progress_css_provider = None
        grid.attach(button, 1, 0, 1, 1)

    def on_latest_clicked(self, button, kind):
        if button.download_cancel_event is not None:
            button.download_cancel_event.set()
            play_ui_sound("cancel")
            return

        proton_dir = COMPATIBILITY_DIR / CONFIGS[kind]["dir"]
        if proton_dir.exists():
            shutil.rmtree(proton_dir, ignore_errors=True)
            self.set_button_label(button, _("Download"))
            play_ui_sound("cancel")
            return

        closed_event = self.closed_event
        cancel_event = threading.Event()
        button.download_cancel_event = cancel_event

        self.hide_status(kind, "latest")
        self.set_button_label(button, _("Cancel"))
        self.set_button_progress(button, 0)

        def finish(new_label):
            self.clear_button_progress(button)
            button.download_cancel_event = None
            self.set_button_label(button, new_label)

        def worker():
            last_pct = [-1]

            def _progress(frac):
                if cancel_event.is_set() or closed_event.is_set():
                    raise _DownloadCancelled()
                pct = int(frac * 100)
                if pct != last_pct[0]:
                    last_pct[0] = pct
                    idle_add_while_open(closed_event, self.set_button_progress, button, frac)

            try:
                ensure_latest(kind, _progress)
            except _DownloadCancelled:
                pass
            except Exception as e:
                idle_add_while_open(closed_event, self.show_error, kind, e, _("Download failed"), "latest")
            idle_add_while_open(closed_event, finish, _("Remove") if proton_dir.exists() else _("Download"))
            if proton_dir.exists():
                idle_add_while_open(closed_event, play_ui_sound, "confirm")

        run_in_background(worker)

    def get_installed_path(self, tag_name, variant):
        display_name = variant["tag_to_display"](tag_name)

        for compat_dir in COMPATIBILITY_DIRS:
            for name in (tag_name, display_name):
                p = compat_dir / name
                if p.exists():
                    return p

        pattern = re.compile(f"(?:{re.escape(tag_name)}|{re.escape(display_name)})(?!\\d)", re.IGNORECASE)
        for compat_dir in COMPATIBILITY_DIRS:
            if not compat_dir.exists():
                continue
            for folder in compat_dir.iterdir():
                if not folder.is_dir():
                    continue
                if pattern.search(folder.name):
                    return folder

        return COMPATIBILITY_DIR / display_name

    def set_button_label(self, button, label):
        button.set_label(label)
        if label == _("Remove"):
            button.add_css_class("destructive-action")
        else:
            button.remove_css_class("destructive-action")

    def set_button_progress(self, button, fraction):
        provider = button.progress_css_provider
        if provider is None:
            provider = Gtk.CssProvider()
            button.progress_css_provider = provider
            button.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        pct = max(0.0, min(1.0, fraction)) * 100
        r, g, b = get_effective_accent_rgb()
        css = (
            "button { background-image: linear-gradient(to right, "
            f"rgba({r}, {g}, {b}, 0.5) {pct:.1f}%, transparent {pct:.1f}%); }}"
        )
        provider.load_from_string(css)

    def clear_button_progress(self, button):
        if button.progress_css_provider is not None:
            button.get_style_context().remove_provider(button.progress_css_provider)
            button.progress_css_provider = None

    def on_button_clicked(self, widget, release, variant):
        if widget.download_cancel_event is not None:
            widget.download_cancel_event.set()
            play_ui_sound("cancel")
            return

        tag_name = release["tag_name"]
        version_path = self.get_installed_path(tag_name, variant)

        if version_path.exists():
            self.on_remove_clicked(widget, release, variant)
        else:
            self.on_download_clicked(widget, release, variant)

    def on_download_clicked(self, widget, release, variant):
        selected_asset = select_asset(release["assets"], variant["archive_ext"])

        if selected_asset:
            self.download_and_extract(
                selected_asset["browser_download_url"],
                selected_asset["name"],
                release["tag_name"],
                widget,
                variant,
            )
        else:
            print(release['tag_name'])

    def download_and_extract(self, url, filename, tag_name, button, variant):
        closed_event = self.closed_event
        cancel_event = threading.Event()
        button.download_cancel_event = cancel_event

        self.set_button_label(button, _("Cancel"))
        self.set_button_progress(button, 0)

        def finish(new_label):
            self.clear_button_progress(button)
            button.download_cancel_event = None
            self.set_button_label(button, new_label)

        def worker():
            try:
                COMPATIBILITY_DIR.mkdir(parents=True, exist_ok=True)

                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                last_pct = [-1]

                def _progress(frac):
                    if cancel_event.is_set() or closed_event.is_set():
                        raise _DownloadCancelled()
                    pct = int(frac * 100)
                    if pct != last_pct[0]:
                        last_pct[0] = pct
                        idle_add_while_open(closed_event, self.set_button_progress, button, frac)

                stream = StreamProgress(response.raw, total_size, _progress)

                with tarfile.open(fileobj=stream, mode=get_tar_mode(filename)) as tar:
                    tar.extractall(path=COMPATIBILITY_DIR, filter="fully_trusted")

                idle_add_while_open(closed_event, finish, _("Remove"))
                idle_add_while_open(closed_event, play_ui_sound, "confirm")

            except _DownloadCancelled:
                version_path = self.get_installed_path(tag_name, variant)
                if version_path.exists():
                    shutil.rmtree(version_path, ignore_errors=True)
                idle_add_while_open(closed_event, finish, _("Download"))

            except Exception as e:
                print(f"Error during download/extraction: {e}")
                idle_add_while_open(closed_event, finish, _("Download"))

        run_in_background(worker)

    def on_remove_clicked(self, widget, release, variant):
        tag_name = release["tag_name"]
        version_path = self.get_installed_path(tag_name, variant)
        if version_path.exists():
            try:
                shutil.rmtree(version_path)
                self.set_button_label(widget, _("Download"))
                play_ui_sound("cancel")
            except Exception:
                pass
