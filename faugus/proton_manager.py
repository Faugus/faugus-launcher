

import requests
import gi
import tarfile
import shutil
import threading
import warnings

from faugus.proton_downloader import select_asset, get_tar_mode

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib
from faugus.language_config import *
from faugus.utils import widget_children, hide_dialog_action_area, destroy_and_release, run_in_background, IdComboBox, apply_titlebar_preference, get_effective_accent_rgb

if IS_FLATPAK:
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
else:
    GLib.set_prgname("faugus-launcher")

_ = setup_gettext('faugus-launcher')

VARIANTS = {
    "cachyos": {
        "tab_label": "Proton-CachyOS",
        "api_url": "https://api.github.com/repos/CachyOS/proton-cachyos/releases",
        "tag_prefix": "cachyos-",
        "archive_ext": ["x86_64.tar.xz"],
        "tag_to_display": lambda tag: f"Proton-CachyOS-{tag.removeprefix('cachyos-')}",
    },
    "ge": {
        "tab_label": "GE-Proton",
        "api_url": "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases",
        "tag_prefix": "GE-Proton",
        "archive_ext": [".tar.gz", ".tar.xz"],
        "min_version": (9, 1),
        "tag_to_display": lambda tag: tag,
    },
    "em": {
        "tab_label": "Proton-EM",
        "api_url": "https://api.github.com/repos/Etaash-mathamsetty/Proton/releases",
        "tag_prefix": "EM-",
        "archive_ext": [".tar.xz"],
        "tag_to_display": lambda tag: f"proton-{tag}",
    },
    "dw": {
        "tab_label": "DW-Proton",
        "api_url": "https://dawn.wine/api/v1/repos/dawn-winery/dwproton/releases",
        "tag_prefix": "dwproton-",
        "archive_ext": ["x86_64.tar.xz"],
        "tag_to_display": lambda tag: f"DW-Proton-{tag.removeprefix('dwproton-')}",
    },
}


class _DownloadCancelled(Exception):
    pass


class _StreamProgress:
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


class ProtonDownloader(Gtk.Dialog):
    def __init__(self):
        super().__init__(title=_("Proton Manager"))
        apply_titlebar_preference(self)
        hide_dialog_action_area(self)
        self.set_resizable(False)
        self.set_modal(True)

        self.closed_event = threading.Event()

        self.content_area = self.get_content_area()
        self.content_area.set_halign(Gtk.Align.CENTER)
        self.content_area.set_valign(Gtk.Align.CENTER)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)

        self.view_stack = Gtk.Stack()
        self.view_stack.set_halign(Gtk.Align.FILL)
        self.view_stack.set_valign(Gtk.Align.FILL)
        self.view_stack.set_vexpand(True)
        self.view_stack.set_hexpand(True)

        self.tab_switcher = IdComboBox()
        self.tab_switcher.set_hexpand(True)
        self.tab_switcher.set_margin_top(10)
        self.tab_switcher.set_margin_start(10)
        self.tab_switcher.set_margin_end(10)
        self.tab_switcher.connect(
            "changed",
            lambda combo: self.view_stack.set_visible_child_name(combo.get_active_id())
        )

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
        for key, variant in VARIANTS.items():
            grid = Gtk.Grid()
            grid.set_hexpand(True)
            grid.set_row_spacing(5)
            grid.set_column_spacing(20)
            grid.set_margin_start(10)
            grid.set_margin_end(10)
            grid.set_margin_bottom(10)

            self.view_stack.add_titled(grid, key, variant["tab_label"])

            self.tab_switcher.append(key, variant["tab_label"])

            self.grids[key] = grid

        self.tab_switcher.set_active(0)

        self.get_releases()

    def get_releases(self):
        closed_event = self.closed_event
        for key, variant in VARIANTS.items():
            run_in_background(self.fetch_releases_from_url, variant, self.grids[key], closed_event)

    def fetch_releases_from_url(self, variant, grid, closed_event):
        page = 1
        seen_tags = set()
        url = variant["api_url"]
        prefix = variant["tag_prefix"]

        while not closed_event.is_set():
            response = requests.get(url, params={"page": page, "per_page": 100})
            if response.status_code == 200:
                page_releases = response.json()
                if not page_releases:
                    break

                for release in page_releases:
                    if closed_event.is_set():
                        return

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
                    has_valid_asset = any(
                        any(asset["name"].endswith(ext) for ext in variant["archive_ext"])
                        for asset in assets
                    )
                    if not has_valid_asset:
                        continue

                    GLib.idle_add(self.add_release_to_grid, release, grid, variant, closed_event)

                page += 1
            else:
                break

    def add_release_to_grid(self, release, grid, variant, closed_event):
        if closed_event.is_set():
            return

        tag_name = release["tag_name"]
        display_tag_name = variant["tag_to_display"](tag_name)

        row_index = len(widget_children(grid)) // 2

        label = Gtk.Label(label=display_tag_name, xalign=0)
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        grid.attach(label, 0, row_index, 1, 1)

        version_path = self.get_installed_path(tag_name, variant)
        is_installed = version_path.exists()

        button = Gtk.Button(label=_("Remove") if is_installed else _("Download"))
        button.connect("clicked", self.on_button_clicked, release, variant)
        button.set_size_request(120, -1)
        button.download_cancel_event = None
        button.progress_css_provider = None
        grid.attach(button, 1, row_index, 1, 1)

    def get_installed_path(self, tag_name, variant):
        display_name = variant["tag_to_display"](tag_name)

        for compat_dir in COMPATIBILITY_DIRS:
            for name in (tag_name, display_name):
                p = compat_dir / name
                if p.exists():
                    return p

        tag_lower = tag_name.lower()
        display_lower = display_name.lower()
        for compat_dir in COMPATIBILITY_DIRS:
            if not compat_dir.exists():
                continue
            for folder in compat_dir.iterdir():
                if not folder.is_dir():
                    continue
                fn_lower = folder.name.lower()
                if fn_lower == tag_lower or fn_lower == display_lower:
                    return folder
                if tag_lower in fn_lower or display_lower in fn_lower:
                    return folder

        return COMPATIBILITY_DIR / display_name

    def update_button(self, button, new_label):
        button.set_label(new_label)
        button.set_sensitive(True)

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

        button.set_label(_("Cancel"))
        self.set_button_progress(button, 0)

        def safe_idle_add(*args):
            if not closed_event.is_set():
                GLib.idle_add(*args)

        def finish(new_label):
            self.clear_button_progress(button)
            button.download_cancel_event = None
            button.set_label(new_label)

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
                    pct = int(frac * 1000)
                    if pct != last_pct[0]:
                        last_pct[0] = pct
                        safe_idle_add(self.set_button_progress, button, frac)

                stream = _StreamProgress(response.raw, total_size, _progress)

                with tarfile.open(fileobj=stream, mode=get_tar_mode(filename)) as tar:
                    tar.extractall(path=COMPATIBILITY_DIR, filter="fully_trusted")

                safe_idle_add(finish, _("Remove"))

            except _DownloadCancelled:
                version_path = self.get_installed_path(tag_name, variant)
                if version_path and version_path.exists():
                    shutil.rmtree(version_path, ignore_errors=True)
                safe_idle_add(finish, _("Download"))

            except Exception as e:
                print(f"Error during download/extraction: {e}")
                safe_idle_add(finish, _("Download"))

        run_in_background(worker)

    def on_remove_clicked(self, widget, release, variant):
        tag_name = release["tag_name"]
        version_path = self.get_installed_path(tag_name, variant)
        if version_path and version_path.exists():
            try:
                shutil.rmtree(version_path)
                self.update_button(widget, _("Download"))
            except Exception:
                pass


def main():
    app = Gtk.Application()

    def on_activate(app):
        win = ProtonDownloader()
        win.connect("response", lambda d, r: (d.closed_event.set(), destroy_and_release(d)))
        win.connect("destroy", lambda *a: app.quit())
        win.present()

    app.connect("activate", on_activate)
    app.run(None)


if __name__ == "__main__":
    main()
