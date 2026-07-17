import time
import gi
gi.require_version("Manette", "0.2")
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk, Manette
from faugus.keyboard import VirtualKeyboard
from faugus.path_manager import PathManager
from faugus.utils import widget_children, IdComboBox, show_steamgriddb_picker

MAPPED_BUTTONS = {
    "confirm": 5,
    "back": 7,
    "square": 6,
    "triangle": 4,
    "lb": 11,
    "rb": 12,
    "start": 9,
}
MAPPED_DPAD = {
    0: Gtk.DirectionType.UP,
    1: Gtk.DirectionType.DOWN,
    2: Gtk.DirectionType.LEFT,
    3: Gtk.DirectionType.RIGHT,
}

RAW_BUTTONS = {
    "confirm": 304,
    "back": 305,
    "square": 307,
    "triangle": 308,
    "lb": 310,
    "rb": 311,
    "start": 315,
}
RAW_HAT_AXES = (16, 17)

BUTTON_ROLES = {}
for _role, _code in MAPPED_BUTTONS.items():
    BUTTON_ROLES[_code] = _role
for _role, _code in RAW_BUTTONS.items():
    BUTTON_ROLES[_code] = _role

DPAD_DIRECTIONS = dict(MAPPED_DPAD)

_gamecontrollerdb = None


def _load_gamecontrollerdb():
    global _gamecontrollerdb
    if _gamecontrollerdb is not None:
        return _gamecontrollerdb

    mappings = {}
    path = PathManager.get_asset("gamecontrollerdb.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                platform_field = next((p for p in parts if p.startswith("platform:")), None)
                if platform_field and platform_field != "platform:Linux":
                    continue
                mappings[parts[0]] = ",".join(parts[2:])
    except OSError:
        mappings = {}

    _gamecontrollerdb = mappings
    return mappings


def _apply_gamecontrollerdb_mapping(device):
    if device.get_mapping() is not None or not device.supports_mapping():
        return
    mapping = _load_gamecontrollerdb().get(device.get_guid())
    if mapping:
        device.save_user_mapping(mapping)


def init_gamepad(self):
    self.gamepad_monitor = Manette.Monitor.new()
    self.gamepad_device = None
    self.gamepad_signal_ids = []

    self.axis_threshold = 0.7
    self.reset_threshold = 0.3
    self.can_move_x = True
    self.can_move_y = True

    self.held_direction = None
    self.hold_start_time = 0
    self.last_repeat_time = 0
    self.repeat_delay = 0.5
    self.repeat_interval = 0.1

    self.active_popover = None
    self.gamepad_active_combo = None
    self.gamepad_combo_popover = None
    self.gamepad_combo_listbox = None

    self.gamepad_monitor.connect("device-connected", lambda mon, device: _attach_device(self, device))
    self.gamepad_monitor.connect("device-disconnected", lambda mon, device: _detach_device(self, device))

    iterator = self.gamepad_monitor.iterate()
    while True:
        ok, device = iterator.next()
        if not ok:
            break
        _attach_device(self, device)

    GLib.timeout_add(50, lambda: _tick_repeat(self))


def _attach_device(self, device):
    if self.gamepad_device:
        _detach_device(self, self.gamepad_device)

    self.gamepad_device = device

    _apply_gamecontrollerdb_mapping(device)

    self.gamepad_signal_ids = [
        device.connect("event", lambda dev, event: _on_device_event(self, event)),
    ]


def _on_device_event(self, event):
    event_type = event.get_event_type()

    if event_type == Manette.EventType.EVENT_BUTTON_PRESS:
        _on_button_press(self, event)
    elif event_type == Manette.EventType.EVENT_BUTTON_RELEASE:
        _on_button_release(self, event)
    elif event_type == Manette.EventType.EVENT_ABSOLUTE:
        _on_absolute_axis(self, event)
    elif event_type == Manette.EventType.EVENT_HAT:
        _on_hat_axis(self, event)


def _detach_device(self, device):
    if self.gamepad_device is not device:
        return

    for signal_id in self.gamepad_signal_ids:
        device.disconnect(signal_id)

    self.gamepad_signal_ids = []
    self.gamepad_device = None
    self.held_direction = None


def _is_usable(self):
    active_win = get_active_window()
    is_focused = active_win is not None
    is_running = hasattr(self, "running") and bool(self.running)

    if is_running or not is_focused:
        self.held_direction = None
        return False, active_win

    return True, active_win


def _tick_repeat(self):
    usable, _ = _is_usable(self)

    if usable and getattr(self, "held_direction", None) is not None:
        now = time.time()
        if now - self.hold_start_time >= self.repeat_delay:
            if now - self.last_repeat_time >= self.repeat_interval:
                _dispatch_navigation(self, self.held_direction)
                self.last_repeat_time = now

    return True


def _set_held_direction(self, direction):
    if direction is not None:
        if getattr(self, "held_direction", None) != direction:
            self.held_direction = direction
            self.hold_start_time = time.time()
            self.last_repeat_time = time.time()
            _dispatch_navigation(self, direction)
    else:
        self.held_direction = None


def _dispatch_navigation(self, direction):
    combo_popover = getattr(self, "gamepad_combo_popover", None)
    if getattr(self, "gamepad_active_combo", None) and combo_popover and combo_popover.get_visible():
        _navigate_combo(self, direction)
        return
    self.gamepad_active_combo = None

    active_popover = getattr(self, "active_popover", None)
    if active_popover and active_popover.get_visible():
        _navigate_popover(self, direction)
        return
    self.active_popover = None

    navigate_gamepad(direction)


def _on_hat_axis(self, event):
    ok, axis, value = event.get_hat()
    if not ok or not _is_usable(self)[0]:
        return

    hat_x, hat_y = RAW_HAT_AXES

    direction = None
    if axis == hat_y:
        if value == -1: direction = Gtk.DirectionType.UP
        elif value == 1: direction = Gtk.DirectionType.DOWN
    elif axis == hat_x:
        if value == -1: direction = Gtk.DirectionType.LEFT
        elif value == 1: direction = Gtk.DirectionType.RIGHT

    if direction is None:
        held_is_vertical = axis == hat_y and self.held_direction in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN)
        held_is_horizontal = axis == hat_x and self.held_direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT)
        if held_is_vertical or held_is_horizontal:
            _set_held_direction(self, None)
        return

    _set_held_direction(self, direction)


def _on_absolute_axis(self, event):
    ok, axis, value = event.get_absolute()
    if not ok or not _is_usable(self)[0]:
        return

    if axis == 1:
        if self.can_move_y:
            if value < -self.axis_threshold:
                _set_held_direction(self, Gtk.DirectionType.UP)
                self.can_move_y = False
            elif value > self.axis_threshold:
                _set_held_direction(self, Gtk.DirectionType.DOWN)
                self.can_move_y = False
        elif abs(value) < self.reset_threshold:
            self.can_move_y = True
            if getattr(self, "held_direction", None) in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN):
                _set_held_direction(self, None)

    elif axis == 0:
        if self.can_move_x:
            if value < -self.axis_threshold:
                _set_held_direction(self, Gtk.DirectionType.LEFT)
                self.can_move_x = False
            elif value > self.axis_threshold:
                _set_held_direction(self, Gtk.DirectionType.RIGHT)
                self.can_move_x = False
        elif abs(value) < self.reset_threshold:
            self.can_move_x = True
            if getattr(self, "held_direction", None) in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT):
                _set_held_direction(self, None)


def _on_button_press(self, event):
    ok, button = event.get_button()
    if not ok:
        return

    usable, active_win = _is_usable(self)
    if not usable:
        return

    direction = DPAD_DIRECTIONS.get(button)
    if direction is not None:
        _set_held_direction(self, direction)
        return

    menu_visible = False
    if getattr(self, "active_popover", None):
        if self.active_popover.get_visible():
            menu_visible = True
        else:
            self.active_popover = None

    if menu_visible:
        _handle_menu_button(self, button)
    else:
        _handle_button_down(self, button, active_win)


def _on_button_release(self, event):
    ok, button = event.get_button()
    if not ok:
        return

    direction = DPAD_DIRECTIONS.get(button)
    if direction is not None and getattr(self, "held_direction", None) == direction:
        _set_held_direction(self, None)


def _handle_button_down(self, button, win):
    is_dialog_active = isinstance(win, Gtk.Dialog)
    role = BUTTON_ROLES.get(button)
    active_combo = getattr(self, "gamepad_active_combo", None)

    if role == "confirm":
        if active_combo:
            focused_row = win.get_focus() if win else None
            if isinstance(focused_row, Gtk.ListBoxRow):
                active_combo.set_selected(focused_row.get_index())
            _close_combo(self)
            return

        focused = win.get_focus() if win else None
        combo = find_combobox(focused)

        if isinstance(focused, Gtk.TreeView):
            _handle_treeview_confirm(focused)
        elif combo:
            open_combobox(self, combo)
        else:
            GLib.idle_add(lambda: activate_focused_widget(self))

    elif role == "back":
        if active_combo:
            _close_combo(self)
        elif is_dialog_active:
            win.close()

    elif active_combo:
        return

    elif not is_dialog_active:
        if role == "square":
            self.button_kill.emit("clicked")
        elif role == "triangle":
            _open_context_menu(self)
        elif role == "lb":
            self.button_add.emit("clicked")
        elif role == "rb":
            self.button_settings.emit("clicked")
        elif role == "start":
            GLib.idle_add(lambda: self.show_power_menu(None))

    elif isinstance(getattr(win, "notebook", None), Gtk.Notebook):
        if role == "lb":
            win.notebook.set_current_page(0)
        elif role == "rb":
            win.notebook.set_current_page(1)

    elif isinstance(win, VirtualKeyboard):
        if role == "square":
            win.on_backspace(None)
        elif role == "triangle":
            win.on_toggle_mode(win.get_focus(), "Shift")
        elif role == "start":
            win.on_enter(None)


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
        _open_keyboard_for_treeview(path, column, editable_renderer, treeview)
    else:
        treeview.row_activated(path, column)


def _open_keyboard_for_treeview(path, column, renderer, treeview):
    active_win = get_active_window()
    model = treeview.get_model()
    current_text = model[path][0] if model else ""

    dummy_entry = Gtk.Entry()
    dummy_entry.set_text(current_text)

    def on_keyboard_closed():
        renderer.emit("edited", path.to_string(), dummy_entry.get_text())
        treeview.grab_focus()
        treeview.set_cursor(path, column, False)
        active_win.present()

    dialog = VirtualKeyboard(active_win, dummy_entry, on_close=on_keyboard_closed)
    dialog.present()


def _open_context_menu(self):
    focused = self.get_focus()
    active_menu = None

    if isinstance(focused, Gtk.FlowBoxChild):
        self.on_item_right_click(focused, None)
        active_menu = getattr(self, "context_menu", None)

    elif isinstance(focused, Gtk.ListBoxRow):
        listbox = focused.get_parent()
        listbox.select_row(focused)

        menu = getattr(self, "category_context_menu", None)
        if menu:
            menu.set_parent(focused)
            menu.popup()
            active_menu = menu

    if not active_menu:
        return

    self.active_popover = active_menu

    items = [w for w in widget_children(active_menu.get_child()) if isinstance(w, Gtk.Button) and w.get_visible()]
    if not items:
        return

    menu_play = getattr(self, "menu_play", None)
    target = menu_play if menu_play in items else next((i for i in items if i.get_sensitive()), items[0])
    self.set_focus_visible(True)
    target.grab_focus()


def adjust_widget_value(widget, direction):
    if isinstance(widget, (Gtk.Scale, Gtk.SpinButton)):
        adjustment = widget.get_adjustment()
        step = adjustment.get_step_increment() or 1

        new_value = adjustment.get_value() + (step if direction == "right" else -step)
        adjustment.set_value(new_value)
        return True

    return False


def find_combobox(widget):
    while widget:
        if isinstance(widget, IdComboBox):
            return widget
        widget = widget.get_parent()
    return None


def open_combobox(self, combo):
    if getattr(self, "gamepad_active_combo", None):
        return

    model = combo.get_model()
    count = model.get_n_items() if model else 0
    if count == 0:
        return

    current = combo.get_selected()
    if current == Gtk.INVALID_LIST_POSITION or current >= count:
        current = 0

    list_box = Gtk.ListBox()
    list_box.set_selection_mode(Gtk.SelectionMode.NONE)

    for i in range(count):
        item = model.get_item(i)
        text = item.get_string() if item and hasattr(item, "get_string") else ""
        label = Gtk.Label(label=text, xalign=0)
        label.set_margin_start(10)
        label.set_margin_end(10)
        label.set_margin_top(6)
        label.set_margin_bottom(6)
        row = Gtk.ListBoxRow()
        row.set_child(label)
        list_box.append(row)

    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_max_content_height(480)
    scrolled.set_propagate_natural_height(True)
    scrolled.set_child(list_box)

    popover = Gtk.Popover()
    popover.set_parent(combo)
    popover.set_autohide(True)
    popover.add_css_class("menu")
    popover.set_child(scrolled)

    width = combo.get_width()
    if width > 0:
        list_box.set_size_request(width, -1)

    self.gamepad_active_combo = combo
    self.gamepad_combo_popover = popover
    self.gamepad_combo_listbox = list_box

    popover.connect("closed", lambda p: _on_combo_popover_closed(self, combo))
    popover.popup()

    row = list_box.get_row_at_index(current)
    if row:
        row.grab_focus()


def _on_combo_popover_closed(self, combo):
    if getattr(self, "gamepad_active_combo", None) is combo:
        popover = self.gamepad_combo_popover
        self.gamepad_active_combo = None
        self.gamepad_combo_popover = None
        self.gamepad_combo_listbox = None
        combo.grab_focus()
        if popover:
            popover.unparent()


def _close_combo(self):
    popover = getattr(self, "gamepad_combo_popover", None)
    if popover:
        popover.popdown()
    else:
        self.gamepad_active_combo = None


def _navigate_combo(self, direction):
    popover = getattr(self, "gamepad_combo_popover", None)
    if not popover or not popover.get_visible():
        self.gamepad_active_combo = None
        return

    if direction not in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN):
        return

    root = popover.get_root()
    if root:
        root.set_focus_visible(True)
    popover.child_focus(direction)


def _navigate_popover(self, direction):
    popover = getattr(self, "active_popover", None)
    if not popover or not popover.get_visible():
        self.active_popover = None
        return
    root = popover.get_root()
    if root:
        root.set_focus_visible(True)
    popover.child_focus(direction)


def _find_parent_popover(widget):
    parent = widget.get_parent() if widget else None
    while parent:
        if isinstance(parent, Gtk.Popover):
            return parent
        parent = parent.get_parent()
    return None


def _handle_menu_button(self, button):
    popover = getattr(self, "active_popover", None)
    if not popover or not popover.get_visible():
        return

    role = BUTTON_ROLES.get(button)

    if role == "confirm":
        GLib.idle_add(lambda: activate_focused_widget(self))

    elif role == "back":
        anchor = popover.get_parent()
        parent_popover = _find_parent_popover(anchor)

        popover.popdown()

        if parent_popover and parent_popover.get_visible() and anchor:
            self.active_popover = parent_popover
            self.set_focus_visible(True)
            anchor.grab_focus()
        elif parent_popover:
            parent_popover.popdown()
            self.active_popover = None
        else:
            self.active_popover = None


def _find_column_list_view(widget):
    while widget:
        if type(widget).__name__ == "GtkColumnListView":
            return widget
        widget = widget.get_parent()
    return None


def _is_descendant_of(widget, ancestor):
    w = widget.get_parent()
    while w is not None:
        if w is ancestor:
            return True
        w = w.get_parent()
    return False


def _find_ancestor_by_typename(widget, type_name):
    while widget:
        if type(widget).__name__ == type_name:
            return widget
        widget = widget.get_parent()
    return None


def _find_descendant_by_typename(widget, type_name):
    if type(widget).__name__ == type_name:
        return widget
    child = widget.get_first_child()
    while child:
        found = _find_descendant_by_typename(child, type_name)
        if found:
            return found
        child = child.get_next_sibling()
    return None


def _collect_focusable(widget, out):
    if not widget.get_mapped():
        return
    if widget.get_sensitive() and widget.get_focusable() and not isinstance(widget, Gtk.Label):
        out.append(widget)
    child = widget.get_first_child()
    while child:
        _collect_focusable(child, out)
        child = child.get_next_sibling()


def _focus_nearest_in_direction(current, direction, root):
    ok, current_bounds = current.compute_bounds(root)
    if not ok:
        return False
    cx0, cy0 = current_bounds.origin.x, current_bounds.origin.y
    cx1, cy1 = cx0 + current_bounds.size.width, cy0 + current_bounds.size.height

    candidates = []
    _collect_focusable(root, candidates)

    aligned = []
    others = []
    for candidate in candidates:
        if candidate is current:
            continue
        ok, bounds = candidate.compute_bounds(root)
        if not ok:
            continue
        x0, y0 = bounds.origin.x, bounds.origin.y
        x1, y1 = x0 + bounds.size.width, y0 + bounds.size.height

        if direction == Gtk.DirectionType.LEFT and x1 > cx0:
            continue
        if direction == Gtk.DirectionType.RIGHT and x0 < cx1:
            continue
        if direction == Gtk.DirectionType.UP and y1 > cy0:
            continue
        if direction == Gtk.DirectionType.DOWN and y0 < cy1:
            continue

        if direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT):
            primary_dist = (cx0 - x1) if direction == Gtk.DirectionType.LEFT else (x0 - cx1)
            cross_overlap = min(cy1, y1) - max(cy0, y0)
            cross_dist = abs((y0 + y1) / 2 - (cy0 + cy1) / 2)
        else:
            primary_dist = (cy0 - y1) if direction == Gtk.DirectionType.UP else (y0 - cy1)
            cross_overlap = min(cx1, x1) - max(cx0, x0)
            cross_dist = abs((x0 + x1) / 2 - (cx0 + cx1) / 2)

        entry = (primary_dist, cross_dist, candidate)
        if cross_overlap > 0:
            aligned.append(entry)
        else:
            others.append(entry)

    pool = aligned if aligned else others
    if not pool:
        return False

    pool.sort(key=lambda e: (e[0], e[1]))
    target = pool[0][2]
    target.grab_focus()
    if isinstance(target, Gtk.FlowBoxChild):
        parent = target.get_parent()
        if isinstance(parent, Gtk.FlowBox):
            parent.select_child(target)
    return True


def _navigate_column_list(list_view, direction):
    model = list_view.get_model()
    count = model.get_n_items() if model else 0
    if count == 0:
        return False

    current = model.get_selected() if hasattr(model, "get_selected") else Gtk.INVALID_LIST_POSITION
    if current == Gtk.INVALID_LIST_POSITION:
        current = -1

    new_index = current - 1 if direction == Gtk.DirectionType.UP else current + 1
    if new_index < 0 or new_index >= count:
        return False

    list_view.activate_action("list.select-item", GLib.Variant("(ubb)", (new_index, False, False)))
    list_view.activate_action("list.scroll-to-item", GLib.Variant("u", new_index))
    return True


def navigate_gamepad(direction):
    active_window = get_active_window()
    if active_window:
        active_window.set_focus_visible(True)
    focused = active_window.get_focus() if active_window else None

    if not focused:
        if active_window:
            active_window.child_focus(Gtk.DirectionType.TAB_FORWARD)
        return

    if isinstance(focused, Gtk.ScrolledWindow):
        target = _find_descendant_by_typename(focused, "GtkColumnListView")
        if target:
            target.grab_focus()
            focused = active_window.get_focus()
        else:
            child = focused.get_child()
            if child and child.child_focus(Gtk.DirectionType.TAB_FORWARD):
                focused = active_window.get_focus()

    is_horizontal = direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT)
    is_vertical = direction in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN)

    listbox_suggestions = getattr(active_window, "listbox_suggestions", None)
    if is_vertical and listbox_suggestions is not None and isinstance(focused, Gtk.ListBoxRow) \
            and focused.get_parent() is listbox_suggestions:
        index = focused.get_index()
        if direction == Gtk.DirectionType.UP:
            if index > 0:
                target = listbox_suggestions.get_row_at_index(index - 1)
                if target:
                    target.grab_focus()
            return
        else:
            target = listbox_suggestions.get_row_at_index(index + 1)
            if target:
                target.grab_focus()
                return
            grid = getattr(active_window, "grid", None)
            first_key = grid.get_child_at(0, 0) if grid else None
            if first_key:
                first_key.grab_focus()
            return

    if is_vertical and _find_ancestor_by_typename(focused, "GtkPathBar"):
        if direction == Gtk.DirectionType.UP:
            titlebar = active_window.get_titlebar() if hasattr(active_window, "get_titlebar") else None
            if isinstance(titlebar, Gtk.HeaderBar):
                titlebar.child_focus(Gtk.DirectionType.TAB_FORWARD)
                return
        else:
            column_list = _find_descendant_by_typename(active_window, "GtkColumnListView")
            if column_list:
                column_list.grab_focus()
                return

    column_list = _find_column_list_view(focused)
    if column_list and is_vertical:
        if _navigate_column_list(column_list, direction):
            return

    if isinstance(focused, Gtk.TreeView):
        model = focused.get_model()
        path, _ = focused.get_cursor()

        if is_horizontal:
            _focus_nearest_in_direction(focused, direction, active_window)
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
                elif not _focus_nearest_in_direction(focused, direction, active_window) and direction == Gtk.DirectionType.UP:
                    titlebar = active_window.get_titlebar() if hasattr(active_window, "get_titlebar") else None
                    if isinstance(titlebar, Gtk.HeaderBar):
                        titlebar.child_focus(Gtk.DirectionType.TAB_FORWARD)
            return

    elif is_horizontal:
        dir_str = "right" if direction == Gtk.DirectionType.RIGHT else "left"
        if adjust_widget_value(focused, dir_str):
            return

    if is_horizontal:
        if _focus_nearest_in_direction(focused, direction, active_window):
            return

    active_window.child_focus(direction)

    new_focus = active_window.get_focus()
    if isinstance(new_focus, Gtk.ScrolledWindow):
        target = _find_descendant_by_typename(new_focus, "GtkColumnListView")
        if target:
            target.grab_focus()
        else:
            child = new_focus.get_child()
            if child:
                child.child_focus(Gtk.DirectionType.TAB_FORWARD)

    new_focus = active_window.get_focus()
    stuck = new_focus is focused

    if stuck and isinstance(focused, Gtk.Button):
        parent = focused.get_parent()
        while parent:
            if isinstance(parent, Gtk.HeaderBar):
                active_window.child_focus(Gtk.DirectionType.TAB_FORWARD if direction in (Gtk.DirectionType.DOWN, Gtk.DirectionType.RIGHT) else Gtk.DirectionType.TAB_BACKWARD)
                return
            parent = parent.get_parent()

    if stuck and direction == Gtk.DirectionType.UP:
        titlebar = active_window.get_titlebar() if hasattr(active_window, "get_titlebar") else None
        if isinstance(titlebar, Gtk.HeaderBar):
            titlebar.child_focus(Gtk.DirectionType.TAB_FORWARD)
            return

    if stuck and direction == Gtk.DirectionType.DOWN:
        column_list = _find_descendant_by_typename(active_window, "GtkColumnListView")
        if column_list:
            column_list.grab_focus()


def activate_focused_widget(self):
    active_window = get_active_window()
    focused = active_window.get_focus() if active_window else None

    if not focused:
        return

    if isinstance(focused, (Gtk.Entry, Gtk.Text)):
        parent = focused.get_root()
        fetch_suggestions = None
        on_suggestion_selected = None
        entry_title = getattr(parent, "entry_title", None)
        is_title_suggestion_field = (
            entry_title is not None
            and (focused is entry_title or _is_descendant_of(focused, entry_title))
            and getattr(parent, "interface_mode", None) == "SteamGridDB"
        )
        if is_title_suggestion_field:
            fetch_suggestions = parent.fetch_title_suggestions_for_keyboard
            on_suggestion_selected = parent.on_keyboard_suggestion_selected
            parent._virtual_keyboard_active_for_title = True
            popover = getattr(parent, "popover_suggestion", None)
            if popover is not None:
                popover.popdown()

        def on_keyboard_closed():
            if is_title_suggestion_field:
                parent._virtual_keyboard_active_for_title = False
            parent.present()

        dialog = VirtualKeyboard(
            parent, focused, on_close=on_keyboard_closed,
            fetch_suggestions=fetch_suggestions, on_suggestion_selected=on_suggestion_selected
        )
        dialog.present()

    elif isinstance(focused, Gtk.Button):
        label = focused.get_label() if hasattr(focused, "get_label") else None
        focused.emit("clicked")

        if label in ("Shift", "Caps", "?123", "ABC"):
            def restore_focus():
                win = get_active_window()
                if not win: return
                target = {"?123": "ABC", "ABC": "?123"}.get(label, label)

                def find_and_focus(w):
                    if isinstance(w, Gtk.Button) and w.get_label() == target:
                        w.grab_focus()
                        return True
                    for c in widget_children(w):
                        if find_and_focus(c): return True
                    return False

                find_and_focus(win)

            GLib.idle_add(restore_focus)

    elif isinstance(focused, Gtk.CheckButton):
        focused.set_active(not focused.get_active())

    elif isinstance(focused, Gtk.ListBoxRow):
        focused.emit("activate")

    elif isinstance(focused, Gtk.FlowBoxChild) and hasattr(focused, "gamepad_activate"):
        focused.gamepad_activate()

    elif isinstance(focused, Gtk.FlowBoxChild):
        game = self.selected()
        if game:
            if game.gameid in self.running:
                self.running_dialog(game.title)
            else:
                self.button_play.emit("clicked")

    elif getattr(active_window, "interface_mode", None) == "SteamGridDB" and focused in (
        getattr(active_window, "hero_preview1", None), getattr(active_window, "hero_preview2", None)
    ):
        show_steamgriddb_picker(active_window, "hero")

    elif getattr(active_window, "interface_mode", None) == "SteamGridDB" and focused in (
        getattr(active_window, "image_banner_stack", None), getattr(active_window, "image_banner2_stack", None)
    ):
        show_steamgriddb_picker(active_window, "grid")

    elif type(focused).__name__ == "GtkColorSwatch":
        chooser = focused.get_ancestor(Gtk.ColorChooser)
        if chooser:
            chooser.set_rgba(focused.get_property("rgba"))

    elif _find_column_list_view(focused):
        column_list = _find_column_list_view(focused)
        model = column_list.get_model()
        current = model.get_selected() if model and hasattr(model, "get_selected") else Gtk.INVALID_LIST_POSITION
        if current != Gtk.INVALID_LIST_POSITION:
            column_list.activate_action("list.activate-item", GLib.Variant("u", current))


def get_active_window():
    toplevels = Gtk.Window.get_toplevels()
    for i in range(toplevels.get_n_items()):
        window = toplevels.get_item(i)
        if window.is_active():
            return window
    return None
