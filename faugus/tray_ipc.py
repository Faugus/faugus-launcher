import os
import socket
from gi.repository import Gio, GLib
from faugus.path_manager import tray_socket

COMMAND_PRESENT = "PRESENT"
COMMAND_QUIT = "QUIT"
COMMAND_LAUNCH = "LAUNCH"


class TrayServer:
    def __init__(self, on_present, on_quit, on_launch):
        self.on_present = on_present
        self.on_quit = on_quit
        self.on_launch = on_launch
        self.service = None

    def start(self):
        if os.path.exists(tray_socket):
            os.remove(tray_socket)

        self.service = Gio.SocketService.new()
        address = Gio.UnixSocketAddress.new(tray_socket)
        self.service.add_address(address, Gio.SocketType.STREAM, Gio.SocketProtocol.DEFAULT, None)
        self.service.connect("incoming", self._on_incoming)
        self.service.start()

    def stop(self):
        if self.service:
            self.service.stop()
            self.service.close()
        if os.path.exists(tray_socket):
            os.remove(tray_socket)

    def _on_incoming(self, service, connection, source_object):
        stream = connection.get_input_stream()
        stream.read_bytes_async(4096, GLib.PRIORITY_DEFAULT, None, self._on_read, connection)
        return False

    def _on_read(self, stream, result, connection):
        try:
            data = stream.read_bytes_finish(result)
        except GLib.Error:
            return
        message = data.get_data().decode("utf-8").strip()
        command, _, arg = message.partition(":")
        if command == COMMAND_PRESENT:
            self.on_present()
        elif command == COMMAND_QUIT:
            self.on_quit()
        elif command == COMMAND_LAUNCH:
            self.on_launch(arg)


def send_command(command):
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2)
        client.connect(tray_socket)
        client.sendall(command.encode("utf-8"))
        client.close()
    except OSError:
        pass
