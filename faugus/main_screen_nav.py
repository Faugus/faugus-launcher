import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

from faugus.utils import widget_children


def get_active_window():
    toplevels = Gtk.Window.get_toplevels()
    for i in range(toplevels.get_n_items()):
        window = toplevels.get_item(i)
        if window.is_active():
            return window
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
    if widget.get_sensitive() and widget.get_focusable() and not isinstance(widget, (Gtk.Label, Gtk.ScrolledWindow)):
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


def _find_list_base_view(widget):
    while widget:
        if type(widget).__name__ in ("GtkColumnListView", "GridView"):
            return widget
        widget = widget.get_parent()
    return None


def _find_list_base_descendant(widget):
    return _find_descendant_by_typename(widget, "GtkColumnListView") or _find_descendant_by_typename(widget, "GridView")


def _grid_view_columns(grid_view):
    first_y = None
    count_in_row = 0
    child = grid_view.get_first_child()
    while child:
        if child.get_child_visible():
            ok, b = child.compute_bounds(grid_view)
            if ok:
                if first_y is None:
                    first_y = b.origin.y
                    count_in_row = 1
                elif abs(b.origin.y - first_y) < 1:
                    count_in_row += 1
                else:
                    break
        child = child.get_next_sibling()
    return max(count_in_row, 1)


def _navigate_list_base_view(view, direction):
    model = view.get_model()
    count = model.get_n_items() if model else 0
    if count == 0:
        return False

    current = model.get_selected() if hasattr(model, "get_selected") else Gtk.INVALID_LIST_POSITION
    is_grid = type(view).__name__ == "GridView"

    if current == Gtk.INVALID_LIST_POSITION:
        new_index = 0
    elif is_grid:
        ncols = _grid_view_columns(view)
        if direction == Gtk.DirectionType.LEFT:
            new_index = current - 1
        elif direction == Gtk.DirectionType.RIGHT:
            new_index = current + 1
        elif direction == Gtk.DirectionType.UP:
            new_index = current - ncols
        else:
            new_index = current + ncols
    else:
        if direction not in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN):
            return False
        new_index = current - 1 if direction == Gtk.DirectionType.UP else current + 1

    if new_index < 0 or new_index >= count:
        return False

    view.activate_action("list.select-item", GLib.Variant("(ubb)", (new_index, False, False)))
    view.activate_action("list.scroll-to-item", GLib.Variant("u", new_index))

    selected_child = _find_list_base_selected_child(view)
    if selected_child is not None:
        selected_child.grab_focus()
    return True


def _find_list_base_selected_child(view):
    child = view.get_first_child()
    while child:
        if child.get_state_flags() & Gtk.StateFlags.SELECTED:
            return child
        child = child.get_next_sibling()
    return None


def _grab_focus_list_base_view(view):
    selected_child = _find_list_base_selected_child(view)
    if selected_child is not None:
        selected_child.grab_focus()
    else:
        view.grab_focus()


def escape_focus(window, widget, direction):
    widget.set_can_focus(False)
    try:
        result = window.child_focus(direction)
    finally:
        widget.set_can_focus(True)
    return bool(result)


def adjust_widget_value(widget, direction):
    if isinstance(widget, (Gtk.Scale, Gtk.SpinButton)):
        adjustment = widget.get_adjustment()
        step = adjustment.get_step_increment() or 1

        current = adjustment.get_value()
        new_value = current + (step if direction == "right" else -step)
        new_value = max(adjustment.get_lower(), min(new_value, adjustment.get_upper()))
        if new_value == current:
            return False

        adjustment.set_value(new_value)
        return True

    return False


def _flowbox_has_row_below(flowbox, current_child):
    ok, current_bounds = current_child.compute_bounds(flowbox)
    if not ok:
        return True
    cy1 = current_bounds.origin.y + current_bounds.size.height
    for c in flowbox:
        if not c.get_child_visible() or c is current_child:
            continue
        ok2, b = c.compute_bounds(flowbox)
        if ok2 and b.origin.y >= cy1 - 1:
            return True
    return False


def _flowbox_has_row_above(flowbox, current_child):
    ok, current_bounds = current_child.compute_bounds(flowbox)
    if not ok:
        return True
    cy0 = current_bounds.origin.y
    for c in flowbox:
        if not c.get_child_visible() or c is current_child:
            continue
        ok2, b = c.compute_bounds(flowbox)
        if ok2 and b.origin.y <= cy0 - 1:
            return True
    return False


def focus_top_bar(window):
    top_bar = getattr(window, "top_bar", None)
    if top_bar is None:
        return False

    candidates = []
    _collect_focusable(top_bar, candidates)
    if not candidates:
        return False

    candidates[0].grab_focus()
    return True


def focus_bottom_bar_by_column(window, focused_flowbox_child):
    scale_zoom = getattr(window, "scale_zoom", None)
    bottom_bar = scale_zoom.get_parent() if scale_zoom is not None else None
    if not isinstance(bottom_bar, Gtk.CenterBox):
        box_bottom = getattr(window, "box_bottom", None)
        if box_bottom is None:
            return False
        candidates = []
        _collect_focusable(box_bottom, candidates)
        if not candidates:
            return False
        candidates[0].grab_focus()
        return True

    flowbox = focused_flowbox_child.get_parent() if focused_flowbox_child is not None else None

    target_widget = None
    if flowbox is not None:
        ok, fb_bounds = flowbox.compute_bounds(window)
        ok2, item_bounds = focused_flowbox_child.compute_bounds(window)
        if ok and ok2 and fb_bounds.size.width > 0:
            relative_x = (item_bounds.origin.x + item_bounds.size.width / 2) - fb_bounds.origin.x
            third = fb_bounds.size.width / 3

            if relative_x < third:
                target_widget = bottom_bar.get_start_widget()
            elif relative_x < 2 * third:
                target_widget = bottom_bar.get_center_widget()
            else:
                target_widget = bottom_bar.get_end_widget()

    if target_widget is None:
        target_widget = bottom_bar.get_center_widget() or bottom_bar.get_start_widget() or bottom_bar.get_end_widget()
    if target_widget is None:
        return False

    candidates = []
    _collect_focusable(target_widget, candidates)
    if not candidates:
        return False

    candidates[0].grab_focus()
    return True


def focus_flowbox_child(flowbox, child):
    flowbox.grab_focus()
    flowbox.select_child(child)
    child.grab_focus()

    if flowbox.child_focus(Gtk.DirectionType.TAB_FORWARD):
        flowbox.child_focus(Gtk.DirectionType.TAB_BACKWARD)
    elif flowbox.child_focus(Gtk.DirectionType.TAB_BACKWARD):
        flowbox.child_focus(Gtk.DirectionType.TAB_FORWARD)
    flowbox.select_child(child)
    if flowbox.get_focus_child() is not child:
        child.grab_focus()


def _focus_games_area(window):
    if getattr(window, "carrousel_active", lambda: False)():
        carrousel_fixed = getattr(window, "carrousel_fixed", None)
        if carrousel_fixed is not None:
            carrousel_fixed.grab_focus()
            refresh = getattr(window, "on_carrousel_focus_changed", None)
            if refresh:
                refresh(carrousel_fixed, None)
            return True
        return False

    flowbox = getattr(window, "flowbox", None)
    if flowbox is None:
        return False

    selected = flowbox.get_selected_children()
    child = selected[0] if selected else None
    if child is None:
        child = next((c for c in widget_children(flowbox) if c.get_child_visible()), None)
    if child is None:
        return False

    focus_flowbox_child(flowbox, child)
    return True


def navigate_main_screen(window, focused, direction):
    carrousel_fixed = getattr(window, "carrousel_fixed", None)
    if carrousel_fixed is not None and getattr(window, "carrousel_active", lambda: False)() \
            and (focused is carrousel_fixed or _is_descendant_of(focused, carrousel_fixed)):
        if direction == Gtk.DirectionType.LEFT:
            window.carrousel_move(-1)
            return True
        if direction == Gtk.DirectionType.RIGHT:
            window.carrousel_move(1)
            return True
        if direction in (Gtk.DirectionType.UP, Gtk.DirectionType.DOWN):
            result = escape_focus(window, carrousel_fixed, direction)
            refresh = getattr(window, "on_carrousel_focus_changed", None)
            if refresh:
                refresh(carrousel_fixed, None)
            return result
        return False

    if direction in (Gtk.DirectionType.LEFT, Gtk.DirectionType.RIGHT):
        if adjust_widget_value(focused, "right" if direction == Gtk.DirectionType.RIGHT else "left"):
            return True

        flowbox = getattr(window, "flowbox", None)
        if isinstance(focused, Gtk.FlowBoxChild):
            _focus_nearest_in_direction(focused, direction, focused.get_parent())
            return True
        if flowbox is not None and focused is flowbox:
            return True

        for container in (getattr(window, "bottom_bar", None), getattr(window, "box_bottom", None), getattr(window, "top_bar", None)):
            if container is not None and (focused is container or _is_descendant_of(focused, container)):
                _focus_nearest_in_direction(focused, direction, container)
                return True

    if direction == Gtk.DirectionType.DOWN:
        flowbox = getattr(window, "flowbox", None)
        if isinstance(focused, Gtk.FlowBoxChild):
            if not _flowbox_has_row_below(focused.get_parent(), focused):
                return focus_bottom_bar_by_column(window, focused)
            return False
        if flowbox is not None and focused is flowbox:
            selected = flowbox.get_selected_children()
            reference_child = selected[0] if selected else None
            if reference_child is None or not _flowbox_has_row_below(flowbox, reference_child):
                return focus_bottom_bar_by_column(window, reference_child)
            return False

    if direction == Gtk.DirectionType.UP:
        flowbox = getattr(window, "flowbox", None)
        if isinstance(focused, Gtk.FlowBoxChild) or (flowbox is not None and focused is flowbox):
            reference_child = focused if isinstance(focused, Gtk.FlowBoxChild) else None
            if reference_child is None and flowbox is not None:
                selected = flowbox.get_selected_children()
                reference_child = selected[0] if selected else None
            if reference_child is not None and not _flowbox_has_row_above(reference_child.get_parent(), reference_child):
                focus_top_bar(window)
                return True
            return False

        bottom_container = getattr(window, "bottom_bar", None) or getattr(window, "box_bottom", None)
        if bottom_container is not None and (focused is bottom_container or _is_descendant_of(focused, bottom_container)):
            return _focus_games_area(window)

    return False


def navigate_focus(direction):
    active_window = get_active_window()
    if active_window:
        active_window.set_focus_visible(True)
    focused = active_window.get_focus() if active_window else None

    if not focused:
        if active_window:
            active_window.child_focus(Gtk.DirectionType.TAB_FORWARD)
        return True

    if navigate_main_screen(active_window, focused, direction):
        return True

    if isinstance(focused, Gtk.ScrolledWindow):
        target = _find_list_base_descendant(focused)
        if target:
            _grab_focus_list_base_view(target)
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
            return True
        else:
            target = listbox_suggestions.get_row_at_index(index + 1)
            if target:
                target.grab_focus()
                return True
            grid = getattr(active_window, "grid", None)
            first_key = grid.get_child_at(0, 0) if grid else None
            if first_key:
                first_key.grab_focus()
            return True

    if is_vertical and _find_ancestor_by_typename(focused, "GtkPathBar"):
        if direction == Gtk.DirectionType.UP:
            titlebar = active_window.get_titlebar() if hasattr(active_window, "get_titlebar") else None
            if isinstance(titlebar, Gtk.HeaderBar):
                titlebar.child_focus(Gtk.DirectionType.TAB_FORWARD)
                return True
        else:
            list_base_view = _find_list_base_descendant(active_window)
            if list_base_view:
                _grab_focus_list_base_view(list_base_view)
                return True

    list_base_view = _find_list_base_view(focused)
    if list_base_view and (is_vertical or (is_horizontal and type(list_base_view).__name__ == "GridView")):
        if _navigate_list_base_view(list_base_view, direction):
            return True

    if isinstance(focused, Gtk.TreeView):
        model = focused.get_model()
        path, _ = focused.get_cursor()

        if is_horizontal:
            _focus_nearest_in_direction(focused, direction, active_window)
            return True

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
            return True

    if is_horizontal:
        if _focus_nearest_in_direction(focused, direction, active_window):
            return True

    active_window.child_focus(direction)

    new_focus = active_window.get_focus()
    if isinstance(new_focus, Gtk.ScrolledWindow):
        target = _find_list_base_descendant(new_focus)
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
                return True
            parent = parent.get_parent()

    if stuck and direction == Gtk.DirectionType.UP:
        titlebar = active_window.get_titlebar() if hasattr(active_window, "get_titlebar") else None
        if isinstance(titlebar, Gtk.HeaderBar):
            titlebar.child_focus(Gtk.DirectionType.TAB_FORWARD)
            return True

    if stuck and direction == Gtk.DirectionType.DOWN:
        list_base_view = _find_list_base_descendant(active_window)
        if list_base_view:
            _grab_focus_list_base_view(list_base_view)
            return True

    return not stuck
