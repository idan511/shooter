from json_socket import JSONSocket
import socket
import threading
import argparse
from time import sleep
import selectors
from transaction import Transaction
from server_transactions import *
import curses
import time
import random

class ClientHandler:

    def __init__(self, client_socket: JSONSocket, client_address, game_server):
        print(f"New client on {client_address}")
        self.client_character = None
        self.client_name = None
        self.client_socket = client_socket
        self.client_address = client_address
        self.game_server = game_server

        self.handshake()

    def handshake(self):
        print("Waiting for handshake")
        client_payload = self.client_socket.recv_json()
        print(f"Received handshake: {client_payload}")
        if client_payload["type"] != "handshake":
            print("Invalid handshake")
            self.client_socket.close()
            return
        self.client_name = client_payload["player_name"]
        self.client_character = client_payload["player_character"]
        print(f"Received handshake from {self.client_name} with character {self.client_character}")
        handshake_ack_payload = {
            "type": "handshake_ack",
            "success": True,
            "game_size": self.game_server.game_size
        }
        self.client_socket.send_json(handshake_ack_payload)

class GameProjectile:
    def __init__(self, game, player, row, col, direction, ttl=20):
        self.row = row
        self.col = col
        self.ttl = ttl
        self.game = game
        self.player = player
        self.direction = direction

    def advance(self):
        raise NotImplementedError

    def character(self):
        raise NotImplementedError

    def damage(self):
        raise NotImplementedError

    def fire(self):
        self.game.projectiles.append(self)

    def color(self):
        return 0

class GameBullet(GameProjectile):
    def __init__(self, game, player, row, col, direction, ttl=20):
        super().__init__(game, player, row, col, direction, ttl)

    def advance(self):
        match self.direction:
            case "up":
                self.row -= 1
            case "down":
                self.row += 1
            case "left":
                self.col -= 1
            case "right":
                self.col += 1

        self.ttl -= 1

    def character(self):
        return "·"

    def damage(self):
        return 10

class GameBigBullet(GameProjectile):
    def __init__(self, game, player, row, col, direction, ttl=10):
        super().__init__(game, player, row, col, direction, ttl)

    def advance(self):
        match self.direction:
            case "up":
                self.row -= 1
            case "down":
                self.row += 1
            case "left":
                self.col -= 1
            case "right":
                self.col += 1

        self.ttl -= 1

    def character(self):
        return "●"

    def damage(self):
        return 20

class GameSingleLaser(GameProjectile):
    def __init__(self, game, player, row, col, direction, ttl=1):
        super().__init__(game, player, row, col, direction, ttl)

    def advance(self):
        match self.direction:
            case "up":
                self.row -= 2
            case "down":
                self.row += 2
            case "left":
                self.col -= 2
            case "right":
                self.col += 2

        self.ttl -= 1

    def character(self):
        match self.direction:
            case "up":
                return "│"
            case "down":
                return "│"
            case "left":
                return "─"
            case "right":
                return "─"

    def damage(self):
        return 3

    def color(self):
        return 204 # pale red

class GameLazer(GameProjectile):
    def __init__(self, game, player, row, col, direction, ttl=30):
        super().__init__(game, player, row, col, direction, ttl)

    def fire(self):
        # fire 3 single lasers in the direction of fire
        for i in range(3):
            projectile = GameSingleLaser(self.game, self.player, self.row, self.col, self.direction, self.ttl)
            projectile.fire()
            match self.direction:
                case "up":
                    self.row -= 1
                case "down":
                    self.row += 1
                case "left":
                    self.col -= 1
                case "right":
                    self.col += 1

class GameHomingMissile(GameProjectile):
    def __init__(self, game, player, row, col, direction, ttl=20, target=None):
        print("new homing missile")
        super().__init__(game, player, row, col, direction, ttl)
        if target is None:
            self.acquire_target()
        else:
            self.target = target

    def acquire_target(self):
        print("acquiring target")
        min_distance = float("inf")
        self.target = None
        for player_name, player in self.game.players.items():
            print(f"checking player {player_name} eq {self.player}")
            if player_name == self.player:
                continue
            distance = abs(player.row - self.row) + abs(player.col - self.col)
            if distance < min_distance:
                print(f"new target {player_name}")
                min_distance = distance
                self.target = player

    def advance(self):
        if self.target:
            if self.row < self.target.row:
                self.row += 1
            elif self.row > self.target.row:
                self.row -= 1
            elif self.col < self.target.col:
                self.col += 1
            elif self.col > self.target.col:
                self.col -= 1
        else:
            match self.direction:
                case "up":
                    self.row -= 1
                case "down":
                    self.row += 1
                case "left":
                    self.col -= 1
                case "right":
                    self.col += 1

        self.ttl -= 1

    def character(self):
        # purple bullet
        return "☼"

    def damage(self):
        return 5

    def color(self):
        return 136 # purple

class GamePlayer:
    def __init__(self, character, row, col, projectile_type=GameBullet):
        self.character = character
        self.row = row
        self.col = col
        self.projectile_type = projectile_type
        self.health = 100

    def color(self):
        return 0

class GamePowerup:
    def __init__(self, row, col, ttl):
        self.row = row
        self.col = col
        self.ttl = ttl

    def apply(self, player):
        raise NotImplementedError

    def character(self):
        raise NotImplementedError

    def color(self):
        return 0

class GameHealthPowerup(GamePowerup):
    def apply(self, player):
        player.health += 25

    def character(self):
        return "♥"

    def color(self):
        return 197 # red

class GameHomingMissilePowerup(GamePowerup):
    def apply(self, player):
        player.projectile_type = GameHomingMissile

    def character(self):
        return "⌾"

    def color(self):
        return 136 # purple

class GameBigBulletPowerup(GamePowerup):
    def apply(self, player):
        player.projectile_type = GameBigBullet

    def character(self):
        return "●"

class GameLazerPowerup(GamePowerup):
    def apply(self, player):
        player.projectile_type = GameLazer

    def character(self):
        return "/"

    def color(self):
        return 204 # pale red

class GameBoard:
    def __init__(self, game_server, rows, cols):
        self.game_server = game_server
        self.rows = rows
        self.cols = cols
        self.players = {}
        self.projectiles = []
        self.powerups = []
        self.status = "What a game :)"

    def add_player(self, player_name, player_character, row, col):
        self.players[player_name] = GamePlayer(player_character, row, col)

    def remove_player(self, player_name):
        del self.players[player_name]

    def update(self):
        # give a small chance for a powerup to spawn
        if random.random() < 0.01:
            row = random.randint(0, self.rows - 1)
            col = random.randint(0, self.cols - 1)
            powerup_ttl = random.randint(100, 200)
            powerup = random.choice([GameHealthPowerup,
                                     GameHomingMissilePowerup,
                                     GameBigBulletPowerup,
                                     GameLazerPowerup])(row, col, powerup_ttl)
            self.powerups.append(powerup)

        for projectile in self.projectiles:
            projectile.advance()
            if projectile.ttl <= 0:
                continue
            if projectile.row < 0 or projectile.row >= self.rows or projectile.col < 0 or projectile.col >= self.cols:
                self.projectiles.remove(projectile)
            for player_name, player in list(self.players.items()):
                if player.row == projectile.row and player.col == projectile.col:
                    player.health -= projectile.damage()
                    self.projectiles.remove(projectile)
                    self.status = f"{player_name} was hit by a projectile!"

        for powerup in self.powerups:
            powerup.ttl -= 1
            if powerup.ttl <= 0:
                continue
            for player_name, player in list(self.players.items()):
                if player.row == powerup.row and player.col == powerup.col:
                    powerup.apply(player)
                    self.powerups.remove(powerup)
                    self.status = f"{player_name} picked up a powerup!"

        for projectile in self.projectiles:
            if projectile.ttl <= 0:
                self.projectiles.remove(projectile)

        for powerup in self.powerups:
            if powerup.ttl <= 0:
                self.powerups.remove(powerup)

        for player_name, player in list(self.players.items()):
            if player.health <= 0:
                self.remove_player(player_name)
                self.status = f"{player_name} died!!!!"

        if len(self.players) == 1:
            self.status = f"{list(self.players.keys())[0]} is the winner!"

    def get_game_state(self):
        game_state = []
        players_health = {}
        for player_name, player in self.players.items():
            game_state.append((int(player.row), int(player.col), player.character, player.color()))
            players_health[player_name] = player.health
        for projectile in self.projectiles:
            projectile_character = projectile.character()
            if isinstance(projectile_character, str):
                game_state.append((int(projectile.row), int(projectile.col), projectile_character, projectile.color()))
            else: # it's a list
                game_state.append(projectile_character)
        for powerup in self.powerups:
            game_state.append((int(powerup.row), int(powerup.col), powerup.character(), powerup.color()))
        return game_state, players_health, self.status

    def player_action(self, player, action):
        match action:
            case 119: # 'w'
                if self.players[player].row > 0:
                    self.players[player].row -= 1
                    print(f"{player} moved up ({self.players[player].row}, {self.players[player].col})")

            case 115: # 's'
                if self.players[player].row < self.rows - 1:
                    self.players[player].row += 1
                    print(f"{player} moved down ({self.players[player].row}, {self.players[player].col})")

            case 97: # 'a'
                if self.players[player].col > 0:
                    self.players[player].col -= 1
                    print(f"{player} moved left ({self.players[player].row}, {self.players[player].col})")


            case 100: # 'd'
                if self.players[player].col < self.cols - 1:
                    self.players[player].col += 1
                    print(f"{player} moved right ({self.players[player].row}, {self.players[player].col})")

            case curses.KEY_UP:
                projectile = self.players[player].projectile_type(self, player, self.players[player].row - 1, self.players[player].col, "up")
                projectile.fire()

            case curses.KEY_DOWN:
                projectile = self.players[player].projectile_type(self, player, self.players[player].row + 1, self.players[player].col, "down")
                projectile.fire()

            case curses.KEY_LEFT:
                projectile = self.players[player].projectile_type(self, player, self.players[player].row, self.players[player].col - 1, "left")
                projectile.fire()

            case curses.KEY_RIGHT:
                projectile = self.players[player].projectile_type(self, player, self.players[player].row, self.players[player].col + 1, "right")
                projectile.fire()


class GameServer:

    def __init__(self, ip, port, max_players, game_size):
        self.game_started = False
        self.clients_lock = None
        self.client_threads = None
        print(f"Starting server on {ip}:{port}, max players: {max_players}, game size: {game_size}")
        self.server_socket = None
        self.clients = None
        self.clients_acceptor = None
        self.ip = ip
        self.port = port
        self.max_players = max_players
        self.game_size = game_size
        self.transactions = {}
        self.game_board = GameBoard(self, *game_size)

    def run(self):
        print("Creating server socket")
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print("Binding server socket")
        self.server_socket.bind((self.ip, self.port))
        print("Listening for connections")
        self.server_socket.listen(self.max_players)
        self.clients = {}
        self.client_threads = {}
        self.clients_acceptor = threading.Thread(target=GameServer.accept_clients, args=(self,))
        self.clients_acceptor.start()
        self.clients_lock = threading.Lock()
        print("clients acceptor started, press enter to start game loop")
        input()
        print("Starting...")
        self.game_started = True
        self.clients_acceptor.join()
        for client in self.clients.values():
            client.client_socket.send_json({
                "type": "game_start"
            })
        selector_timeout = 0.01
        game_refresh_interval = 0.05
        last_update_time = time.time()

        while True:
            clients_selector = selectors.DefaultSelector()
            with self.clients_lock:
                cur_clients = self.clients.copy()

            for client in cur_clients.values():
                clients_selector.register(client.client_socket, selectors.EVENT_READ, client)

            events = clients_selector.select(timeout=selector_timeout)
            current_time = time.time()

            for key, mask in events:
                client = key.data
                data = client.client_socket.recv_json()
                # print(f"Received data from {client.client_name}: {data}")
                tid = tuple(data["tid"])
                if tid in self.transactions:
                    # print(f"Continuing transaction {tid}")
                    transaction = self.transactions[tid]
                    transaction.handle(data)
                else:
                    # print(f"New transaction {tid}")
                    try:
                        transaction = Transaction(self, tid[1], client.client_socket, date_type_handlers[data["type"]], tid=tid[0])
                        self.transactions[tid] = transaction
                        transaction.handle(data)
                    except KeyError:
                        print(f"Unknown message type: {data['type']}")
                        response = {
                            "tid": data["tid"],
                            "type": "unknown_message"
                        }
                        client.client_socket.send_json(response)

            if current_time - last_update_time >= game_refresh_interval:
                self.game_board.update()
                game_state = self.game_board.get_game_state()
                for client in cur_clients.values():
                    transaction = Transaction(self, "self", client.client_socket, send_game_state)
                    self.transactions[(transaction.transaction_id, "self")] = transaction
                    transaction.handle(game_state)
                last_update_time = current_time

                if len(self.game_board.players) == 1:
                    winner = list(self.game_board.players.keys())[0]
                    print(f"Game over, winner: {winner}")
                    for client in cur_clients.values():
                        transaction = Transaction(self, "self", client.client_socket, endgame_handler)
                        transaction.handle(winner)
                    break


    def __del__(self):
        if self.clients:
            print("Closing client sockets")
            for client in self.clients.values():
                client.client_socket.close()
        if self.server_socket:
            print("Closing server socket")
            self.server_socket.close()

    def accept_clients(self):
        while not self.game_started:
            self.server_socket.settimeout(2)
            try:
                client_socket, client_address = self.server_socket.accept()
                if len(self.clients) >= self.max_players:
                    print(f"Rejected connection from {client_address}, too many players")
                    client_socket.close()
                    continue
                client_socket = JSONSocket(client_socket)
                client_handler = ClientHandler(client_socket, client_address, self)
                with self.clients_lock:
                    self.clients[client_handler.client_name] = client_handler
                    self.game_board.add_player(client_handler.client_name, client_handler.client_character, random.randint(0, self.game_size[0] - 1), random.randint(0, self.game_size[1] - 1))
                print(f"Accepted connection from {client_address}")
            except TimeoutError:
                continue


def parse_args():
    parser = argparse.ArgumentParser(description="Run a game server")
    parser.add_argument("--ip", default="0.0.0.0", type=str, help="The IP address of the server")
    parser.add_argument("--port", default=12345, type=int, help="The port of the server")
    parser.add_argument("--max-players", default=4, type=int, help="The maximum number of players")
    parser.add_argument("--game-size", default=[30, 80], type=int, nargs=2,
                        help="The size of the game board, in format rows cols")

    return parser.parse_args()


def main():
    args = parse_args()

    server = GameServer(args.ip, args.port, args.max_players, args.game_size)

    server.run()


if __name__ == "__main__":
    main()
