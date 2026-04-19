import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

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
    def __init__(self, parent, entry):
        super().__init__(title="Faugus Launcher", transient_for=parent, modal=True)

        self.entry = entry
        self.mode = "lower"
        self.original_text = self.entry.get_text()

        #self.set_default_size(800, 450)
        self.set_resizable(False)
        self.get_style_context().add_class("tv-keyboard")
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
        vbox.pack_start(self.display_entry, False, False, 0)

        self.grid = Gtk.Grid(row_spacing=8, column_spacing=8)
        self.grid.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(self.grid, True, True, 0)

        self.build_keys()
        self.show_all()
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
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def build_keys(self):
        for child in self.grid.get_children():
            self.grid.remove(child)

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

                if (label == "Shift" and self.mode == "shift") or \
                   (label == "Caps" and self.mode == "caps") or \
                   (label in ("?123", "ABC") and self.mode == "symbols"):
                    btn.get_style_context().add_class("suggested-action")

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
            self.mode = "lower"
            self.build_keys()
            self.show_all()

    def on_backspace(self, button):
        text = self.display_entry.get_text()
        if len(text) > 0:
            new_text = text[:-1]
            self.display_entry.set_text(new_text)
            self.display_entry.set_position(len(new_text))

    def on_toggle_mode(self, button, mode_type):
        target_mode = mode_type.lower()
        if self.mode == target_mode:
            self.mode = "lower"
        else:
            self.mode = target_mode
        self.build_keys()
        self.show_all()

    def on_toggle_symbols(self, button):
        if self.mode == "symbols":
            self.mode = "lower"
        else:
            self.mode = "symbols"
        self.build_keys()
        self.show_all()

    def on_clear(self, button):
        self.display_entry.set_text("")
        self.display_entry.set_position(0)

    def on_enter(self, button):
        self.entry.emit("activate")
        self.destroy()

    def on_cancel(self, button):
        self.entry.set_text(self.original_text)
        self.display_entry.set_text(self.original_text)
        self.destroy()

    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CANCEL:
            self.entry.set_text(self.original_text)
            self.display_entry.set_text(self.original_text)
        self.destroy()
