#!/usr/bin/python3

import threading
from evdev import InputDevice, categorize, ecodes, list_devices
from pynput.keyboard import Key, Controller
import time

class GamepadApp:
    def __init__(self):
        self.keyboard = Controller()
        self.gamepad = None  # Variable to store the connected gamepad
        self.gamepad_thread = None  # Gamepad monitoring thread

        # Start monitoring for the gamepad
        self.start_monitoring()

    def find_gamepad(self):
        devices = [InputDevice(path) for path in list_devices()]
        for device in devices:
            # Check if the device has key or directional events
            capabilities = device.capabilities()
            if ecodes.EV_KEY in capabilities or ecodes.EV_ABS in capabilities:
                return device
        return None

    def start_monitoring(self):
        """Starts continuous monitoring of the gamepad"""
        self.check_gamepad()  # Initially check for gamepad
        # Continuously check for gamepad connectivity in a loop
        self.monitor_gamepad_connectivity()

    def monitor_gamepad_connectivity(self):
        """Check gamepad connectivity every 1 second"""
        while True:
            self.check_gamepad()
            time.sleep(1)  # Wait 1 second between checks

    def check_gamepad(self):
        """Check if the gamepad is connected or reconnected"""
        new_gamepad = self.find_gamepad()
        if new_gamepad and new_gamepad != self.gamepad:
            print(f"{new_gamepad.name} connected.")
            self.gamepad = new_gamepad
            if self.gamepad_thread:
                self.gamepad_thread.join()  # Wait for the previous thread to finish
            self.gamepad_thread = threading.Thread(target=self.monitor_gamepad, daemon=True)
            self.gamepad_thread.start()
        elif not new_gamepad and self.gamepad:
            print("Gamepad disconnected.")
            self.gamepad = None  # Reset the gamepad

    def monitor_gamepad(self):
        try:
            if not self.gamepad:
                return

            # Variable to control the printing of direction logs
            last_direction = None
            last_direction_time = None
            direction_interval = 0.2  # Time interval between prints (in seconds)

            for event in self.gamepad.read_loop():
                if event.type != ecodes.EV_KEY and event.type != ecodes.EV_ABS:
                    continue

                key_event = categorize(event)
                button_code = event.code
                current_state = event.value

                # Limit printing of button events
                if current_state == 1:  # Button pressed
                    if button_code == 304:  # X
                        self.keyboard.press(Key.enter)
                        self.keyboard.release(Key.enter)
                    elif button_code == 305:  # Circle
                        self.keyboard.press(Key.esc)
                        self.keyboard.release(Key.esc)
                    elif button_code == 307:  # Square
                        pass
                    elif button_code == 308:  # Triangle
                        pass

                # Process events for direction (if they are of type EV_ABS)
                if event.type == ecodes.EV_ABS:
                    # Filter only events from the D-pad axes, ignoring joystick axes
                    if event.code == ecodes.ABS_HAT0X:  # D-pad horizontal
                        if event.value < 0:
                            self.keyboard.press(Key.left)
                            self.keyboard.release(Key.left)
                        elif event.value > 0:
                            self.keyboard.press(Key.right)
                            self.keyboard.release(Key.right)
                    elif event.code == ecodes.ABS_HAT0Y:  # D-pad vertical
                        if event.value < 0:
                            self.keyboard.press(Key.up)
                            self.keyboard.release(Key.up)
                        elif event.value > 0:
                            self.keyboard.press(Key.down)
                            self.keyboard.release(Key.down)

        except Exception as e:
            print(f"Error accessing the gamepad: {e}")

def main():
    GamepadApp()
    # Keeps the monitoring running
    threading.Event().wait()

if __name__ == "__main__":
    main()
