import pygame
from gi.repository import GLib, Gtk
from faugus.keyboard import VirtualKeyboard

def get_button_map(joy):
    name = joy.get_name().lower()

    if any(kw in name for kw in ("playstation", "dualshock", "dualsense", "ps4")):
        return {"confirm": 0, "back": 1, "square": 2, "triangle": 3, "lb": 9, "rb": 10, "start": 6, "start_alt": 4}

    return {"confirm": 0, "back": 1, "square": 2, "triangle": 3, "lb": 4, "rb": 5, "start": 7, "start_alt": 6}

def init_gamepad(self):
    pygame.init()
    pygame.joystick.init()

    self.joystick = None
    self.button_map = None

    self.axis_threshold = 0.7
    self.reset_threshold = 0.3
    self.can_move_x = True
    self.can_move_y = True

    GLib.timeout_add(50, lambda: poll_gamepad(self))

def poll_gamepad(self):
    for event in pygame.event.get():
        if event.type == pygame.JOYDEVICEADDED:
            self.joystick = pygame.joystick.Joystick(event.device_index)
            self.joystick.init()
            self.button_map = get_button_map(self.joystick)
            print(f"Gamepad conectado: {self.joystick.get_name()}")
            continue

        elif event.type == pygame.JOYDEVICEREMOVED:
            if self.joystick and self.joystick.get_instance_id() == event.instance_id:
                print("Gamepad desconectado.")
                self.joystick.quit()
                self.joystick = None
                self.button_map = None
            continue

        if not self.joystick or not self.button_map:
            continue

        if getattr(self, "context_menu", None) and self.context_menu.get_visible():
            handle_menu_navigation(self, event, self.button_map)
            continue

        if event.type == pygame.JOYHATMOTION:
            _handle_hat_motion(event.value)

        elif event.type == pygame.JOYAXISMOTION:
            _handle_axis_motion(self, event)

        elif event.type == pygame.JOYBUTTONDOWN:
            _handle_button_down(self, event.button)

    return True

def _handle_hat_motion(value):
    x, y = value
    if y == 1: navigate_gamepad(Gtk.DirectionType.UP)
    elif y == -1: navigate_gamepad(Gtk.DirectionType.DOWN)

    if x == -1: navigate_gamepad(Gtk.DirectionType.LEFT)
    elif x == 1: navigate_gamepad(Gtk.DirectionType.RIGHT)

def _handle_axis_motion(self, event):
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

def _handle_button_down(self, button):
    win = get_active_window()
    is_dialog_active = isinstance(win, Gtk.Dialog)
    btn = self.button_map

    if button == btn["confirm"]:
        focused = win.get_focus() if win else None

        if isinstance(focused, Gtk.TreeView):
            _handle_treeview_confirm(focused)
        elif not find_combobox(focused):
            GLib.idle_add(lambda: activate_focused_widget(self))

    elif button == btn["back"]:
        if is_dialog_active:
            win.response(Gtk.ResponseType.CANCEL)

    elif not is_dialog_active:
        if button == btn["square"]:
            self.on_button_kill_clicked(None)
        elif button == btn["triangle"]:
            _open_context_menu(self)
        elif button == btn["lb"]:
            self.on_button_add_clicked(None)
        elif button == btn["rb"]:
            self.on_button_settings_clicked(None)
        elif button == btn["start"]:
            GLib.idle_add(lambda: self.on_button_bye_clicked(None))

def _handle_treeview_confirm(treeview):
    path, column = treeview.get_cursor()
    if path is None:
        return

    column = column or treeview.get_column(0)
    if column is None:
        return

    editable_renderer = next(
        (r for r in column.get_cells() if isinstance(r, Gtk.CellRendererText) and r.get_property("editable")),
        None
    )

    if editable_renderer:
        treeview.set_cursor(path, column, True)
        GLib.idle_add(lambda: _open_keyboard_for_treeview(path, column, editable_renderer, treeview))
    else:
        treeview.row_activated(path, column)

def _open_keyboard_for_treeview(path, column, renderer, treeview):
    active_win = get_active_window()
    active_widget = active_win.get_focus() if active_win else None

    if isinstance(active_widget, Gtk.Entry):
        dummy_entry = Gtk.Entry()
        dummy_entry.set_text(active_widget.get_text())

        dialog = VirtualKeyboard(active_win, dummy_entry)

        def on_keyboard_closed(*args):
            renderer.emit("edited", path.to_string(), dummy_entry.get_text())
            treeview.grab_focus()
            treeview.set_cursor(path, column, False)
            active_win.present()

        dialog.connect("destroy", on_keyboard_closed)
        dialog.show_all()

def _open_context_menu(self):
    focused = self.get_focus()
    if isinstance(focused, Gtk.FlowBoxChild):
        self.on_item_right_click(focused, None)
        items = self.context_menu.get_children()

        for i, item in enumerate(items):
            if item == self.menu_play:
                self.menu_index = i
                self.context_menu.select_item(item)
                break

def adjust_widget_value(widget, direction):
    combo = find_combobox(widget)
    if combo and combo.get_model():
        count = combo.get_model().iter_n_children(None)
        current = combo.get_active()

        step = 1 if direction == "right" else -1
        combo.set_active((current + step) % count)
        return True

    if isinstance(widget, (Gtk.Scale, Gtk.SpinButton)):
        adjustment = widget.get_adjustment()
        step = adjustment.get_step_increment() or 1

        new_value = adjustment.get_value() + (step if direction == "right" else -step)
        adjustment.set_value(new_value)
        return True

    return False

def find_combobox(widget):
    while widget:
        if isinstance(widget, Gtk.ComboBox):
            return widget
        widget = widget.get_parent()
    return None

def handle_menu_navigation(self, event, btn):
    items = self.context_menu.get_children()
    if not items:
        return

    self.menu_index = getattr(self, "menu_index", 0)

    def is_valid(item):
        return isinstance(item, Gtk.MenuItem) and not isinstance(item, Gtk.SeparatorMenuItem) and item.get_sensitive()

    def move(step):
        for _ in range(len(items)):
            self.menu_index = (self.menu_index + step) % len(items)
            if is_valid(items[self.menu_index]):
                break

    if event.type == pygame.JOYHATMOTION:
        y = event.value[1]
        if y == -1: move(1)
        elif y == 1: move(-1)
        self.context_menu.select_item(items[self.menu_index])

    elif event.type == pygame.JOYBUTTONDOWN:
        if event.button == btn["confirm"]:
            item = items[self.menu_index]
            if is_valid(item):
                GLib.idle_add(item.activate)

        elif event.button == btn["back"]:
            self.context_menu.popdown()

def navigate_gamepad(direction):
    active_window = get_active_window()
    focused = active_window.get_focus() if active_window else None

    if not focused:
        return

    is_horizontal = direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT)
    is_vertical = direction in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN)

    if isinstance(focused, Gtk.TreeView):
        model = focused.get_model()
        path, _ = focused.get_cursor()

        if is_horizontal:
            active_window.child_focus(Gtk.DirectionType.TAB_FORWARD if direction == Gtk.DirectionType.RIGHT else Gtk.DirectionType.TAB_BACKWARD)
            return

        if model and is_vertical:
            count = len(model)
            if count > 0:
                current_index = path.get_indices()[0] if path else -1
                new_index = current_index - 1 if direction == Gtk.DirectionType.UP else current_index + 1

                if 0 <= new_index < count:
                    new_path = Gtk.TreePath(new_index)
                    focused.set_cursor(new_path)
                    focused.scroll_to_cell(new_path, None, False, 0.0, 0.0)
                else:
                    active_window.child_focus(Gtk.DirectionType.TAB_BACKWARD if direction == Gtk.DirectionType.UP else Gtk.DirectionType.TAB_FORWARD)
                return

    elif is_horizontal:
        dir_str = "right" if direction == Gtk.DirectionType.RIGHT else "left"
        if adjust_widget_value(focused, dir_str):
            return

    active_window.child_focus(direction)

    if isinstance(focused, Gtk.Button):
        parent = focused.get_parent()
        while parent:
            if isinstance(parent, Gtk.HeaderBar):
                active_window.child_focus(Gtk.DirectionType.TAB_FORWARD if direction in (Gtk.DirectionType.DOWN, Gtk.DirectionType.RIGHT) else Gtk.DirectionType.TAB_BACKWARD)
                return
            parent = parent.get_parent()

def activate_focused_widget(self):
    active_window = get_active_window()
    focused = active_window.get_focus() if active_window else None

    if not focused:
        return

    if isinstance(focused, Gtk.Entry):
        parent = focused.get_toplevel()
        dialog = VirtualKeyboard(parent, focused)
        dialog.connect("destroy", lambda *a: parent.present())
        dialog.show_all()

    elif isinstance(focused, Gtk.Button):
        focused.emit("clicked")

    elif isinstance(focused, Gtk.CheckButton):
        focused.set_active(not focused.get_active())

    elif isinstance(focused, Gtk.ListBoxRow):
        focused.emit("activate")

    elif isinstance(focused, Gtk.FlowBoxChild):
        game = self.selected()
        if game:
            if game.gameid in self.running:
                self.running_dialog(game.title)
            else:
                self.on_button_play_clicked()

def get_active_window():
    for window in Gtk.Window.list_toplevels():
        if window.is_active():
            return window
    return None
