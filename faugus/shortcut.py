#!/usr/bin/python3

import sys
import gi
import shutil

gi.require_version("Gtk", "3.0")
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from faugus.utils import *
from faugus.config_manager import *
from faugus.steam_setup import lossless_dll

if IS_FLATPAK:
    faugus_png = PathManager.get_icon('io.github.Faugus.faugus-launcher.svg')
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
    lsfgvk_possible_paths = [
        Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')), # Deprecated in LSFG-VK v2.0
        Path("/usr/lib/extensions/vulkan/lsfgvk/lib/liblsfg-vk-layer.so"),
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so')),
    ]
    lsfgvk_path = next((p for p in lsfgvk_possible_paths if p.exists()), lsfgvk_possible_paths[-1])
else:
    faugus_png = PathManager.get_icon('faugus-launcher.svg')
    GLib.set_prgname("faugus-launcher")
    lsfgvk_possible_paths = [
        Path("/usr/lib/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path("/usr/lib64/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path("/usr/local/lib/liblsfg-vk.so"), # Deprecated in LSFG-VK v2.0
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk.so')), # Deprecated in LSFG-VK v2.0
        Path("/usr/lib/liblsfg-vk-layer.so"),
        Path("/usr/lib64/liblsfg-vk-layer.so"),
        Path(os.path.expanduser('~/.local/lib/liblsfg-vk-layer.so'))
    ]
    lsfgvk_path = next((p for p in lsfgvk_possible_paths if p.exists()), lsfgvk_possible_paths[-1])

icons_dir = PathManager.user_config('faugus-launcher/icons-nolauncher')
presets_file = PathManager.user_config('faugus-launcher/presets.json')

_ = setup_gettext('faugus-launcher')

class CreateShortcut(Gtk.Window, HiDpiMixin):
    def __init__(self, file_path):
        super().__init__(title="Faugus Launcher")
        self.set_wmclass("faugus-launcher", "faugus-launcher")
        self.file_path = file_path
        self.set_resizable(False)

        game_title = os.path.basename(file_path)
        self.set_title(game_title)
        print(self.file_path)

        self.icon_directory = f"{icons_dir}/icon_temp/"

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        self.icons_path = icons_dir
        self.icon_extracted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.ico')
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.ico'

        self.addapp_enabled = False
        self.addapp = ""
        self.addapp_delay = ""
        self.addapp_first = False

        self.launch_arguments = ""

        self.lossless_enabled = False
        self.lossless_multiplier = 1
        self.lossless_flow = 100
        self.lossless_performance = False
        self.lossless_hdr = False
        self.lossless_present = False

        self.label_title = Gtk.Label(label=_("Title"))
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", on_entry_changed, self.entry_title)
        self.entry_title.set_tooltip_text(_("Game Title"))

        self.label_protonfix = Gtk.Label(label="Protonfix")
        self.label_protonfix.set_halign(Gtk.Align.START)
        self.entry_protonfix = Gtk.Entry()
        self.entry_protonfix.set_tooltip_text("UMU ID")
        self.button_search_protonfix = Gtk.Button()
        self.button_search_protonfix.set_image(
            Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.button_search_protonfix.connect("clicked", on_button_search_protonfix_clicked)
        self.button_search_protonfix.set_size_request(50, -1)

        self.label_game_arguments = Gtk.Label(label=_("Game Arguments"))
        self.label_game_arguments.set_halign(Gtk.Align.START)
        self.entry_game_arguments = Gtk.Entry()
        self.entry_game_arguments.set_tooltip_text(_("e.g.: -d3d11 -fullscreen"))

        self.button_launch_arguments = Gtk.Button(label=_("Launch Arguments"))
        self.button_launch_arguments.connect("clicked", self.on_button_launch_arguments_clicked)
        self.button_launch_arguments.set_tooltip_text(_("e.g.: PROTON_USE_WINED3D=1 gamescope -W 2560 -H 1440"))

        self.button_addapp = Gtk.Button(label=_("Additional Application"))
        self.button_addapp.connect("clicked", self.on_button_addapp_clicked)
        self.button_addapp.set_tooltip_text(
            _("Additional application to run with the game, like Cheat Engine, Trainers, Mods..."))

        self.button_lossless = Gtk.Button(label=_("Lossless Scaling Frame Generation"))
        self.button_lossless.connect("clicked", self.on_button_lossless_clicked)

        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_size_request(120, -1)
        self.button_shortcut_icon.set_tooltip_text(_("Select an icon for the shortcut"))
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)

        self.checkbox_mangohud = Gtk.CheckButton(label="MangoHud")
        self.checkbox_mangohud.set_tooltip_text(
            _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more."))
        self.checkbox_gamemode = Gtk.CheckButton(label="GameMode")
        self.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance."))
        self.checkbox_disable_hidraw = Gtk.CheckButton(label=_("Disable Hidraw"))
        self.checkbox_disable_hidraw.set_tooltip_text(
            _("May fix controller issues with some games. Only works with GE-Proton10 or Proton-EM-10."))
        self.checkbox_prevent_sleep = Gtk.CheckButton(label=_("Prevent Sleep"))

        # Button Cancel
        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", self.on_cancel_clicked)
        self.button_cancel.set_size_request(150, -1)

        # Button Ok
        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", self.on_ok_clicked)
        self.button_ok.set_size_request(150, -1)

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.box.set_margin_start(0)
        self.box.set_margin_end(0)
        self.box.set_margin_top(0)
        self.box.set_margin_bottom(0)

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        self.grid_title = Gtk.Grid()
        self.grid_title.set_row_spacing(10)
        self.grid_title.set_column_spacing(10)
        self.grid_title.set_margin_start(10)
        self.grid_title.set_margin_end(10)
        self.grid_title.set_margin_top(10)

        self.grid_protonfix = Gtk.Grid()
        self.grid_protonfix.set_row_spacing(10)
        self.grid_protonfix.set_column_spacing(10)
        self.grid_protonfix.set_margin_start(10)
        self.grid_protonfix.set_margin_end(10)
        self.grid_protonfix.set_margin_top(10)

        self.grid_launch_arguments = Gtk.Grid()
        self.grid_launch_arguments.set_row_spacing(10)
        self.grid_launch_arguments.set_column_spacing(10)
        self.grid_launch_arguments.set_margin_start(10)
        self.grid_launch_arguments.set_margin_end(10)
        self.grid_launch_arguments.set_margin_top(10)

        self.grid_game_arguments = Gtk.Grid()
        self.grid_game_arguments.set_row_spacing(10)
        self.grid_game_arguments.set_column_spacing(10)
        self.grid_game_arguments.set_margin_start(10)
        self.grid_game_arguments.set_margin_end(10)
        self.grid_game_arguments.set_margin_top(10)

        self.grid_lossless = Gtk.Grid()
        self.grid_lossless.set_row_spacing(10)
        self.grid_lossless.set_column_spacing(10)
        self.grid_lossless.set_margin_start(10)
        self.grid_lossless.set_margin_end(10)
        self.grid_lossless.set_margin_top(10)

        self.grid_addapp = Gtk.Grid()
        self.grid_addapp.set_row_spacing(10)
        self.grid_addapp.set_column_spacing(10)
        self.grid_addapp.set_margin_start(10)
        self.grid_addapp.set_margin_end(10)
        self.grid_addapp.set_margin_top(10)

        self.grid_title.attach(self.label_title, 0, 0, 4, 1)
        self.grid_title.attach(self.entry_title, 0, 1, 4, 1)
        self.entry_title.set_hexpand(True)

        self.grid_protonfix.attach(self.label_protonfix, 0, 0, 1, 1)
        self.grid_protonfix.attach(self.entry_protonfix, 0, 1, 3, 1)
        self.entry_protonfix.set_hexpand(True)
        self.grid_protonfix.attach(self.button_search_protonfix, 3, 1, 1, 1)

        self.grid_game_arguments.attach(self.label_game_arguments, 0, 0, 4, 1)
        self.grid_game_arguments.attach(self.entry_game_arguments, 0, 1, 4, 1)
        self.entry_game_arguments.set_hexpand(True)

        self.grid_launch_arguments.attach(self.button_launch_arguments, 0, 0, 1, 1)
        self.button_launch_arguments.set_hexpand(True)

        self.grid_addapp.attach(self.button_addapp, 0, 0, 1, 1)
        self.button_addapp.set_hexpand(True)

        self.grid_lossless.attach(self.button_lossless, 0, 0, 1, 1)
        self.button_lossless.set_hexpand(True)

        self.grid_tools = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.grid_tools.set_row_spacing(10)
        self.grid_tools.set_column_spacing(10)
        self.grid_tools.set_margin_start(10)
        self.grid_tools.set_margin_end(10)
        self.grid_tools.set_margin_top(10)
        self.grid_tools.set_margin_bottom(10)

        self.grid_shortcut_icon = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.grid_shortcut_icon.set_row_spacing(10)
        self.grid_shortcut_icon.set_column_spacing(10)
        self.grid_shortcut_icon.set_margin_start(10)
        self.grid_shortcut_icon.set_margin_end(10)
        self.grid_shortcut_icon.set_margin_top(10)
        self.grid_shortcut_icon.set_margin_bottom(10)

        self.grid_tools.add(self.checkbox_mangohud)
        self.grid_tools.add(self.checkbox_gamemode)
        self.grid_tools.add(self.checkbox_prevent_sleep)
        self.grid_tools.add(self.checkbox_disable_hidraw)

        self.grid_shortcut_icon.add(self.button_shortcut_icon)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)

        self.box_tools = Gtk.Box()
        self.box_tools.pack_start(self.grid_tools, False, False, 0)
        self.box_tools.pack_end(self.grid_shortcut_icon, False, False, 0)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        # botton_box.set_margin_top(10)
        bottom_box.set_margin_bottom(10)

        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        bottom_box.pack_start(self.button_cancel, True, True, 0)
        bottom_box.pack_start(self.button_ok, True, True, 0)

        self.main_grid = Gtk.Grid(orientation=Gtk.Orientation.VERTICAL)
        self.main_grid.add(self.grid_title)
        self.main_grid.add(self.grid_protonfix)
        self.main_grid.add(self.grid_game_arguments)
        self.main_grid.add(self.grid_launch_arguments)
        self.main_grid.add(self.grid_addapp)
        self.main_grid.add(self.grid_lossless)
        self.main_grid.add(self.box_tools)

        self.load_config()

        self.mangohud_enabled = os.path.exists(mangohud_dir)
        if not self.mangohud_enabled:
            self.checkbox_mangohud.set_sensitive(False)
            self.checkbox_mangohud.set_active(False)
            self.checkbox_mangohud.set_tooltip_text(
                _("Shows an overlay for monitoring FPS, temperatures, CPU/GPU load and more. NOT INSTALLED."))

        self.gamemode_enabled = os.path.exists(gamemoderun) or os.path.exists("/usr/games/gamemoderun")
        if not self.gamemode_enabled:
            self.checkbox_gamemode.set_sensitive(False)
            self.checkbox_gamemode.set_active(False)
            self.checkbox_gamemode.set_tooltip_text(_("Tweaks your system to improve performance. NOT INSTALLED."))

        if os.path.exists(lsfgvk_path):
            if lossless_dll or os.path.exists(self.lossless_location):
                self.button_lossless.set_sensitive(True)
            else:
                self.button_lossless.set_sensitive(False)
                self.button_lossless.set_tooltip_text(_("Lossless.dll NOT FOUND. If it's installed, go to Faugus Launcher's settings and set the location."))
        else:
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Lossless Scaling Vulkan Layer NOT INSTALLED."))

        frame.add(self.main_grid)
        self.box.add(frame)
        self.box.add(bottom_box)
        self.add(self.box)

        if not os.path.exists(self.icon_directory):
            os.makedirs(self.icon_directory)

        status = extract_ico_frames(self.file_path, self.icon_temp)
        if status == "ok":
            surface = self.new_surface_from_image(self.icon_temp, 50, 50)
            self.button_shortcut_icon.set_image(Gtk.Image.new_from_surface(surface))
        elif status == "no_icons":
            self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())

        shutil.rmtree(self.icon_directory, ignore_errors=True)

        # Connect the destroy signal to Gtk.main_quit
        self.connect("destroy", Gtk.main_quit)

    def on_button_launch_arguments_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Launch Arguments"), parent=self, flags=0)
        dialog.set_resizable(False)
        dialog.set_modal(True)
        dialog.set_default_size(650, 400)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hbox.set_margin_start(10)
        hbox.set_margin_end(10)
        hbox.set_margin_top(10)
        hbox.set_margin_bottom(10)

        store_presets = Gtk.ListStore(str)

        if os.path.exists(presets_file):
            try:
                with open(presets_file, "r") as f:
                    for item in json.load(f):
                        store_presets.append([item])
            except Exception:
                pass
        store_presets.append([""])

        tree_presets = Gtk.TreeView(model=store_presets)
        tree_presets.set_hexpand(True)
        tree_presets.set_vexpand(True)
        renderer_presets = Gtk.CellRendererText()
        renderer_presets.set_property("editable", True)

        def on_preset_edited(renderer, path, new_text):
            store_presets[path][0] = new_text
            if path == str(len(store_presets) - 1) and new_text.strip() != "":
                store_presets.append([""])

        def on_preset_key_press(widget, event):
            if event.keyval == Gdk.KEY_Delete:
                selection = widget.get_selection()
                model, treeiter = selection.get_selected()
                if treeiter is not None:
                    if model[treeiter][0] != "" or len(model) > 1:
                        model.remove(treeiter)
                    if len(model) == 0 or model[-1][0] != "":
                        model.append([""])
                return True
            return False

        renderer_presets.connect("edited", on_preset_edited)
        tree_presets.connect("key-press-event", on_preset_key_press)
        column_presets = Gtk.TreeViewColumn(_("Presets"), renderer_presets, text=0)
        tree_presets.append_column(column_presets)
        scroll_presets = Gtk.ScrolledWindow()
        scroll_presets.add(tree_presets)

        btn_copy = Gtk.Button()
        btn_copy.set_size_request(50, 50)
        btn_copy.set_valign(Gtk.Align.CENTER)

        img = Gtk.Image.new_from_icon_name("faugus-play-symbolic", Gtk.IconSize.BUTTON)

        def flip_image(w, cr):
            cr.translate(w.get_allocated_width(), 0)
            cr.scale(-1, 1)
            return False

        img.connect("draw", flip_image)
        btn_copy.set_image(img)

        store_args = Gtk.ListStore(str)
        current_args = self.launch_arguments.split("\n")
        for arg in current_args:
            if arg.strip():
                store_args.append([arg])
        store_args.append([""])

        tree_args = Gtk.TreeView(model=store_args)
        tree_args.set_hexpand(True)
        tree_args.set_vexpand(True)
        renderer_args = Gtk.CellRendererText()
        renderer_args.set_property("editable", True)

        def on_arg_edited(renderer, path, new_text):
            store_args[path][0] = new_text
            if path == str(len(store_args) - 1) and new_text.strip() != "":
                store_args.append([""])

        def on_arg_key_press(widget, event):
            if event.keyval == Gdk.KEY_Delete:
                selection = widget.get_selection()
                model, treeiter = selection.get_selected()
                if treeiter is not None:
                    if model[treeiter][0] != "" or len(model) > 1:
                        model.remove(treeiter)
                    if len(model) == 0 or model[-1][0] != "":
                        model.append([""])
                return True
            return False

        renderer_args.connect("edited", on_arg_edited)
        tree_args.connect("key-press-event", on_arg_key_press)
        column_args = Gtk.TreeViewColumn(_("Launch Arguments"), renderer_args, text=0)
        tree_args.append_column(column_args)
        scroll_args = Gtk.ScrolledWindow()
        scroll_args.add(tree_args)

        sel_presets = tree_presets.get_selection()
        sel_args = tree_args.get_selection()

        def on_presets_selection_changed(sel):
            if sel.count_selected_rows() > 0:
                sel_args.unselect_all()

        def on_args_selection_changed(sel):
            if sel.count_selected_rows() > 0:
                sel_presets.unselect_all()

        sel_presets.connect("changed", on_presets_selection_changed)
        sel_args.connect("changed", on_args_selection_changed)

        def on_copy_clicked(btn):
            selection = tree_presets.get_selection()
            model, treeiter = selection.get_selected()
            if treeiter is not None:
                val = model[treeiter][0].strip()
                if val:
                    store_args.insert(len(store_args) - 1, [val])

        btn_copy.connect("clicked", on_copy_clicked)

        hbox.pack_start(scroll_args, True, True, 0)
        hbox.pack_start(btn_copy, False, False, 0)
        hbox.pack_start(scroll_presets, True, True, 0)

        content_area = dialog.get_content_area()
        content_area.pack_start(hbox, True, True, 0)

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.set_size_request(150, -1)
        button_cancel.set_hexpand(True)
        button_cancel.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.set_hexpand(True)
        button_ok.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)
        bottom_box.pack_start(button_cancel, True, True, 0)
        bottom_box.pack_start(button_ok, True, True, 0)

        content_area.pack_start(bottom_box, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            presets_to_save = [row[0] for row in store_presets if row[0].strip()]
            with open(presets_file, "w") as f:
                json.dump(presets_to_save, f)

            args_to_save = [row[0] for row in store_args if row[0].strip()]
            self.launch_arguments = "\n".join(args_to_save)

        dialog.destroy()
        return response

    def on_button_addapp_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Additional Application"), parent=self, flags=0)
        dialog.set_modal(True)
        dialog.set_resizable(False)

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)

        enabled = val if (val := getattr(self, "addapp_enabled", False)) != "" else False
        addapp = val if (val := getattr(self, "addapp", "")) != "" else ""
        addapp_delay = val if (val := getattr(self, "addapp_delay", "")) != "" else ""
        addapp_first = val if (val := getattr(self, "addapp_first", False)) != "" else False

        checkbox_enable = Gtk.CheckButton(label=_("Enable"))
        checkbox_enable.set_active(enabled)
        checkbox_enable.set_halign(Gtk.Align.START)

        label_path = Gtk.Label(label=_("Path"))
        label_path.set_halign(Gtk.Align.START)

        self.entry_addapp = Gtk.Entry()
        self.entry_addapp.set_text(addapp)
        self.entry_addapp.set_tooltip_text(_("/path/to/the/app"))
        self.entry_addapp.set_has_tooltip(True)
        self.entry_addapp.connect("query-tooltip", on_entry_query_tooltip)
        self.entry_addapp.set_hexpand(True)

        button_search_addapp = Gtk.Button()
        button_search_addapp.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        button_search_addapp.connect("clicked", self.on_button_search_addapp_clicked)
        button_search_addapp.set_size_request(50, -1)

        label_delay = Gtk.Label(label=_("Delay (seconds)"))
        label_delay.set_halign(Gtk.Align.START)

        adjustment = Gtk.Adjustment(
            value=int(addapp_delay) if addapp_delay else 0,
            lower=0,
            upper=60,
            step_increment=1,
            page_increment=10,
            page_size=0
        )

        self.entry_delay = Gtk.SpinButton()
        self.entry_delay.set_adjustment(adjustment)
        self.entry_delay.set_numeric(True)
        self.entry_delay.set_hexpand(True)

        checkbox_addapp_first = Gtk.CheckButton(label=_("Run the application first"))
        checkbox_addapp_first.set_active(addapp_first)
        checkbox_addapp_first.set_halign(Gtk.Align.START)

        def on_enable_toggled(cb):
            active = cb.get_active()
            label_path.set_sensitive(active)
            self.entry_addapp.set_sensitive(active)
            button_search_addapp.set_sensitive(active)
            label_delay.set_sensitive(active)
            self.entry_delay.set_sensitive(active)
            checkbox_addapp_first.set_sensitive(active)

        checkbox_enable.connect("toggled", on_enable_toggled)
        on_enable_toggled(checkbox_enable)

        grid.attach(checkbox_enable,        0, 0, 1, 1)
        grid.attach(label_path,             0, 1, 1, 1)
        grid.attach(self.entry_addapp,      0, 2, 3, 1)
        grid.attach(button_search_addapp,   3, 2, 1, 1)
        grid.attach(label_delay,            0, 3, 1, 1)
        grid.attach(self.entry_delay,       0, 4, 4, 1)
        grid.attach(checkbox_addapp_first,  0, 5, 1, 1)

        frame.add(grid)

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.set_size_request(150, -1)
        button_cancel.set_hexpand(True)
        button_cancel.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.set_hexpand(True)
        button_ok.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)
        bottom_box.pack_start(button_cancel, True, True, 0)
        bottom_box.pack_start(button_ok, True, True, 0)

        content_area = dialog.get_content_area()
        content_area.pack_start(frame, True, True, 0)
        content_area.pack_start(bottom_box, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.addapp_enabled = checkbox_enable.get_active()
            self.addapp = self.entry_addapp.get_text()
            self.addapp_delay = self.entry_delay.get_text()
            self.addapp_first = checkbox_addapp_first.get_active()

        dialog.destroy()
        return response

    def on_button_lossless_clicked(self, widget):
        dialog = Gtk.Dialog(title=_("Lossless Scaling Frame Generation"), parent=self, flags=0)
        dialog.set_modal(True)
        dialog.set_resizable(False)

        frame = Gtk.Frame()
        frame.set_margin_start(10)
        frame.set_margin_end(10)
        frame.set_margin_top(10)
        frame.set_margin_bottom(10)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)

        enabled = val if (val := getattr(self, "lossless_enabled", False)) != "" else False
        multiplier = val if (val := getattr(self, "lossless_multiplier", 1)) != "" else 1
        flow = val if (val := getattr(self, "lossless_flow", 100)) != "" else 100
        performance = val if (val := getattr(self, "lossless_performance", False)) != "" else False
        hdr = val if (val := getattr(self, "lossless_hdr", False)) != "" else False
        present = val if (val := getattr(self, "lossless_present", False)) != "" else "VSync/FIFO (default)"

        checkbox_enable = Gtk.CheckButton(label=_("Enable"))
        checkbox_enable.set_active(enabled)
        checkbox_enable.set_halign(Gtk.Align.START)

        label_multiplier = Gtk.Label(label=_("Multiplier"))
        label_multiplier.set_halign(Gtk.Align.START)
        spin_multiplier = Gtk.SpinButton()
        spin_multiplier.set_adjustment(Gtk.Adjustment(value=multiplier, lower=1, upper=20, step_increment=1))
        spin_multiplier.set_numeric(True)
        spin_multiplier.set_tooltip_text(_("Multiply the FPS."))

        label_flow = Gtk.Label(label=_("Flow Scale"))
        label_flow.set_halign(Gtk.Align.START)
        adjustment = Gtk.Adjustment(value=flow, lower=25, upper=100, step_increment=1)
        scale_flow = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale_flow.set_digits(0)
        scale_flow.set_hexpand(True)
        scale_flow.set_value_pos(Gtk.PositionType.RIGHT)
        scale_flow.set_tooltip_text(_("Lower the internal motion estimation resolution."))

        checkbox_performance = Gtk.CheckButton(label=_("Performance Mode"))
        checkbox_performance.set_tooltip_text(_("Massively improve performance at the cost of quality."))
        checkbox_performance.set_active(performance)

        checkbox_hdr = Gtk.CheckButton(label=_("HDR Mode"))
        checkbox_hdr.set_tooltip_text(_("Enable special HDR-only behavior."))
        checkbox_hdr.set_active(hdr)

        label_present = Gtk.Label(label=_("Present Mode (Experimental)"))
        label_present.set_halign(Gtk.Align.START)

        combobox_present = Gtk.ComboBoxText()
        combobox_present.set_tooltip_text(_("Override the present mode."))

        options = [
            "VSync/FIFO (default)",
            "Mailbox",
            "Immediate",
        ]

        for opt in options:
            combobox_present.append_text(opt)

        mapping = {
            "fifo": "VSync/FIFO (default)",
            "mailbox": "Mailbox",
            "immediate": "Immediate",
        }

        ui_value = mapping.get(present, "VSync/FIFO (default)")
        combobox_present.set_active(options.index(ui_value))

        def on_enable_toggled(cb):
            active = cb.get_active()
            label_multiplier.set_sensitive(active)
            spin_multiplier.set_sensitive(active)
            label_flow.set_sensitive(active)
            scale_flow.set_sensitive(active)
            checkbox_performance.set_sensitive(active)
            checkbox_hdr.set_sensitive(active)
            label_present.set_sensitive(active)
            combobox_present.set_sensitive(active)

        checkbox_enable.connect("toggled", on_enable_toggled)
        on_enable_toggled(checkbox_enable)

        grid.attach(checkbox_enable,        0, 0, 1, 1)
        grid.attach(label_multiplier,       0, 1, 1, 1)
        grid.attach(spin_multiplier,        0, 2, 1, 1)
        grid.attach(label_flow,             0, 3, 1, 1)
        grid.attach(scale_flow,             0, 4, 1, 1)
        grid.attach(checkbox_performance,   0, 5, 1, 1)
        grid.attach(checkbox_hdr,           0, 6, 1, 1)
        grid.attach(label_present,          0, 7, 1, 1)
        grid.attach(combobox_present,       0, 8, 1, 1)

        frame.add(grid)

        button_cancel = Gtk.Button(label=_("Cancel"))
        button_cancel.set_size_request(150, -1)
        button_cancel.set_hexpand(True)
        button_cancel.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.CANCEL))

        button_ok = Gtk.Button(label=_("Ok"))
        button_ok.set_size_request(150, -1)
        button_ok.set_hexpand(True)
        button_ok.connect("clicked", lambda b: dialog.response(Gtk.ResponseType.OK))

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)
        bottom_box.pack_start(button_cancel, True, True, 0)
        bottom_box.pack_start(button_ok, True, True, 0)

        content_area = dialog.get_content_area()
        content_area.pack_start(frame, True, True, 0)
        content_area.pack_start(bottom_box, False, False, 0)

        dialog.show_all()
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.lossless_enabled = checkbox_enable.get_active()
            self.lossless_multiplier = spin_multiplier.get_value_as_int()
            self.lossless_flow = scale_flow.get_value()
            self.lossless_performance = checkbox_performance.get_active()
            self.lossless_hdr = checkbox_hdr.get_active()

            present = combobox_present.get_active_text()

            mapping = {
                "VSync/FIFO (default)": "fifo",
                "Mailbox": "mailbox",
                "Immediate": "immediate",
            }

            self.lossless_present = mapping.get(present, "fifo")

        dialog.destroy()
        return response

    def on_button_search_addapp_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select an additional application"),
            action=Gtk.FileChooserAction.OPEN,
            accept_label=_("Open"),
            cancel_label=_("Cancel"),
        )

        add_windows_file_filters(filechooser)

        response = filechooser.run()

        if response == Gtk.ResponseType.ACCEPT:
            selected_file = filechooser.get_filename()
            if selected_file:
                self.entry_addapp.set_text(selected_file)

        filechooser.destroy()

    def load_config(self):
        cfg = ConfigManager()

        mangohud = cfg.config.get('mangohud', 'False') == 'True'
        gamemode = cfg.config.get('gamemode', 'False') == 'True'
        disable_hidraw = cfg.config.get('disable-hidraw', 'False') == 'True'
        prevent_sleep = cfg.config.get('prevent-sleep', 'False') == 'True'
        self.default_runner = cfg.config.get('default-runner', '').strip('"')
        self.lossless_location = cfg.config.get('lossless-location', '')

        self.checkbox_mangohud.set_active(mangohud)
        self.checkbox_gamemode.set_active(gamemode)
        self.checkbox_disable_hidraw.set_active(disable_hidraw)
        self.checkbox_prevent_sleep.set_active(prevent_sleep)

    def on_cancel_clicked(self, widget):
        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.destroy()

    def on_ok_clicked(self, widget):

        validation_result = self.validate_fields()
        if not validation_result:
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        title_formatted = format_title(title)

        addapp_bat = f"{os.path.dirname(self.file_path)}/faugus-{title_formatted}.bat"
        game_arguments = self.entry_game_arguments.get_text()

        if self.addapp_enabled:
            write_addapp_bat(addapp_bat, self.file_path, self.addapp, self.addapp_delay, self.addapp_first, game_arguments)

        if os.path.isfile(os.path.expanduser(self.icon_temp)):
            os.rename(os.path.expanduser(self.icon_temp), f'{self.icons_path}/{title_formatted}.ico')

        new_icon_path = f"{icons_dir}/{title_formatted}.ico"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        protonfix = self.entry_protonfix.get_text()

        raw_args = self.launch_arguments.split()
        env_vars = []
        other_args = []
        for arg in raw_args:
            if "=" in arg and not arg.startswith("-"):
                env_vars.append(arg)
            else:
                other_args.append(arg)

        launch_arguments = " ".join(env_vars + other_args)

        game_arguments = self.entry_game_arguments.get_text()
        lossless_enabled = self.lossless_enabled
        lossless_multiplier = self.lossless_multiplier
        lossless_flow = self.lossless_flow
        lossless_performance = self.lossless_performance
        lossless_hdr = self.lossless_hdr
        lossless_present = self.lossless_present

        mangohud = True if self.checkbox_mangohud.get_active() else ""
        gamemode = True if self.checkbox_gamemode.get_active() else ""
        disable_hidraw = True if self.checkbox_disable_hidraw.get_active() else ""
        prevent_sleep = True if self.checkbox_prevent_sleep.get_active() else ""

        game_directory = os.path.dirname(self.file_path)

        command_parts = []

        if disable_hidraw:
            command_parts.append("PROTON_DISABLE_HIDRAW=1")
        if prevent_sleep:
            command_parts.append("PREVENT_SLEEP=1")
        if protonfix:
            command_parts.append(f'GAMEID={protonfix}')
        if launch_arguments:
            command_parts.append(launch_arguments)
        command_parts.extend(build_lossless_env(lossless_enabled, lossless_multiplier, lossless_flow, lossless_performance, lossless_hdr, lossless_present))
        if gamemode:
            command_parts.append("gamemoderun")
        if mangohud:
            command_parts.append("mangohud")

        command_parts.append(f"'{umu_run}'")

        if self.addapp_enabled:
            escaped_addapp_bat = addapp_bat.replace("'", "'\\''")
            command_parts.append(f"'{escaped_addapp_bat}'")
        elif self.file_path:
            escaped_file_path = self.file_path.replace("'", "'\\''")
            command_parts.append(f"'{escaped_file_path}'")

        if game_arguments:
            command_parts.append(f"{game_arguments}")

        command = ' '.join(command_parts)

        if IS_FLATPAK:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={title}\n'
                f'Exec=flatpak run --command={launcher_path} io.github.Faugus.faugus-launcher --run "{command}"\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )
        else:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={title}\n'
                f'Exec={launcher_path} --run "{command}"\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )

        applications_directory = app_dir
        if not os.path.exists(applications_directory):
            os.makedirs(applications_directory)

        desktop_directory = desktop_dir
        if not os.path.exists(desktop_directory):
            os.makedirs(desktop_directory)

        applications_shortcut_path = f"{app_dir}/{title_formatted}.desktop"

        with open(applications_shortcut_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        os.chmod(applications_shortcut_path, 0o755)

        desktop_shortcut_path = f"{desktop_dir}/{title_formatted}.desktop"
        shutil.copyfile(applications_shortcut_path, desktop_shortcut_path)
        os.chmod(desktop_shortcut_path, 0o755)

        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.destroy()

    def set_image_shortcut_icon(self):
        image_path = faugus_png

        pixbuf = GdkPixbuf.Pixbuf.new_from_file(image_path)
        scaled_pixbuf = pixbuf.scale_simple(50, 50, GdkPixbuf.InterpType.BILINEAR)

        image = Gtk.Image.new_from_pixbuf(scaled_pixbuf)
        return image

    def on_button_shortcut_icon_clicked(self, widget):
        self.set_sensitive(False)

        path = self.file_path

        if os.path.isfile(path):
            os.makedirs(self.icon_directory, exist_ok=True)
            status = extract_ico_simple(path, self.icon_converted)
            if status == "no_icons":
                self.button_shortcut_icon.set_image(self.set_image_shortcut_icon())

        filechooser = Gtk.FileChooserNative.new(
            _("Select an icon for the shortcut"),
            self,
            Gtk.FileChooserAction.OPEN,
            _("Open"),
            _("Cancel")
        )

        add_image_file_filters(filechooser)

        filechooser.set_current_folder(self.icon_directory)

        response = filechooser.run()
        if response == Gtk.ResponseType.ACCEPT:
            file_path = filechooser.get_filename()
            if not file_path or not is_valid_image(file_path):
                show_invalid_image_dialog()
            else:
                shutil.copyfile(file_path, self.icon_temp)
                surface = self.new_surface_from_image(self.icon_temp, 50, 50)
                image = Gtk.Image.new_from_surface(surface)
                self.button_shortcut_icon.set_image(image)

        filechooser.destroy()

        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        self.set_sensitive(True)

    def validate_fields(self):
        title = self.entry_title.get_text()
        self.entry_title.get_style_context().remove_class("entry")

        if not title:
            self.entry_title.get_style_context().add_class("entry")
            return False

        return True

def main():
    os.environ["GTK_USE_PORTAL"] = "1"
    apply_dark_theme()
    exec_path = sys.argv[1]

    win = CreateShortcut(exec_path)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
