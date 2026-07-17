import os
import shutil
import sys
import time
import calendar
import warnings
from datetime import datetime, timedelta
import gi

warnings.filterwarnings('ignore', category=DeprecationWarning)

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk
from faugus.language_config import *
from faugus.utils import on_entry_changed, load_red_entry_css, load_frame_css, hide_dialog_action_area, IdComboBox, new_file_chooser, destroy_and_release, set_file_chooser_start_folder, load_json_file, save_json_file, build_bottom_button_box


def load_config():
    return load_json_file(CONFIG_FILE_DIR, default={})


def save_config(config):
    save_json_file(config, CONFIG_FILE_DIR)


def perform_backup(dest_path):
    temp_dir = os.path.join(FAUGUS_TEMP, "temp-backup")
    os.makedirs(temp_dir, exist_ok=True)

    for item, src in BACKUP_ITEMS.items():
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
    zip_path = os.path.join(FAUGUS_TEMP, f"faugus-launcher-{current_date}")

    shutil.make_archive(zip_path, "zip", temp_dir)
    shutil.rmtree(temp_dir)

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path):
        os.remove(dest_path)

    shutil.move(zip_path + ".zip", dest_path)
    return current_date


def setup_autostart(enable):
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, "faugus-backup.desktop")

    if enable:
        os.makedirs(autostart_dir, exist_ok=True)
        with open(desktop_file, "w") as f:
            f.write("[Desktop Entry]\n")
            f.write("Type=Application\n")
            f.write("Name=Faugus Backup Service\n")
            f.write("Exec=python -m faugus.backup --daemon\n")
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


def daemon_mode():
    while True:
        try:
            config = load_config()
            if should_run_backup(config):
                dest_dir = config.get('backup-dest-dir', '')
                if not dest_dir:
                    dest_dir = os.path.expanduser("~")

                current_date = datetime.now().strftime("%Y-%m-%d")
                zip_filename = f"faugus-launcher-{current_date}.zip"
                dest_path = os.path.join(dest_dir, zip_filename)

                new_date = perform_backup(dest_path)
                config['backup-last-date'] = new_date
                save_config(config)
        except Exception:
            pass
        time.sleep(14400)


_ = setup_gettext('faugus-launcher')


class BackupWindow(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title=_("Backup Settings"), transient_for=parent)
        hide_dialog_action_area(self)
        self.set_modal(True)
        self.set_resizable(False)
        self.connect("response", lambda d, r: destroy_and_release(d))

        self.config = load_config()

        load_red_entry_css()
        load_frame_css()

        self.root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.get_content_area().append(self.root_box)

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
        self.frame.set_child(self.main_box)
        self.root_box.append(self.frame)

        self.label_path = Gtk.Label(label=_("Backup Destination"))
        self.label_path.set_halign(Gtk.Align.START)
        self.main_box.append(self.label_path)

        dest_dir = self.config.get('backup-dest-dir', '')
        if not dest_dir:
            dest_dir = os.path.expanduser(PathManager.user_home('Faugus Backup'))

        self.box_dest = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry_dest = Gtk.Entry()
        self.entry_dest.connect("changed", on_entry_changed)
        self.entry_dest.set_text(dest_dir)
        self.entry_dest.set_hexpand(True)
        self.entry_dest.set_tooltip_text(_("Backup destination path"))
        self.button_browse = Gtk.Button()
        self.button_browse.set_child(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.button_browse.connect("clicked", self.on_browse_clicked)
        self.button_browse.set_size_request(50, -1)
        self.box_dest.append(self.entry_dest)
        self.box_dest.append(self.button_browse)
        self.main_box.append(self.box_dest)

        self.button_manual = Gtk.Button(label=_("Backup now"))
        self.button_manual.set_margin_top(10)
        self.button_manual.connect("clicked", self.on_manual_clicked)
        self.main_box.append(self.button_manual)

        self.box_switch = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.checkbox_auto = Gtk.CheckButton(label=_("Automatic Backup"))
        self.checkbox_auto.set_margin_top(10)
        is_enabled = self.config.get('backup-auto-enabled', 'False') == 'True'
        self.checkbox_auto.set_active(is_enabled)
        self.checkbox_auto.connect("toggled", self.on_check_toggled)
        self.box_switch.append(self.checkbox_auto)
        self.main_box.append(self.box_switch)

        self.box_freq = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.radio_daily = Gtk.CheckButton(label=_("Daily"))
        self.radio_weekly = Gtk.CheckButton(label=_("Weekly"))
        self.radio_weekly.set_group(self.radio_daily)
        self.radio_monthly = Gtk.CheckButton(label=_("Monthly"))
        self.radio_monthly.set_group(self.radio_daily)

        self.box_freq.append(self.radio_daily)
        self.box_freq.append(self.radio_weekly)
        self.box_freq.append(self.radio_monthly)
        self.main_box.append(self.box_freq)

        self.box_weekly = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.combo_weekly = IdComboBox()
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
        self.combo_weekly.set_hexpand(True)
        self.box_weekly.append(self.combo_weekly)
        self.main_box.append(self.box_weekly)

        self.box_monthly = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        adj = Gtk.Adjustment(value=1, lower=1, upper=31, step_increment=1, page_increment=5, page_size=0)
        self.spin_monthly = Gtk.SpinButton(adjustment=adj, numeric=True)
        self.spin_monthly.set_hexpand(True)
        self.box_monthly.append(self.spin_monthly)
        self.main_box.append(self.box_monthly)

        last_date = self.config.get('backup-last-date')
        if not last_date or not last_date.strip():
            last_date = _("No backup yet")
        self.label_last_backup = Gtk.Label(label=f"{_('Last backup:')} {last_date}")
        self.label_last_backup.set_margin_top(10)
        self.main_box.append(self.label_last_backup)

        self.label_warning = Gtk.Label(label=_("Prefixes and Protons will not be backed up!"))
        self.label_warning.set_markup(f'<span color="red">{_("Prefixes and Protons will not be backed up!")}</span>')
        self.main_box.append(self.label_warning)

        self.button_cancel = Gtk.Button(label=_("Cancel"))
        self.button_cancel.set_hexpand(True)
        self.button_cancel.connect("clicked", self.on_cancel_clicked)

        self.button_ok = Gtk.Button(label=_("Ok"))
        self.button_ok.set_hexpand(True)
        self.button_ok.connect("clicked", self.on_ok_clicked)

        self.bottom_box = build_bottom_button_box(self.button_cancel, self.button_ok)

        self.root_box.append(self.bottom_box)

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

    def on_check_toggled(self, widget):
        self.update_ui_state()

    def on_freq_toggled(self, widget):
        self.update_ui_state()

    def update_ui_state(self):
        is_active = self.checkbox_auto.get_active()

        self.radio_daily.set_sensitive(is_active)
        self.radio_weekly.set_sensitive(is_active)
        self.radio_monthly.set_sensitive(is_active)

        self.combo_weekly.set_sensitive(is_active)
        self.spin_monthly.set_sensitive(is_active)

        self.box_weekly.set_visible(is_active and self.radio_weekly.get_active())
        self.box_monthly.set_visible(is_active and self.radio_monthly.get_active())

    def on_browse_clicked(self, widget):
        filechooser = new_file_chooser(
            self,
            _("Select the backup destination"),
            Gtk.FileChooserAction.SELECT_FOLDER,
        )
        entry_value = self.entry_dest.get_text()
        set_file_chooser_start_folder(filechooser, "backup_destination", entry_value or None)

        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                self.entry_dest.set_text(dialog.get_file().get_path())
            destroy_and_release(dialog)

        filechooser.connect("response", on_response)
        filechooser.present()

    def on_manual_clicked(self, widget):
        if not self.entry_dest.get_text():
            self.entry_dest.add_css_class("entry")
            return
        dest_dir = self.entry_dest.get_text()
        if not dest_dir:
            dest_dir = os.path.expanduser("~")

        current_date = datetime.now().strftime("%Y-%m-%d")
        zip_filename = f"faugus-launcher-{current_date}.zip"
        dest_path = os.path.join(dest_dir, zip_filename)

        try:
            new_date = perform_backup(dest_path)
            self.config['backup-last-date'] = new_date
            save_config(self.config)
            self.label_last_backup.set_text(f"{_('Last backup:')} {new_date}")
        except Exception:
            pass

    def on_cancel_clicked(self, widget):
        destroy_and_release(self)

    def on_ok_clicked(self, widget):
        self.config['backup-auto-enabled'] = str(self.checkbox_auto.get_active())

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
        save_config(self.config)

        setup_autostart(self.checkbox_auto.get_active())

        if self.checkbox_auto.get_active() and should_run_backup(self.config):
            try:
                dest_dir = self.config.get('backup-dest-dir', '')
                if not dest_dir:
                    dest_dir = os.path.expanduser("~")
                current_date = datetime.now().strftime("%Y-%m-%d")
                zip_filename = f"faugus-launcher-{current_date}.zip"
                dest_path = os.path.join(dest_dir, zip_filename)

                new_date = perform_backup(dest_path)
                self.config['backup-last-date'] = new_date
                save_config(self.config)
            except Exception:
                pass

        destroy_and_release(self)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        daemon_mode()
