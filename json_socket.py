"""
Helper class for reading and writing JSON data over a socket.
"""

import json
from socket import socket
import signal

INT_SIZE = 4

class JSONSocket:

    def __init__(self, sock: socket):
        self.sock = sock

    @staticmethod
    def create_socket(*args, **kwargs):
        """
        Create a new socket.
        :param args: the arguments to pass to the socket constructor
        :param kwargs: the keyword arguments to pass to the socket constructor
        :return: the new socket
        """
        return JSONSocket(socket(*args, **kwargs))

    def send_json(self, data: dict):
        """
        Send a JSON object over a socket.
        :param self: the socket to send the data over
        :param data: the data to send
        """
        json_data = json.dumps(data)
        json_bytes = json_data.encode()
        data_size = len(json_bytes)
        size_bytes = data_size.to_bytes(INT_SIZE, byteorder="big")
        self.sendall(size_bytes)
        self.sendall(json_bytes)

    def recv_json(self):
        """
        Receive a JSON object over a socket.
        :param self: the socket to receive the data from
        :return: the received data
        """
        size_bytes = self.recv(INT_SIZE)
        data_size = int.from_bytes(size_bytes, byteorder="big")
        json_bytes = b""
        while len(json_bytes) < data_size:
            packet = self.recv(data_size - len(json_bytes))
            if not packet:
                return None
            json_bytes += packet


        json_data = json_bytes.decode()

        try:
            data = json.loads(json_data)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Error decoding JSON: '{json_data}', Error: {e}")
        return data

    def __getattr__(self, item):
        return getattr(self.sock, item)
