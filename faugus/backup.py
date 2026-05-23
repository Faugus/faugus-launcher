import os
import shutil
import sys
import time
import calendar
import gettext
from datetime import datetime, timedelta
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
from faugus.language_config import *

def load_config(faugus_dir):
    config = {}
    config_path = os.path.join(faugus_dir, "config.ini")
    if os.path.isfile(config_path):
        with open(config_path, 'r') as f:
            for line in f.read().splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip().strip('"')
    return config

def save_config(faugus_dir, config):
    config_path = os.path.join(faugus_dir, "config.ini")
    with open(config_path, 'w') as f:
        for key, value in config.items():
            if key in ['default-prefix', 'default-runner']:
                f.write(f'{key}="{value}"\n')
            else:
                f.write(f'{key}={value}\n')

def perform_backup(faugus_dir, dest_path):
    items = ["banners", "games-backup", "icons", "config.ini", "envar.txt", "games.json", "latest-games.txt"]
    temp_dir = os.path.join(faugus_dir, "temp-backup")
    os.makedirs(temp_dir, exist_ok=True)

    for item in items:
        src = os.path.join(faugus_dir, item)
        dst = os.path.join(temp_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif os.path.isfile(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

    marker_path = os.path.join(temp_dir, ".faugus_marker")
    with open(marker_path, "w") as f:
        f.write("faugus-launcher-backup")

    current_date = datetime.now().strftime("%Y-%m-%d")
    zip_path = os.path.join(faugus_dir, f"faugus-launcher-{current_date}")

    shutil.make_archive(zip_path, "zip", temp_dir)
    shutil.rmtree(temp_dir)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path):
        os.remove(dest_path)

    shutil.move(zip_path + ".zip", dest_path)
    return current_date

def setup_autostart(enable, script_path, faugus_dir):
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, "faugus-backup.desktop")

    if enable:
        os.makedirs(autostart_dir, exist_ok=True)
        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            f.write("Type=Application\n")
            f.write("Name=Faugus Backup Service\n")
            f.write(f"Exec=python -m faugus.backup --daemon {faugus_dir}\n")
            f.write("Hidden=false\n")
            f.write("NoDisplay=false\n")
            f.write("X-GNOME-Autostart-enabled=true\n")
    else:
        if os.path.exists(desktop_file):
            os.remove(desktop_file)

def get_last_monthly_target(today, target_day):
    def safe_replace(date_obj, day):
        try:
            return date_obj.replace(day=day)
        except ValueError:
            last_day = calendar.monthrange(date_obj.year, date_obj.month)[1]
            return date_obj.replace(day=last_day)

    current_month_target = safe_replace(today, target_day)
    if today >= current_month_target:
        return current_month_target

    first_day_current_month = today.replace(day=1)
    last_day_prev_month = first_day_current_month - timedelta(days=1)
    return safe_replace(last_day_prev_month, target_day)

def should_run_backup(config):
    if config.get('backup-auto-enabled', 'False') != 'True':
        return False

    last_backup_str = config.get('backup-last-date', '2000-01-01')
    if not last_backup_str or last_backup_str.strip() == "":
        last_backup_str = '2000-01-01'

    try:
        last_backup = datetime.strptime(last_backup_str, "%Y-%m-%d").date()
    except ValueError:
        last_backup = datetime(2000, 1, 1).date()

    today = datetime.today().date()
    if today <= last_backup:
        return False

    freq = config.get('backup-frequency', 'daily')
    target_day = int(config.get('backup-target-day', '0'))

    if freq == 'daily':
        return True
    elif freq == 'weekly':
        today_dow = today.weekday()
        days_ago = (today_dow - target_day) % 7
        last_target_date = today - timedelta(days=days_ago)
        return last_backup < last_target_date
    elif freq == 'monthly':
        last_target_date = get_last_monthly_target(today, target_day)
        return last_backup < last_target_date

    return False

def daemon_mode(faugus_dir):
    while True:
        try:
            config = load_config(faugus_dir)
            if should_run_backup(config):
                dest_dir = config.get('backup-dest-dir', '')
                if not dest_dir:
                    dest_dir = os.path.expanduser("~")

                current_date = datetime.now().strftime("%Y-%m-%d")
                zip_filename = f"faugus-launcher-{current_date}.zip"
                dest_path = os.path.join(dest_dir, zip_filename)

                new_date = perform_backup(faugus_dir, dest_path)
                config['backup-last-date'] = new_date
                save_config(faugus_dir, config)
        except Exception:
            pass
        time.sleep(14400)

try:
    translation = gettext.translation('faugus-launcher', localedir=LOCALE_DIR, languages=[lang])
    translation.install()
    _ = translation.gettext
except FileNotFoundError:
    gettext.install('faugus-launcher', localedir=LOCALE_DIR)
    _ = gettext.gettext

class BackupWindow(Gtk.Dialog):
    def __init__(self, parent, faugus_dir):
        super().__init__(title=_("Backup Settings"), transient_for=parent)
        self.set_modal(True)
        self.set_resizable(False)

        self.faugus_dir = faugus_dir
        self.config = load_config(self.faugus_dir)

        css_provider = Gtk.CssProvider()
        css = """
        .entry {
            border-color: Red;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css_provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)

        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.get_content_area().pack_start(self.root_box, True, True, 0)

        self.frame = Gtk.Frame()
        self.frame.set_margin_start(10)
        self.frame.set_margin_end(10)
        self.frame.set_margin_top(10)
        self.frame.set_margin_bottom(10)

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_bottom(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.frame.add(self.main_box)
        self.root_box.pack_start(self.frame, True, True, 0)

        self.lbl_path = Gtk.Label(label=_("Backup Destination"))
        self.lbl_path.set_halign(Gtk.Align.START)
        self.main_box.pack_start(self.lbl_path, False, False, 0)

        dest_dir = self.config.get('backup-dest-dir', '')
        if not dest_dir:
            dest_dir = os.path.expanduser(PathManager.user_home('Faugus Backup'))

        self.box_dest = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry_dest = Gtk.Entry()
        self.entry_dest.connect("changed", self.on_entry_changed, self.entry_dest)
        self.entry_dest.set_text(dest_dir)
        self.entry_dest.set_hexpand(True)
        self.btn_browse = Gtk.Button()
        self.btn_browse.set_image(Gtk.Image.new_from_icon_name("system-search-symbolic", Gtk.IconSize.BUTTON))
        self.btn_browse.connect("clicked", self.on_browse_clicked)
        self.btn_browse.set_size_request(50, -1)
        self.box_dest.pack_start(self.entry_dest, True, True, 0)
        self.box_dest.pack_start(self.btn_browse, False, False, 0)
        self.main_box.pack_start(self.box_dest, False, False, 0)

        self.btn_manual = Gtk.Button(label=_("Backup now"))
        self.btn_manual.set_margin_top(10)
        self.btn_manual.connect("clicked", self.on_manual_clicked)
        self.main_box.pack_start(self.btn_manual, False, False, 0)

        self.box_switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.check_auto = Gtk.CheckButton(label=_("Automatic Backups"))
        self.check_auto.set_margin_top(10)
        is_enabled = self.config.get('backup-auto-enabled', 'False') == 'True'
        self.check_auto.set_active(is_enabled)
        self.check_auto.connect("toggled", self.on_check_toggled)
        self.box_switch.pack_start(self.check_auto, False, False, 0)
        self.main_box.pack_start(self.box_switch, False, False, 0)

        self.box_freq = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.radio_daily = Gtk.RadioButton.new_with_label_from_widget(None, _("Daily"))
        self.radio_weekly = Gtk.RadioButton.new_with_label_from_widget(self.radio_daily, _("Weekly"))
        self.radio_monthly = Gtk.RadioButton.new_with_label_from_widget(self.radio_daily, _("Monthly"))

        self.box_freq.pack_start(self.radio_daily, False, False, 0)
        self.box_freq.pack_start(self.radio_weekly, False, False, 0)
        self.box_freq.pack_start(self.radio_monthly, False, False, 0)
        self.main_box.pack_start(self.box_freq, False, False, 0)

        self.box_weekly = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_weekly.set_no_show_all(True)

        self.combo_weekly = Gtk.ComboBoxText()
        self.combo_weekly.set_tooltip_text(_("Day of the week"))
        days = [
            ("Monday", _("Monday")),
            ("Tuesday", _("Tuesday")),
            ("Wednesday", _("Wednesday")),
            ("Thursday", _("Thursday")),
            ("Friday", _("Friday")),
            ("Saturday", _("Saturday")),
            ("Sunday", _("Sunday"))
        ]
        for day_id, day_name in days:
            self.combo_weekly.append(day_id, day_name)
        self.combo_weekly.set_active(0)
        self.combo_weekly.show()
        self.combo_weekly.set_hexpand(True)
        self.box_weekly.pack_start(self.combo_weekly, False, True, 0)
        self.main_box.pack_start(self.box_weekly, False, False, 0)

        self.box_monthly = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.box_monthly.set_no_show_all(True)

        adj = Gtk.Adjustment(value=1, lower=1, upper=31, step_increment=1, page_increment=5, page_size=0)
        self.spin_monthly = Gtk.SpinButton(adjustment=adj, numeric=True)
        self.spin_monthly.set_tooltip_text(_("Day of the month"))
        self.spin_monthly.show()
        self.spin_monthly.set_hexpand(True)
        self.box_monthly.pack_start(self.spin_monthly, False, True, 0)
        self.main_box.pack_start(self.box_monthly, False, False, 0)

        last_date = self.config.get('backup-last-date')
        if not last_date or not last_date.strip():
            last_date = _("No backup yet")
        self.lbl_last_backup = Gtk.Label(label=f"{_('Last backup:')} {last_date}")
        self.lbl_last_backup.set_margin_top(10)
        self.main_box.pack_start(self.lbl_last_backup, False, False, 0)

        self.lbl_warning = Gtk.Label(label=_("Prefixes and Protons will not be backed up!"))
        self.lbl_warning.set_markup(f'<span color="red">{_("Prefixes and Protons will not be backed up!")}</span>')
        self.main_box.pack_start(self.lbl_warning, False, False, 0)

        self.btn_cancel = Gtk.Button(label=_("Cancel"))
        self.btn_cancel.set_size_request(100, -1)
        self.btn_cancel.set_hexpand(True)
        self.btn_cancel.connect("clicked", self.on_cancel_clicked)

        self.btn_ok = Gtk.Button(label=_("Ok"))
        self.btn_ok.set_size_request(100, -1)
        self.btn_ok.set_hexpand(True)
        self.btn_ok.connect("clicked", self.on_ok_clicked)

        self.bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.bottom_box.set_margin_start(10)
        self.bottom_box.set_margin_end(10)
        self.bottom_box.set_margin_bottom(10)
        self.bottom_box.pack_start(self.btn_cancel, True, True, 0)
        self.bottom_box.pack_start(self.btn_ok, True, True, 0)

        self.root_box.pack_start(self.bottom_box, False, False, 0)

        freq_val = self.config.get('backup-frequency', 'daily')
        if freq_val == 'weekly':
            self.radio_weekly.set_active(True)
        elif freq_val == 'monthly':
            self.radio_monthly.set_active(True)
        else:
            self.radio_daily.set_active(True)

        target_day = int(self.config.get('backup-target-day', '0'))
        if freq_val == 'weekly' and 0 <= target_day < 7:
            self.combo_weekly.set_active(target_day)
        elif freq_val == 'monthly' and 1 <= target_day <= 31:
            self.spin_monthly.set_value(target_day)

        self.radio_daily.connect("toggled", self.on_freq_toggled)
        self.radio_weekly.connect("toggled", self.on_freq_toggled)
        self.radio_monthly.connect("toggled", self.on_freq_toggled)

        self.update_ui_state()
        self.show_all()

    def on_entry_changed(self, widget, entry):
        if entry.get_text():
            entry.get_style_context().remove_class("entry")

    def on_check_toggled(self, widget):
        self.update_ui_state()

    def on_freq_toggled(self, widget):
        self.update_ui_state()

    def update_ui_state(self):
        is_active = self.check_auto.get_active()

        self.radio_daily.set_sensitive(is_active)
        self.radio_weekly.set_sensitive(is_active)
        self.radio_monthly.set_sensitive(is_active)

        self.combo_weekly.set_sensitive(is_active)
        self.spin_monthly.set_sensitive(is_active)

        self.box_weekly.set_visible(is_active and self.radio_weekly.get_active())
        self.box_monthly.set_visible(is_active and self.radio_monthly.get_active())

    def on_browse_clicked(self, widget):
        filechooser = Gtk.FileChooserNative(
            title=_("Select the backup destination"),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            accept_label=_("Open"),
            cancel_label=_("Cancel")
        )
        filechooser.set_transient_for(self)
        response = filechooser.run()
        if response == Gtk.ResponseType.ACCEPT:
            self.entry_dest.set_text(filechooser.get_filename())
        filechooser.destroy()

    def on_manual_clicked(self, widget):
        if not self.entry_dest.get_text():
            self.entry_dest.get_style_context().add_class("entry")
            return
        dest_dir = self.entry_dest.get_text()
        if not dest_dir:
            dest_dir = os.path.expanduser("~")

        current_date = datetime.now().strftime("%Y-%m-%d")
        zip_filename = f"faugus-launcher-{current_date}.zip"
        dest_path = os.path.join(dest_dir, zip_filename)

        try:
            new_date = perform_backup(self.faugus_dir, dest_path)
            self.config['backup-last-date'] = new_date
            save_config(self.faugus_dir, self.config)
            self.lbl_last_backup.set_text(f"{_('Last backup:')} {new_date}")
        except Exception:
            pass

    def on_cancel_clicked(self, widget):
        self.destroy()

    def on_ok_clicked(self, widget):
        self.config['backup-auto-enabled'] = str(self.check_auto.get_active())

        if self.radio_daily.get_active():
            self.config['backup-frequency'] = 'daily'
            self.config['backup-target-day'] = '0'
        elif self.radio_weekly.get_active():
            self.config['backup-frequency'] = 'weekly'
            self.config['backup-target-day'] = str(self.combo_weekly.get_active())
        elif self.radio_monthly.get_active():
            self.config['backup-frequency'] = 'monthly'
            self.config['backup-target-day'] = str(int(self.spin_monthly.get_value()))

        self.config['backup-dest-dir'] = self.entry_dest.get_text()
        save_config(self.faugus_dir, self.config)

        script_path = os.path.abspath(__file__)
        setup_autostart(self.check_auto.get_active(), script_path, self.faugus_dir)

        if self.check_auto.get_active() and should_run_backup(self.config):
            try:
                dest_dir = self.config.get('backup-dest-dir', '')
                if not dest_dir:
                    dest_dir = os.path.expanduser("~")
                current_date = datetime.now().strftime("%Y-%m-%d")
                zip_filename = f"faugus-launcher-{current_date}.zip"
                dest_path = os.path.join(dest_dir, zip_filename)

                new_date = perform_backup(self.faugus_dir, dest_path)
                self.config['backup-last-date'] = new_date
                save_config(self.faugus_dir, self.config)
            except Exception:
                pass

        self.destroy()

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--daemon":
        daemon_mode(sys.argv[2])
