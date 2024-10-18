"""
client program for a shooter game
"""

import socket
from select import select

from json_socket import JSONSocket
import argparse
import curses
from time import sleep
import selectors
from transaction import Transaction
from client_transactions import *

class GameBoard:

        def __init__(self, game_client, rows, cols):
            """
            Initialize the game board
            :param width: the width of the game board
            :param height: the height of the game board
            """
            print(f"Initializing game board with size {rows}x{cols}")
            self.game_client = game_client
            self.rows = rows
            self.cols = cols
            self.stdscr = curses.initscr()
            curses.curs_set(0)
            curses.noecho()
            curses.cbreak()
            curses.start_color()
            curses.use_default_colors()
            for i in range(0, curses.COLORS):
                curses.init_pair(i + 1, i, -1)
            self.stdscr.keypad(True)
            self.outer_board = curses.newwin(rows + 2, cols + 2, 0, 0)
            self.main_board = curses.newwin(rows, cols, 1, 1)
            self.outer_board.border()
            self.health_bar = curses.newwin(1, cols + 2, rows + 2, 0)
            self.status_bar = curses.newwin(1, cols + 2, rows + 3, 0)
            self.debug_bar  = curses.newwin(1, cols + 2, rows + 4, 0)
            self.status_bar.keypad(True)
            self.status_bar.addstr(0, 0, "Welcome to the game!")
            self.status_bar.refresh()

            self.main_board.refresh()
            self.outer_board.refresh()

        def print_game_state(self, game_state):
            """
            Print the game state
            :param game_state: the game state
            """
            self.main_board.clear()
            # each object is a quadruplet (row, col, char, color)
            for obj in game_state:
                try:
                    self.main_board.addch(*obj[:3], curses.color_pair(obj[3]))
                except curses.error:
                    self.debug_bar.clear()
                    self.debug_bar.addstr(0, 0, f"Error adding object {obj}")
                    self.debug_bar.refresh()
            self.main_board.refresh()

        def update_game_state(self, game_state):
            """
            Update the game state
            :param game_state: the game state
            """
            self.print_game_state(game_state)

        def __del__(self):
            curses.endwin()



class GameClient:

    def __init__(self, ip, port, player_name, player_character):
        """
        Initialize the game
        :param ip: the ip address of the server
        :param port: the port of the server
        :param player_name: the name of the player
        :param player_character: the character of the player, can be any character or emoji
        """
        self.server_ip = ip
        self.server_port = port
        self.is_game_over = False
        print(f"Connecting to server {ip}:{port}")
        self.socket = JSONSocket.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.connect((ip, port))
        except ConnectionRefusedError:
            print("Server is not up!")
            exit(1)
        print("Connected to server!")
        handshake_payload = {
            "type": "handshake",
            "player_name": player_name,
            "player_character": player_character

        }
        print(f"Sending handshake...")
        self.socket.send_json(handshake_payload)
        self.player_name = player_name
        print("Waiting for handshake ack...")
        response = self.socket.recv_json()
        if response["type"] == "handshake_ack" and response["success"]:
            print("Handshake successful!")
        else:
            print("Handshake failed!")
            print(f"Reason: {response.get('fail_reason', 'Unknown')}")
            self.socket.close()
            exit(1)

        game_size = response["game_size"]

        print("Waiting for game start")

        game_start_response = self.socket.recv_json()
        if game_start_response["type"] == "game_start":
            print("Game start!")
        else:
            print("Game start failed!")
            self.socket.close()
            return

        self.game_board = GameBoard(self, *game_size)

        self.transactions = {}

        self.run()

    def handle_unknown_message(self, data):
        self.game_board.debug_bar.clear()
        self.game_board.debug_bar.addstr(0, 0, f"Unknown message: {data['type']}")
        self.game_board.debug_bar.refresh()

    def handle_server_message(self):
        self.game_board.debug_bar.clear()
        self.game_board.debug_bar.addstr(0, 0, f"Server sent something")
        self.game_board.debug_bar.refresh()
        data = self.socket.recv_json()
        self.game_board.debug_bar.clear()
        self.game_board.debug_bar.addstr(0, 0, f"Got: {str(data)[:20]}")
        self.game_board.debug_bar.refresh()
        tid = tuple(data["tid"])
        if tid in self.transactions:
            transaction = self.transactions[tid]
            transaction.handle(data)
        else:
            handler = date_type_handlers.get(data["type"], self.handle_unknown_message)
            transaction = Transaction(self, data["tid"][1], self.socket, handler, tid[0])
            self.transactions[tid] = transaction
            transaction.handle(data)

    def handle_user_input(self):
        key = self.game_board.status_bar.getch()
        key_name = curses.keyname(key)
        transaction = Transaction(self, self.player_name, self.socket, keypress_handler)
        self.transactions[(transaction.transaction_id, self.player_name)] = transaction
        transaction.handle(key)
        self.game_board.debug_bar.clear()
        self.game_board.debug_bar.addstr(0, 0, f"Key pressed: {key_name}")
        self.game_board.debug_bar.refresh()

    def run(self):

        while not self.is_game_over:
            # wait for the server to send something,
            # or wait for the user to press a key
            self.game_board.debug_bar.clear()
            self.game_board.debug_bar.addstr(0, 0, "Waiting for server or user input.")
            self.game_board.debug_bar.refresh()
            selector = selectors.DefaultSelector()
            selector.register(self.socket, selectors.EVENT_READ, data=GameClient.handle_server_message)
            selector.register(0, selectors.EVENT_READ, data=GameClient.handle_user_input)
            self.game_board.debug_bar.addstr(" ready!")
            self.game_board.debug_bar.refresh()
            events = selector.select()
            for key, mask in events:
                if self.is_game_over:
                    break
                if key.data:
                    key.data(self)
                else:
                    self.game_board.debug_bar.clear()
                    self.game_board.debug_bar.addstr(0, 0, f"Unknown event")
                    self.game_board.debug_bar.refresh()

        self.game_board.status_bar.getch()

def parse_args():
    parser = argparse.ArgumentParser(description="Game client")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="The IP address of the server")
    parser.add_argument("--port", type=int, default=12345, help="The port of the server")
    parser.add_argument("--player_name", type=str, help="The name of the player")
    parser.add_argument("--player_character", type=str, help="The character of the player")
    args = parser.parse_args()
    return args

def main():
    args = parse_args()
    client = GameClient(args.ip, args.port, args.player_name, args.player_character)

if __name__ == "__main__":
    main()