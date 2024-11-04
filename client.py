"""
client program for a shooter game
"""

import socket
from ast import parse
from select import select

from json_socket import JSONSocket
import argparse
import curses
from time import sleep
import selectors
from transaction import Transaction
from client_transactions import *
import keys

ENABLE_DEBUG_BAR = False

keys_mapping = {
    119: keys.MOVE_UP,  # 'w'
    115: keys.MOVE_DOWN,  # 's'
    97: keys.MOVE_LEFT,  # 'a'
    100: keys.MOVE_RIGHT,  # 'd'
    curses.KEY_UP: keys.SHOOT_UP,
    curses.KEY_DOWN: keys.SHOOT_DOWN,
    curses.KEY_LEFT: keys.SHOOT_LEFT,
    curses.KEY_RIGHT: keys.SHOOT_RIGHT
}

inverted_keys_mapping = {
    119: keys.SHOOT_UP,  # 'w'
    115: keys.SHOOT_DOWN,  # 's'
    97: keys.SHOOT_LEFT,  # 'a'
    100: keys.SHOOT_RIGHT,  # 'd'
    curses.KEY_UP: keys.MOVE_UP,
    curses.KEY_DOWN: keys.MOVE_DOWN,
    curses.KEY_LEFT: keys.MOVE_LEFT,
    curses.KEY_RIGHT: keys.MOVE_RIGHT
}

class GameBoard:
    player_count_label = "Players: "
    player_count_max_size = 3
    health_label = "Your health: "
    health_max_size = 5

    def __init__(self, game_client, rows, cols):
        """
        Initialize the game board
        :param width: the width of the game board
        :param height: the height of the game board
        """
        self.game_state = None
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
        mid_col = (cols + 2) // 2
        self.player_count_label = curses.newwin(1, mid_col, rows + 2, 0)
        self.player_count_label.addstr(0, 0, GameBoard.player_count_label)
        self.player_count_label.refresh()
        self.player_count_value = curses.newwin(1, GameBoard.player_count_max_size, rows + 2, len(GameBoard.player_count_label))
        self.cur_player_count = 0
        self.health_bar_label = curses.newwin(1, mid_col, rows + 2, mid_col)
        self.health_bar_label.addstr(0, 0, GameBoard.health_label)
        self.health_bar_label.refresh()
        self.health_bar_value = curses.newwin(1, GameBoard.health_max_size, rows + 2, mid_col + len(GameBoard.health_label))
        self.cur_health = 0
        self.status_bar = curses.newwin(1, cols + 2, rows + 3, 0)
        self.cur_status = "Welcome to the game!"
        self.debug_bar  = curses.newwin(1, cols + 2, rows + 4, 0)
        self.status_bar.keypad(True)
        self.status_bar.addstr(0, 0, self.cur_status)
        self.status_bar.refresh()
        self.players_health = {}

        self.main_board.refresh()
        self.outer_board.refresh()

    def print_game_state(self):
        """
        Print the game state
        :param game_state: the game state
        """
        self.main_board.erase()
        # each object is a quadruplet (row, col, char, color)
        for obj in self.game_state:
            try:
                self.main_board.addch(*obj[:3], curses.color_pair(obj[3]))
            except curses.error:
                if ENABLE_DEBUG_BAR:
                    self.debug_bar.erase()
                    self.debug_bar.addstr(0, 0, f"Error adding object {obj}")
                    self.debug_bar.refresh()
        self.main_board.refresh()

    def update_game_state(self, game_state):
        """
        Update the game state
        :param game_state: the game state
        """
        self.game_state = game_state
        self.print_game_state()

    def update_players_health(self, players_health):
        players_count = len(players_health)
        if players_count != self.cur_player_count:
            self.cur_player_count = players_count
            self.player_count_value.erase()
            self.player_count_value.addstr(0, 0, str(players_count))
            self.player_count_value.refresh()

        player_health = max(players_health.get(self.game_client.player_name, 0), 0)

        if player_health != self.cur_health:
            self.cur_health = player_health
            if player_health <= 25:
                color = 197 # red
            elif player_health <= 50:
                color = 227 # yellow
            else:
                color = 47 # green

            self.health_bar_value.erase()
            self.health_bar_value.addstr(0, 0, str(player_health), curses.color_pair(color))
            self.health_bar_value.refresh()

    def update_status(self, status):
        if status != self.cur_status:
            self.cur_status = status
            self.status_bar.erase()
            self.status_bar.addstr(0, 0, status)
            self.status_bar.refresh()


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
        print("\n═══════════════════════════════════════════\n")
        print("Welcome to the shooter game!")
        print("Use WASD to move, and arrow keys to shoot.")
        print("\n═══════════════════════════════════════════\n")
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

        loader_animation = "|/-\\"
        loader_index = 0

        print("Waiting for game start  ", end="")

        game_started = False

        while not game_started:
            selector = selectors.DefaultSelector()
            selector.register(self.socket, selectors.EVENT_READ, data=None)
            events = selector.select(timeout=.5)

            if events:
                for key, mask in events:
                    print(f"\b ")
                    game_start_response = self.socket.recv_json()
                    if game_start_response["type"] == "game_start":
                        print("Game start!")
                        game_started = True
                        break
                    else:
                        print("Game start failed!")
                        self.socket.close()
                        return

            else:
                print(f"\b{loader_animation[loader_index]}", end="", flush=True)
                loader_index = (loader_index + 1) % len(loader_animation)

        print()

        self.game_board = GameBoard(self, *game_size)

        self.transactions = {}

        self.run()

    def handle_unknown_message(self, data):
        if ENABLE_DEBUG_BAR:
            self.game_board.debug_bar.erase()
            self.game_board.debug_bar.addstr(0, 0, f"Unknown message: {data['type']}")
            self.game_board.debug_bar.refresh()

    def handle_server_message(self):
        if ENABLE_DEBUG_BAR:
            self.game_board.debug_bar.erase()
            self.game_board.debug_bar.addstr(0, 0, f"Server sent something")
            self.game_board.debug_bar.refresh()
        data = self.socket.recv_json()
        if ENABLE_DEBUG_BAR:
            self.game_board.debug_bar.erase()
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
        transaction.handle(keys_mapping.get(key, 0))
        if ENABLE_DEBUG_BAR:
            self.game_board.debug_bar.erase()
            self.game_board.debug_bar.addstr(0, 0, f"Key pressed: {key_name}")
            self.game_board.debug_bar.refresh()

    def run(self):

        while not self.is_game_over:
            # wait for the server to send something,
            # or wait for the user to press a key
            if ENABLE_DEBUG_BAR:
                self.game_board.debug_bar.erase()
                self.game_board.debug_bar.addstr(0, 0, "Waiting for server or user input.")
                self.game_board.debug_bar.refresh()
            selector = selectors.DefaultSelector()
            selector.register(self.socket, selectors.EVENT_READ, data=GameClient.handle_server_message)
            selector.register(0, selectors.EVENT_READ, data=GameClient.handle_user_input)
            if ENABLE_DEBUG_BAR:
                self.game_board.debug_bar.addstr(" ready!")
                self.game_board.debug_bar.refresh()
            events = selector.select()
            for key, mask in events:
                if self.is_game_over:
                    break
                if key.data:
                    key.data(self)
                else:
                    if ENABLE_DEBUG_BAR:
                        self.game_board.debug_bar.erase()
                        self.game_board.debug_bar.addstr(0, 0, f"Unknown event")
                        self.game_board.debug_bar.refresh()

        # wait a bit so users can see the endgame message
        sleep(3)
        self.game_board.status_bar.addstr(0, 0, "Press any key to exit")
        self.game_board.status_bar.refresh()
        curses.flushinp()
        self.game_board.status_bar.getch()

def parse_args():
    parser = argparse.ArgumentParser(description="Game client")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="The IP address of the server")
    parser.add_argument("--port", type=int, default=12345, help="The port of the server")
    parser.add_argument("--player_name", type=str, help="The name of the player")
    parser.add_argument("--player_character", type=str, help="The character of the player")
    parser.add_argument("--inverted_keys", action="store_true", help="Use inverted keys")
    args = parser.parse_args()
    return args

def main():
    args = parse_args()
    if args.inverted_keys:
        global keys_mapping
        keys_mapping = inverted_keys_mapping
    client = GameClient(args.ip, args.port, args.player_name, args.player_character)

if __name__ == "__main__":
    main()