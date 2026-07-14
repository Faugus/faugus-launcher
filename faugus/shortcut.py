

import sys
import warnings
import gi
import shutil

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib
from faugus.utils import *
from faugus.config_manager import *
from faugus.steam_setup import lossless_dll
from faugus.migration import fix_legacy_shortcut_icons

if IS_FLATPAK:
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
else:
    GLib.set_prgname("faugus-launcher")

_ = setup_gettext('faugus-launcher')


class CreateShortcut(Gtk.ApplicationWindow, HiDpiMixin):
    def __init__(self, file_path):
        super().__init__(title="Faugus")
        self.file_path = file_path
        self.set_resizable(False)

        game_title = os.path.basename(file_path)
        self.set_title(game_title)
        print(self.file_path)

        self.icon_directory = f"{shortcut_icons_dir}/icon_temp/"

        self.icons_path = shortcut_icons_dir
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.png'

        init_addon_defaults(self)

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
        self.button_search_protonfix.set_child(
            Gtk.Image.new_from_icon_name("system-search-symbolic"))
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

        create_mangohud_gamemode_checkboxes(self)
        self.checkbox_disable_hidraw = Gtk.CheckButton(label=_("Disable Hidraw"))
        self.checkbox_disable_hidraw.set_tooltip_text(
            _("May fix controller issues with some games. Only works with GE-Proton10 or Proton-EM-10."))
        self.checkbox_prevent_sleep = Gtk.CheckButton(label=_("Prevent Sleep"))

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.connect("clicked", self.on_cancel_clicked)
        self.button_cancel.set_hexpand(True)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.connect("clicked", self.on_ok_clicked)
        self.button_ok.set_hexpand(True)

        load_red_entry_css()
        load_frame_css()

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

        self.grid_tools = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.grid_tools.set_margin_start(10)
        self.grid_tools.set_margin_end(10)
        self.grid_tools.set_margin_top(10)
        self.grid_tools.set_margin_bottom(10)

        self.grid_shortcut_icon = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.grid_shortcut_icon.set_margin_start(10)
        self.grid_shortcut_icon.set_margin_end(10)
        self.grid_shortcut_icon.set_margin_top(10)
        self.grid_shortcut_icon.set_margin_bottom(10)

        self.grid_tools.append(self.checkbox_mangohud)
        self.grid_tools.append(self.checkbox_gamemode)
        self.grid_tools.append(self.checkbox_prevent_sleep)
        self.grid_tools.append(self.checkbox_disable_hidraw)

        self.grid_shortcut_icon.append(self.button_shortcut_icon)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)
        self.grid_shortcut_icon.set_halign(Gtk.Align.END)
        self.grid_shortcut_icon.set_hexpand(True)

        self.box_tools = Gtk.Box()
        self.box_tools.append(self.grid_tools)
        self.box_tools.append(self.grid_shortcut_icon)

        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bottom_box.set_homogeneous(True)
        bottom_box.set_margin_start(10)
        bottom_box.set_margin_end(10)
        bottom_box.set_margin_bottom(10)

        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)

        bottom_box.append(self.button_cancel)
        bottom_box.append(self.button_ok)

        self.main_grid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.main_grid.append(self.grid_title)
        self.main_grid.append(self.grid_protonfix)
        self.main_grid.append(self.grid_game_arguments)
        self.main_grid.append(self.grid_launch_arguments)
        self.main_grid.append(self.grid_addapp)
        self.main_grid.append(self.grid_lossless)
        self.main_grid.append(self.box_tools)

        self.load_config()

        disable_mangohud_gamemode_if_missing(self)

        if os.path.exists(lsfgvk_path):
            if lossless_dll or os.path.exists(self.lossless_location):
                self.button_lossless.set_sensitive(True)
            else:
                self.button_lossless.set_sensitive(False)
                self.button_lossless.set_tooltip_text(_("Lossless.dll NOT FOUND. If it's installed, go to Faugus's settings and set the location."))
        else:
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Lossless Scaling Vulkan Layer NOT INSTALLED."))

        frame.set_child(self.main_grid)
        self.box.append(frame)
        self.box.append(bottom_box)
        self.set_child(self.box)

        os.makedirs(self.icon_directory, exist_ok=True)

        status = extract_ico(self.file_path, self.icon_temp, best_frame=True)
        if status == "ok":
            texture = self.new_texture_from_image(self.icon_temp, 50, 50)
            self.button_shortcut_icon.set_child(new_picture(texture))
        elif status == "no_icons":
            self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

        shutil.rmtree(self.icon_directory, ignore_errors=True)

    def on_button_launch_arguments_clicked(self, widget):
        def on_result(result):
            self.launch_arguments = result
        show_launch_arguments_dialog(self, self.launch_arguments, on_result)

    def on_button_addapp_clicked(self, widget):
        def on_result(result):
            (self.addapp_enabled, self.addapp,
             self.addapp_delay, self.addapp_first) = result
        show_addapp_dialog(
            self, self.addapp_enabled, self.addapp,
            self.addapp_delay, self.addapp_first, on_result)

    def on_button_lossless_clicked(self, widget):
        def on_result(result):
            (self.lossless_enabled, self.lossless_multiplier,
             self.lossless_flow, self.lossless_performance,
             self.lossless_hdr, self.lossless_present) = result
        show_lossless_dialog(
            self, self.lossless_enabled, self.lossless_multiplier,
            self.lossless_flow, self.lossless_performance,
            self.lossless_hdr, self.lossless_present, on_result)

    def load_config(self):
        cfg = ConfigManager()

        mangohud = cfg.config.get('mangohud', 'False') == 'True'
        gamemode = cfg.config.get('gamemode', 'False') == 'True'
        disable_hidraw = cfg.config.get('disable-hidraw', 'False') == 'True'
        prevent_sleep = cfg.config.get('prevent-sleep', 'False') == 'True'
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

        if not self.validate_fields():
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        title_formatted = format_title(title)

        addapp_bat = f"{os.path.dirname(self.file_path)}/faugus-{title_formatted}.bat"
        game_arguments = self.entry_game_arguments.get_text()

        if self.addapp_enabled:
            write_addapp_bat(addapp_bat, self.file_path, self.addapp, self.addapp_delay, self.addapp_first, game_arguments)

        if os.path.isfile(os.path.expanduser(self.icon_temp)):
            os.rename(os.path.expanduser(self.icon_temp), f'{self.icons_path}/{title_formatted}.png')

        new_icon_path = f"{shortcut_icons_dir}/{title_formatted}.png"
        if not os.path.exists(new_icon_path):
            new_icon_path = faugus_png

        protonfix = self.entry_protonfix.get_text()

        env_vars = []
        other_args = []
        for arg in self.launch_arguments.split():
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

        os.makedirs(app_dir, exist_ok=True)
        os.makedirs(desktop_dir, exist_ok=True)

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
        texture = self.new_texture_from_image(faugus_png_raster, 50, 50)
        return new_picture(texture)

    def on_button_shortcut_icon_clicked(self, widget):
        self.set_sensitive(False)

        path = self.file_path

        if os.path.isfile(path):
            os.makedirs(self.icon_directory, exist_ok=True)
            status = extract_ico(path, self.icon_converted, best_frame=False)
            if status == "no_icons":
                self.button_shortcut_icon.set_child(self.set_image_shortcut_icon())

        choose_shortcut_icon(self)
        self.set_sensitive(True)

    def validate_fields(self):
        title = self.entry_title.get_text()
        self.entry_title.remove_css_class("entry")

        if not title:
            self.entry_title.add_css_class("entry")
            return False

        return True


def main():
    suppress_adwaita_theme_warning()
    fix_legacy_shortcut_icons()

    exec_path = sys.argv[1]

    cfg = ConfigManager()
    apply_interface_customization(
        cfg.config.get('interface-theme', 'system'),
        cfg.config.get('accent-color', 'system'),
    )

    app = Gtk.Application(application_id="io.github.Faugus.faugus-launcher")

    def on_activate(app):
        win = CreateShortcut(exec_path)
        win.set_application(app)
        win.connect("destroy", lambda *a: app.quit())
        win.present()

    app.connect("activate", on_activate)
    app.run(None)


if __name__ == "__main__":
    main()
