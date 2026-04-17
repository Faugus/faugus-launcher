import pygame
from gi.repository import GLib, Gtk

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
    if not self.is_active():
        pygame.event.clear()
        return True

    for event in pygame.event.get():
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

        # --- D-PAD ---
        elif event.type == pygame.JOYHATMOTION:
            x, y = event.value
            if y == 1: self.child_focus(Gtk.DirectionType.UP)
            elif y == -1: self.child_focus(Gtk.DirectionType.DOWN)
            if x == -1: self.child_focus(Gtk.DirectionType.LEFT)
            elif x == 1: self.child_focus(Gtk.DirectionType.RIGHT)

        # --- JOYSTICK ---
        elif event.type == pygame.JOYAXISMOTION:

            # Y-AXIS
            if event.axis == 1:
                if self.can_move_y:
                    if event.value < -self.axis_threshold:
                        self.child_focus(Gtk.DirectionType.UP)
                        self.can_move_y = False
                    elif event.value > self.axis_threshold:
                        self.child_focus(Gtk.DirectionType.DOWN)
                        self.can_move_y = False
                elif abs(event.value) < self.reset_threshold:
                    self.can_move_y = True

            # X-AXIS
            elif event.axis == 0:
                if self.can_move_x:
                    if event.value < -self.axis_threshold:
                        self.child_focus(Gtk.DirectionType.LEFT)
                        self.can_move_x = False
                    elif event.value > self.axis_threshold:
                        self.child_focus(Gtk.DirectionType.RIGHT)
                        self.can_move_x = False
                elif abs(event.value) < self.reset_threshold:
                    self.can_move_x = True

        # --- BUTTONS ---
        elif event.type == pygame.JOYBUTTONDOWN:
            if event.button == 0: # A / X
                activate_focused_widget(self)
            # elif event.button == 1: # B / Circle
            #     self.close()

    return True

def activate_focused_widget(self):
    focused = self.get_focus()
    if not focused:
        return

    elif isinstance(focused, Gtk.FlowBoxChild):
        game = self.selected()
        if not game:
            return

        if game.gameid in self.running:
            self.running_dialog(game.title)
        else:
            self.on_button_play_clicked()
