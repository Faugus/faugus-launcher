

import requests
import gi
import tarfile
import shutil
import threading
import warnings

from faugus.proton_downloader import CONFIGS, select_asset, get_tar_mode

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib
from faugus.language_config import *
from faugus.utils import widget_children, hide_dialog_action_area, destroy_and_release, run_in_background

if IS_FLATPAK:
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
else:
    GLib.set_prgname("faugus-launcher")

_ = setup_gettext('faugus-launcher')

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
        super().__init__(title=_("Faugus Proton Manager"))
        hide_dialog_action_area(self)
        self.set_resizable(False)
        self.set_modal(True)

        self.closed_event = threading.Event()

        self.content_area = self.get_content_area()
        self.content_area.set_halign(Gtk.Align.CENTER)
        self.content_area.set_valign(Gtk.Align.CENTER)
        self.content_area.set_vexpand(True)
        self.content_area.set_hexpand(True)

        self.notebook = Gtk.Notebook()
        self.notebook.set_halign(Gtk.Align.FILL)
        self.notebook.set_valign(Gtk.Align.FILL)
        self.notebook.set_vexpand(True)
        self.notebook.set_hexpand(True)
        self.notebook.set_margin_start(10)
        self.notebook.set_margin_end(10)
        self.notebook.set_margin_top(10)
        self.notebook.set_margin_bottom(10)
        self.content_area.append(self.notebook)

        self.label_progress = Gtk.Label(label="")
        self.label_progress.set_margin_start(10)
        self.label_progress.set_margin_end(10)
        self.label_progress.set_margin_bottom(10)
        self.content_area.append(self.label_progress)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_margin_start(10)
        self.progress_bar.set_margin_end(10)
        self.progress_bar.set_margin_bottom(10)
        self.content_area.append(self.progress_bar)

        self.grids = {}
        for key, variant in CONFIGS.items():
            grid = Gtk.Grid()
            grid.set_hexpand(True)
            grid.set_row_spacing(5)
            grid.set_column_spacing(10)
            scroll = Gtk.ScrolledWindow()
            scroll.set_size_request(400, 400)
            scroll.set_margin_top(10)
            scroll.set_margin_bottom(10)
            scroll.set_margin_start(10)
            scroll.set_margin_end(10)
            scroll.set_child(grid)

            tab_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            tab_label = Gtk.Label(label=variant["tab_label"])
            tab_label.set_width_chars(15)
            tab_label.set_xalign(0.5)
            tab_label.set_hexpand(True)
            tab_box.append(tab_label)
            tab_box.set_hexpand(True)
            self.notebook.append_page(scroll, tab_box)
            self.grids[key] = grid

        self.get_releases()
        self.progress_bar.set_visible(False)
        self.label_progress.set_visible(False)

    def get_releases(self):
        closed_event = self.closed_event
        for key, variant in CONFIGS.items():
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
        grid.attach(button, 1, row_index, 1, 1)

    def get_installed_path(self, tag_name, variant):
        display_name = variant["tag_to_display"](tag_name)

        for name in (tag_name, display_name):
            p = COMPATIBILITY_DIR / name
            if p.exists():
                return p

        if COMPATIBILITY_DIR.exists():
            tag_lower = tag_name.lower()
            display_lower = display_name.lower()
            for folder in COMPATIBILITY_DIR.iterdir():
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

    def on_button_clicked(self, widget, release, variant):
        tag_name = release["tag_name"]
        version_path = self.get_installed_path(tag_name, variant)

        if version_path.exists():
            self.on_remove_clicked(widget, release, variant)
        else:
            self.progress_bar.set_visible(True)
            self.label_progress.set_visible(True)
            self.on_download_clicked(widget, release, variant)

    def disable_all_buttons(self):
        for grid in self.grids.values():
            for child in widget_children(grid):
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(False)

    def enable_all_buttons(self):
        for grid in self.grids.values():
            for child in widget_children(grid):
                if isinstance(child, Gtk.Button):
                    child.set_sensitive(True)

    def on_download_clicked(self, widget, release, variant):
        self.disable_all_buttons()

        selected_asset = select_asset(release["assets"], variant["archive_ext"])

        if selected_asset:
            self.download_and_extract(
                selected_asset["browser_download_url"],
                selected_asset["name"],
                release["tag_name"],
                widget
            )
        else:
            print(release['tag_name'])
            self.enable_all_buttons()

    def download_and_extract(self, url, filename, tag_name, button):
        closed_event = self.closed_event
        progress_bar = self.progress_bar
        label_progress = self.label_progress
        update_button = self.update_button
        enable_all_buttons = self.enable_all_buttons

        button.set_label(_("Downloading..."))
        button.set_sensitive(False)
        label_progress.set_text(_("Downloading %s...") % tag_name)
        label_progress.set_visible(True)
        progress_bar.set_visible(True)
        progress_bar.set_fraction(0)
        progress_bar.set_text("0%")

        main_context = GLib.MainContext.default()
        while main_context.pending():
            main_context.iteration(False)

        def safe_idle_add(*args):
            if not closed_event.is_set():
                GLib.idle_add(*args)

        def worker():
            try:
                COMPATIBILITY_DIR.mkdir(parents=True, exist_ok=True)

                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                last_pct = [-1]

                def _progress(frac):
                    pct = int(frac * 1000)
                    if pct != last_pct[0]:
                        last_pct[0] = pct
                        safe_idle_add(progress_bar.set_fraction, frac)
                        safe_idle_add(progress_bar.set_text, f"{pct / 10:.1f}%")

                stream = _StreamProgress(response.raw, total_size, _progress)

                with tarfile.open(fileobj=stream, mode=get_tar_mode(filename)) as tar:
                    tar.extractall(path=COMPATIBILITY_DIR, filter="fully_trusted")

                safe_idle_add(update_button, button, _("Remove"))
                safe_idle_add(progress_bar.set_visible, False)
                safe_idle_add(label_progress.set_visible, False)

            except Exception as e:
                print(f"Error during download/extraction: {e}")
                safe_idle_add(update_button, button, _("Download"))
                safe_idle_add(label_progress.set_text, _("Error during download"))
            finally:
                safe_idle_add(enable_all_buttons)
                safe_idle_add(button.grab_focus)

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
