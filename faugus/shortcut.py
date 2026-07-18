

import sys
import warnings
import gi
import shutil

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib
from faugus.utils import *
from faugus.config_manager import *
from faugus.migration import fix_legacy_shortcut_icons

if IS_FLATPAK:
    GLib.set_prgname("io.github.Faugus.faugus-launcher")
else:
    GLib.set_prgname("faugus-launcher")

_ = setup_gettext('faugus-launcher')


class CreateShortcut(Gtk.ApplicationWindow, HiDpiMixin):
    def __init__(self, file_path):
        super().__init__(title="Faugus")
        self.file_path = expand_path(file_path)
        self.set_resizable(False)

        game_title = os.path.basename(file_path)
        self.set_title(game_title)
        print(self.file_path)

        self.icon_directory = f"{SHORTCUT_ICONS_DIR}/icon_temp/"

        self.icons_path = SHORTCUT_ICONS_DIR
        self.icon_converted = os.path.expanduser(f'{self.icons_path}/icon_temp/icon.png')
        self.icon_temp = f'{self.icons_path}/icon_temp.png'

        init_addon_defaults(self)

        self.label_title = Gtk.Label(label=_("Title"))
        self.label_title.set_halign(Gtk.Align.START)
        self.entry_title = Gtk.Entry()
        self.entry_title.connect("changed", on_entry_changed)

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
        self.entry_game_arguments.set_tooltip_text(_("-d3d11 -fullscreen"))

        self.button_launch_settings = Gtk.Button(label=_("Launch Settings"))
        self.button_launch_settings.connect("clicked", self.on_button_launch_settings_clicked)

        self.button_addapp = Gtk.Button(label=_("Additional Application"))
        self.button_addapp.connect("clicked", self.on_button_addapp_clicked)
        self.button_addapp.set_tooltip_text(
            _("Additional application to run with the game"))

        self.button_lossless = Gtk.Button(label=_("Lossless Scaling Frame Generation"))
        self.button_lossless.connect("clicked", self.on_button_lossless_clicked)

        self.button_shortcut_icon = Gtk.Button()
        self.button_shortcut_icon.set_size_request(120, -1)
        self.button_shortcut_icon.connect("clicked", self.on_button_shortcut_icon_clicked)

        create_mangohud_gamemode_checkboxes(self)
        self.checkbox_sdl = Gtk.CheckButton(label=_("SDL"))
        self.checkbox_sdl.set_tooltip_text(_("May fix gamepad issues with some games"))
        self.checkbox_no_sleep = Gtk.CheckButton(label=_("No Sleep"))

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

        self.grid_title = build_grid(margin_bottom=False)

        self.grid_protonfix = build_grid(margin_bottom=False)

        self.grid_launch_settings = build_grid(margin_bottom=False)

        self.grid_game_arguments = build_grid(margin_bottom=False)

        self.grid_lossless = build_grid(margin_bottom=False)

        self.grid_addapp = build_grid(margin_bottom=False)

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

        self.grid_launch_settings.attach(self.button_launch_settings, 0, 0, 1, 1)
        self.button_launch_settings.set_hexpand(True)

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
        self.grid_tools.append(self.checkbox_no_sleep)
        self.grid_tools.append(self.checkbox_sdl)

        self.grid_shortcut_icon.append(self.button_shortcut_icon)
        self.grid_shortcut_icon.set_valign(Gtk.Align.CENTER)
        self.grid_shortcut_icon.set_halign(Gtk.Align.END)
        self.grid_shortcut_icon.set_hexpand(True)

        self.box_tools = Gtk.Box()
        self.box_tools.append(self.grid_tools)
        self.box_tools.append(self.grid_shortcut_icon)

        self.button_cancel.set_hexpand(True)
        self.button_ok.set_hexpand(True)
        bottom_box = build_bottom_button_box(self.button_cancel, self.button_ok)

        self.box_main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.box_main.append(self.grid_title)
        self.box_main.append(self.grid_protonfix)
        self.box_main.append(self.grid_game_arguments)
        self.box_main.append(self.grid_launch_settings)
        self.box_main.append(self.grid_addapp)
        self.box_main.append(self.grid_lossless)
        self.box_main.append(self.box_tools)

        self.load_config()

        disable_mangohud_gamemode_if_missing(self)

        if os.path.exists(LSFGVK_PATH):
            self.button_lossless.set_sensitive(True)
        else:
            self.button_lossless.set_sensitive(False)
            self.button_lossless.set_tooltip_text(_("Vulkan Layer not found"))

        frame.set_child(self.box_main)
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

    def on_button_launch_settings_clicked(self, widget):
        def on_result(result, pre_launch, post_launch):
            self.launch_arguments = result
            self.pre_launch = pre_launch
            self.post_launch = post_launch
        show_launch_arguments_dialog(self, self.launch_arguments, self.pre_launch, self.post_launch, on_result)

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
        sdl_enabled = cfg.config.get('sdl-enabled', 'False') == 'True'
        no_sleep = cfg.config.get('no-sleep-enabled', 'False') == 'True'

        self.checkbox_mangohud.set_active(mangohud)
        self.checkbox_gamemode.set_active(gamemode)
        self.checkbox_sdl.set_active(sdl_enabled)
        self.checkbox_no_sleep.set_active(no_sleep)

    def on_cancel_clicked(self, widget):
        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        destroy_and_release(self)

    def on_ok_clicked(self, widget):

        if not self.validate_fields():
            self.set_sensitive(True)
            return

        title = self.entry_title.get_text()
        title_formatted = format_title(title)

        addapp_bat = f"{os.path.dirname(self.file_path)}/faugus-{title_formatted}.bat"
        game_arguments = expand_path(self.entry_game_arguments.get_text())

        if self.addapp_enabled:
            write_addapp_bat(addapp_bat, self.file_path, self.addapp, self.addapp_delay, self.addapp_first, game_arguments)

        if os.path.isfile(os.path.expanduser(self.icon_temp)):
            os.rename(os.path.expanduser(self.icon_temp), f'{self.icons_path}/{title_formatted}.png')

        new_icon_path = f"{SHORTCUT_ICONS_DIR}/{title_formatted}.png"
        if not os.path.exists(new_icon_path):
            new_icon_path = FAUGUS_PNG

        protonfix = self.entry_protonfix.get_text()

        env_vars = []
        other_args = []
        for arg in self.launch_arguments.split():
            if "=" in arg and not arg.startswith("-"):
                env_vars.append(arg)
            else:
                other_args.append(arg)

        launch_arguments = expand_path(" ".join(env_vars + other_args))

        game_arguments = expand_path(self.entry_game_arguments.get_text())
        lossless_enabled = self.lossless_enabled
        lossless_multiplier = self.lossless_multiplier
        lossless_flow = self.lossless_flow
        lossless_performance = self.lossless_performance
        lossless_hdr = self.lossless_hdr
        lossless_present = self.lossless_present

        mangohud = True if self.checkbox_mangohud.get_active() else ""
        gamemode = True if self.checkbox_gamemode.get_active() else ""
        sdl_enabled = True if self.checkbox_sdl.get_active() else ""
        no_sleep = True if self.checkbox_no_sleep.get_active() else ""

        game_directory = os.path.dirname(self.file_path)

        command_parts = []

        if sdl_enabled:
            command_parts.append("PROTON_PREFER_SDL=1")
        if no_sleep:
            command_parts.append("NO_SLEEP=1")
        if protonfix:
            command_parts.append(f'GAMEID={protonfix}')
        if launch_arguments:
            command_parts.append(launch_arguments)
        command_parts.extend(build_lossless_env(lossless_enabled, lossless_multiplier, lossless_flow, lossless_performance, lossless_hdr, lossless_present))
        if gamemode:
            command_parts.append("gamemoderun")
        if mangohud:
            command_parts.append("mangohud")

        command_parts.append(f"'{UMU_RUN}'")

        if self.addapp_enabled:
            escaped_addapp_bat = addapp_bat.replace("'", "'\\''")
            command_parts.append(f"'{escaped_addapp_bat}'")
        elif self.file_path:
            escaped_file_path = self.file_path.replace("'", "'\\''")
            command_parts.append(f"'{escaped_file_path}'")

        if game_arguments:
            command_parts.append(f"{game_arguments}")

        command = ' '.join(command_parts)

        hook_args = ""
        if self.pre_launch:
            hook_args += f' --pre-launch "{self.pre_launch}"'
        if self.post_launch:
            hook_args += f' --post-launch "{self.post_launch}"'

        if IS_FLATPAK:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={title}\n'
                f'Exec=flatpak run --command={LAUNCHER_PATH} io.github.Faugus.faugus-launcher {LAUNCHER_MODULE_ARGS}--run "{command}"{hook_args}\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )
        else:
            desktop_file_content = (
                f'[Desktop Entry]\n'
                f'Name={title}\n'
                f'Exec={LAUNCHER_PATH} {LAUNCHER_MODULE_ARGS}--run "{command}"{hook_args}\n'
                f'Icon={new_icon_path}\n'
                f'Type=Application\n'
                f'Categories=Game;\n'
                f'Path={game_directory}\n'
            )

        os.makedirs(APP_DIR, exist_ok=True)
        os.makedirs(DESKTOP_DIR, exist_ok=True)

        applications_shortcut_path = f"{APP_DIR}/{title_formatted}.desktop"

        with open(applications_shortcut_path, 'w') as desktop_file:
            desktop_file.write(desktop_file_content)

        os.chmod(applications_shortcut_path, 0o755)

        desktop_shortcut_path = f"{DESKTOP_DIR}/{title_formatted}.desktop"
        shutil.copyfile(applications_shortcut_path, desktop_shortcut_path)
        os.chmod(desktop_shortcut_path, 0o755)

        if os.path.isfile(self.icon_temp):
            os.remove(self.icon_temp)
        if os.path.isdir(self.icon_directory):
            shutil.rmtree(self.icon_directory)
        destroy_and_release(self)

    def set_image_shortcut_icon(self):
        texture = self.new_texture_from_image(FAUGUS_PNG_RASTER, 50, 50)
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
