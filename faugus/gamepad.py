import pygame
from gi.repository import GLib, Gtk
from faugus.keyboard import *

def get_button_map(joy):
    name = joy.get_name().lower()

    # PlayStation (DualShock / DualSense)
    if "playstation" in name or "dualshock" in name or "dualsense" in name or "ps4" in name:
        return {
            "confirm": 0,
            "back": 1,
            "square": 2,
            "triangle": 3,
            "lb": 9,
            "rb": 10,
            "start": 6,
            "start_alt": 4,
        }

    # Xbox / SDL
    return {
        "confirm": 0,
        "back": 1,
        "square": 2,
        "triangle": 3,
        "lb": 4,
        "rb": 5,
        "start": 7,
        "start_alt": 6,
    }

def init_gamepad(self):
    pygame.init()
    pygame.joystick.init()

    self.joystick = None

    self.axis_threshold = 0.7
    self.reset_threshold = 0.3

    self.can_move_x = True
    self.can_move_y = True

    GLib.timeout_add(50, lambda: poll_gamepad(self))

def poll_gamepad(self):
    events = pygame.event.get()
    active = any(w.is_active() for w in Gtk.Window.list_toplevels())

    for event in events:
        # --- HOTPLUG ---
        if event.type == pygame.JOYDEVICEADDED:
            self.joystick = pygame.joystick.Joystick(event.device_index)
            self.joystick.init()
            print(f"Gamepad connected: {self.joystick.get_name()}")

        elif event.type == pygame.JOYDEVICEREMOVED:
            print("Gamepad disconnected.")
            if self.joystick and self.joystick.get_instance_id() == event.instance_id:
                self.joystick.quit()
                self.joystick = None

        if not active:
            continue

        joy = self.joystick
        btn = get_button_map(joy) if joy else None

        # --- MENU ---
        if hasattr(self, "context_menu") and self.context_menu.get_visible():
            handle_menu_navigation(self, event, btn)
            continue

        # --- D-PAD ---
        if event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if y == 1:
                navigate_gamepad(Gtk.DirectionType.UP)
            elif y == -1:
                navigate_gamepad(Gtk.DirectionType.DOWN)
            if x == -1:
                navigate_gamepad(Gtk.DirectionType.LEFT)
            elif x == 1:
                navigate_gamepad(Gtk.DirectionType.RIGHT)

        # --- JOYSTICK ---
        elif event.type == pygame.JOYAXISMOTION:
            if event.axis == 1:
                if self.can_move_y:
                    if event.value < -self.axis_threshold:
                        navigate_gamepad(Gtk.DirectionType.UP)
                        self.can_move_y = False
                    elif event.value > self.axis_threshold:
                        navigate_gamepad(Gtk.DirectionType.DOWN)
                        self.can_move_y = False
                elif abs(event.value) < self.reset_threshold:
                    self.can_move_y = True

            elif event.axis == 0:
                if self.can_move_x:
                    if event.value < -self.axis_threshold:
                        navigate_gamepad(Gtk.DirectionType.LEFT)
                        self.can_move_x = False
                    elif event.value > self.axis_threshold:
                        navigate_gamepad(Gtk.DirectionType.RIGHT)
                        self.can_move_x = False
                elif abs(event.value) < self.reset_threshold:
                    self.can_move_x = True

        # --- BUTTONS ---
        elif event.type == pygame.JOYBUTTONDOWN and btn:
            win = get_active_window()
            is_dialog_active = isinstance(win, Gtk.Dialog)

            if event.button == btn["confirm"]:
                win = get_active_window()
                focused = win.get_focus() if win else None

                combo = find_combobox(focused)

                if combo:
                    model = combo.get_model()
                    if model:
                        count = model.iter_n_children(None)
                        current = combo.get_active()
                        combo.set_active((current + 1) % count if count >= 0 else 0)
                    continue

                activate_focused_widget(self)

            elif event.button == btn["back"]:
                if is_dialog_active:
                    win.response(Gtk.ResponseType.CANCEL)

            elif not is_dialog_active:
                if event.button == btn["square"]:
                    self.on_button_kill_clicked(None)

                elif event.button == btn["triangle"]:
                    focused = self.get_focus()
                    if isinstance(focused, Gtk.FlowBoxChild):
                        self.on_item_right_click(focused, None)
                        items = self.context_menu.get_children()
                        for i, item in enumerate(items):
                            if item == self.menu_play:
                                self.menu_index = i
                                self.context_menu.select_item(item)
                                break

                elif event.button == btn["lb"]:
                    self.on_button_add_clicked(None)

                elif event.button == btn["rb"]:
                    self.on_button_settings_clicked(None)

                elif event.button == btn["start"]:
                    self.on_button_bye_clicked(None)

    return True

def find_combobox(widget):
    while widget:
        if isinstance(widget, Gtk.ComboBox):
            return widget
        widget = widget.get_parent()
    return None

def handle_menu_navigation(self, event, btn=None):
    items = self.context_menu.get_children()
    if not items:
        return

    if not hasattr(self, "menu_index"):
        self.menu_index = 0

    def is_valid(item):
        return (
            isinstance(item, Gtk.MenuItem)
            and not isinstance(item, Gtk.SeparatorMenuItem)
            and item.get_sensitive()
        )

    def move(step):
        for _ in range(len(items)):
            self.menu_index = (self.menu_index + step) % len(items)
            if is_valid(items[self.menu_index]):
                break

    if event.type == pygame.JOYHATMOTION:
        x, y = event.value

        if y == -1:
            move(1)
        elif y == 1:
            move(-1)

        self.context_menu.select_item(items[self.menu_index])

    elif event.type == pygame.JOYBUTTONDOWN and btn:
        if event.button == btn["confirm"]:
            if is_valid(items[self.menu_index]):
                items[self.menu_index].activate()

        elif event.button == btn["back"]:
            self.context_menu.popdown()

def navigate_gamepad(direction):
    active_window = get_active_window()
    if active_window:
        active_window.child_focus(direction)

def activate_focused_widget(self):
    active_window = get_active_window()
    if not active_window:
        return

    focused = active_window.get_focus()
    if not focused:
        return

    if isinstance(focused, Gtk.Entry):
        parent = focused.get_toplevel()
        dialog = VirtualKeyboard(parent, focused)
        dialog.connect("destroy", lambda *a: parent.present())
        dialog.show_all()
        return

    if isinstance(focused, Gtk.Button):
        focused.emit("clicked")

    elif isinstance(focused, Gtk.CheckButton):
        focused.set_active(not focused.get_active())

    elif isinstance(focused, Gtk.FlowBoxChild):
        game = self.selected()
        if not game:
            return

        if game.gameid in self.running:
            self.running_dialog(game.title)
        else:
            self.on_button_play_clicked()

def get_active_window():
    for window in Gtk.Window.list_toplevels():
        if window.is_active():
            return window
    return None
