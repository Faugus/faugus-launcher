import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from faugus.utils import hide_dialog_action_area

LAYOUT_LOWER = [
    [("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1), ("8", 1), ("9", 1), ("0", 1), ("-", 1), ("=", 1), ("Back", 2)],
    [("q", 1), ("w", 1), ("e", 1), ("r", 1), ("t", 1), ("y", 1), ("u", 1), ("i", 1), ("o", 1), ("p", 1), ("[", 1), ("]", 1), ("Enter", 2)],
    [("Caps", 2), ("a", 1), ("s", 1), ("d", 1), ("f", 1), ("g", 1), ("h", 1), ("j", 1), ("k", 1), ("l", 1), (";", 1), ("'", 1), ("\\", 1)],
    [("Shift", 2), ("z", 1), ("x", 1), ("c", 1), ("v", 1), ("b", 1), ("n", 1), ("m", 1), (",", 1), (".", 1), ("/", 1), ("?123", 2)],
    [("Cancel", 3), ("Space", 8), ("Clear", 3)]
]

LAYOUT_SHIFT = [
    [("!", 1), ("@", 1), ("#", 1), ("$", 1), ("%", 1), ("^", 1), ("&", 1), ("*", 1), ("(", 1), (")", 1), ("_", 1), ("+", 1), ("Back", 2)],
    [("Q", 1), ("W", 1), ("E", 1), ("R", 1), ("T", 1), ("Y", 1), ("U", 1), ("I", 1), ("O", 1), ("P", 1), ("{", 1), ("}", 1), ("Enter", 2)],
    [("Caps", 2), ("A", 1), ("S", 1), ("D", 1), ("F", 1), ("G", 1), ("H", 1), ("J", 1), ("K", 1), ("L", 1), (":", 1), ("\"", 1), ("|", 1)],
    [("Shift", 2), ("Z", 1), ("X", 1), ("C", 1), ("V", 1), ("B", 1), ("N", 1), ("M", 1), ("<", 1), (">", 1), ("?", 1), ("?123", 2)],
    [("Cancel", 3), ("Space", 8), ("Clear", 3)]
]

LAYOUT_SYMBOLS = [
    [("1", 1), ("2", 1), ("3", 1), ("4", 1), ("5", 1), ("6", 1), ("7", 1), ("8", 1), ("9", 1), ("0", 1), ("-", 1), ("=", 1), ("Back", 2)],
    [("!", 1), ("@", 1), ("#", 1), ("$", 1), ("%", 1), ("^", 1), ("&", 1), ("*", 1), ("(", 1), (")", 1), ("_", 1), ("+", 1), ("Enter", 2)],
    [("Caps", 2), ("~", 1), ("`", 1), ("|", 1), ("•", 1), ("√", 1), ("π", 1), ("÷", 1), ("×", 1), ("{", 1), ("}", 1), ("°", 1), ("£", 1)],
    [("ABC", 2), ("¢", 1), ("€", 1), ("¥", 1), ("^", 1), ("°", 1), ("=", 1), ("[", 1), ("]", 1), ("\\", 1), ("/", 1), ("ABC", 2)],
    [("Cancel", 3), ("Space", 8), ("Clear", 3)]
]


class VirtualKeyboard(Gtk.Dialog):
    def __init__(self, parent, entry, on_close=None):
        super().__init__(title="Faugus", transient_for=parent, modal=True)
        hide_dialog_action_area(self)

        self.entry = entry
        self.on_close = on_close
        self.mode = "lower"
        self.original_text = self.entry.get_text()

        self.set_resizable(False)
        self.add_css_class("tv-keyboard")
        self.apply_css()

        vbox = self.get_content_area()
        vbox.set_spacing(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)
        vbox.set_margin_top(10)

        self.display_entry = Gtk.Entry()
        self.display_entry.set_text(self.entry.get_text())
        self.display_entry.set_alignment(0.5)
        self.display_entry.set_can_focus(False)
        self.display_entry.connect("changed", self.on_display_changed)
        vbox.append(self.display_entry)

        self.grid = Gtk.Grid(row_spacing=8, column_spacing=8)
        self.grid.set_halign(Gtk.Align.CENTER)
        vbox.append(self.grid)

        self.build_keys()
        self.connect("response", self.on_response)

    def apply_css(self):
        css = b"""
        .tv-keyboard button {
            font-weight: bold;
            min-height: 40px;
            min-width: 40px;
            border-radius: 8px;
        }
        .tv-keyboard button:focus {
            background-color: alpha(@theme_selected_bg_color, 1);
        }
        .tv-keyboard entry {
            min-height: 40px;
            border-radius: 8px;
        }
        """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def build_keys(self):
        child = self.grid.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.grid.remove(child)
            child = next_child

        if self.mode == "symbols":
            layout = LAYOUT_SYMBOLS
        elif self.mode == "shift":
            layout = LAYOUT_SHIFT
        else:
            layout = LAYOUT_LOWER

        for r, row in enumerate(layout):
            col_offset = 0
            for item in row:
                label, span = item
                display_label = label

                if self.mode == "caps" and len(label) == 1 and label.isalpha():
                    display_label = label.upper()

                btn = Gtk.Button(label=display_label)
                btn.set_hexpand(True)
                btn.set_vexpand(True)

                btn.grid_col = col_offset
                btn.grid_row = r

                if (label == "Shift" and self.mode == "shift") or \
                   (label == "Caps" and self.mode == "caps") or \
                   (label in ("?123", "ABC") and self.mode == "symbols"):
                    btn.add_css_class("suggested-action")

                if label == "Back":
                    btn.connect("clicked", self.on_backspace)
                elif label == "Enter":
                    btn.connect("clicked", self.on_enter)
                elif label in ("Shift", "Caps"):
                    btn.connect("clicked", self.on_toggle_mode, label)
                elif label in ("?123", "ABC"):
                    btn.connect("clicked", self.on_toggle_symbols)
                elif label == "Space":
                    btn.connect("clicked", self.on_key_clicked, " ")
                elif label in ("Cancel",):
                    btn.connect("clicked", self.on_cancel)
                elif label == "Clear":
                    btn.connect("clicked", self.on_clear)
                else:
                    btn.connect("clicked", self.on_key_clicked, display_label)

                self.grid.attach(btn, col_offset, r, span, 1)
                col_offset += span

    def on_display_changed(self, editable):
        self.entry.set_text(self.display_entry.get_text())

    def on_key_clicked(self, button, char):
        text = self.display_entry.get_text()
        new_text = text + char
        self.display_entry.set_text(new_text)
        self.display_entry.set_position(len(new_text))

        if self.mode == "shift":
            col = getattr(button, 'grid_col', 0)
            row = getattr(button, 'grid_row', 0)

            self.mode = "lower"
            self.build_keys()

            new_btn = self.grid.get_child_at(col, row)
            if new_btn:
                new_btn.grab_focus()

    def on_backspace(self, button):
        text = self.display_entry.get_text()
        if len(text) > 0:
            new_text = text[:-1]
            self.display_entry.set_text(new_text)
            self.display_entry.set_position(len(new_text))

    def on_toggle_mode(self, button, mode_type):
        col = getattr(button, 'grid_col', 0)
        row = getattr(button, 'grid_row', 0)

        target_mode = mode_type.lower()
        if self.mode == target_mode:
            self.mode = "lower"
        else:
            self.mode = target_mode

        self.build_keys()

        new_btn = self.grid.get_child_at(col, row)
        if new_btn:
            new_btn.grab_focus()

    def on_toggle_symbols(self, button):
        col = getattr(button, 'grid_col', 0)
        row = getattr(button, 'grid_row', 0)

        if self.mode == "symbols":
            self.mode = "lower"
        else:
            self.mode = "symbols"

        self.build_keys()

        new_btn = self.grid.get_child_at(col, row)
        if new_btn:
            new_btn.grab_focus()

    def on_clear(self, button):
        self.display_entry.set_text("")
        self.display_entry.set_position(0)

    def on_enter(self, button):
        self.entry.emit("activate")
        self._close()

    def on_cancel(self, button):
        self.entry.set_text(self.original_text)
        self.display_entry.set_text(self.original_text)
        self._close()

    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CANCEL:
            self.entry.set_text(self.original_text)
            self.display_entry.set_text(self.original_text)
        self._close()

    def _close(self):
        callback = self.on_close
        self.destroy()
        if callback:
            callback()
