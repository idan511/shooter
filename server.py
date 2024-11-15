from json_socket import JSONSocket
import socket
import threading
import argparse
import selectors
from transaction import Transaction
from server_transactions import *
import time
import random
import keys

POWERUP_SPAWN_CHANCE = 0.01
END_GAME_ON_SINGLE_PLAYER = True
GAME_REFRESH_INTERVAL = 1 / 15  # 30 FPS
MOVE_INTERVAL = GAME_REFRESH_INTERVAL

BANNED_CHARACTERS = {"\n", "\r", "\t", "\b", "\f", "\v", " ", ":", ";", ",", "."}


class ClientHandler:

    def __init__(self, client_socket: JSONSocket, client_address, game_server):
        print(f"New client on {client_address}")
        self.client_character = None
        self.client_name = None
        self.client_socket = client_socket
        self.client_address = client_address
        self.game_server = game_server

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
            "success": True
        }
        if not self.client_name.isalnum():
            print(f"Rejected connection from {self.client_address}, invalid player name")
            handshake_ack_payload["success"] = False
            handshake_ack_payload["fail_reason"] = "Invalid player name, must be alphanumeric"
        elif self.client_name.lower() in [client.client_name.lower() for client in self.game_server.clients.values()]:
            print(f"Rejected connection from {self.client_address}, duplicate player name")
            handshake_ack_payload["success"] = False
            handshake_ack_payload["fail_reason"] = "Duplicate player name"
        elif self.game_server.game_started:
            print(f"Rejected connection from {self.client_address}, game already started")
            handshake_ack_payload["success"] = False
            handshake_ack_payload["fail_reason"] = "Game already started"
        elif len(self.client_character) != 1:
            print(f"Rejected connection from {self.client_address}, invalid character")
            handshake_ack_payload["success"] = False
            handshake_ack_payload["fail_reason"] = "Invalid character, must be a single character"
        elif self.client_character in BANNED_CHARACTERS:
            print(f"Rejected connection from {self.client_address}, banned character")
            handshake_ack_payload["success"] = False
            handshake_ack_payload["fail_reason"] = "Banned character"
        elif self.client_character in [player.character for player in self.game_server.game_board.players.values()]:
            print(f"Rejected connection from {self.client_address}, duplicate character")
            handshake_ack_payload["success"] = False
            handshake_ack_payload["fail_reason"] = "Duplicate character"

        if handshake_ack_payload["success"]:
            handshake_ack_payload["game_size"] = self.game_server.game_size

        self.client_socket.send_json(handshake_ack_payload)

        return handshake_ack_payload["success"]


class GameProjectile:
    interval = GAME_REFRESH_INTERVAL * 2

    def __init__(self, game, player, row, col, direction, ttl=20):
        self.row = row
        self.col = col
        self.ttl = ttl
        self.game = game
        self.player = player
        self.direction = direction

    def get_player_object(self):
        return self.game.players[self.player]

    def advance(self):
        raise NotImplementedError

    def character(self):
        raise NotImplementedError

    def damage(self):
        raise NotImplementedError

    def fire(self):
        self.get_player_object().last_shot_time = time.time()
        self.game.projectiles.append(self)

    def color(self):
        return 0


class GameBullet(GameProjectile):
    interval = GameProjectile.interval

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


class GameStaticBullet(GameBullet):
    interval = GameBullet.interval

    def __init__(self, game, player, row, col, ttl=20):
        super().__init__(game, player, row, col, "none", ttl)

    def fire(self):
        self.game.projectiles.append(self)

    def advance(self):
        self.ttl -= 1


class GameBigBullet(GameProjectile):
    interval = GameProjectile.interval * 1.1

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
        return 204  # pale red


class GameLazer(GameProjectile):
    interval = GameProjectile.interval * 0.5

    def __init__(self, game, player, row, col, direction, ttl=30):
        super().__init__(game, player, row, col, direction, ttl)

    def fire(self):
        # fire 3 single lasers in the direction of fire
        self.get_player_object().last_shot_time = time.time()
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


class GameExplosiveBullet(GameProjectile):
    interval = GameProjectile.interval * 2

    def __init__(self, game, player, row, col, direction, ttl=15, explosion_max_radius=4):
        super().__init__(game, player, row, col, direction, ttl)
        self.explosion_max_radius = explosion_max_radius

    def create_explosion(self, row, col):
        if 0 <= row < self.game.rows and 0 <= col < self.game.cols:
            projectile = GameStaticBullet(self.game, self.player, row, col, 2)
            projectile.fire()

    def advance(self):
        if self.ttl > self.explosion_max_radius:
            match self.direction:
                case "up":
                    self.row -= 1
                case "down":
                    self.row += 1
                case "left":
                    self.col -= 1
                case "right":
                    self.col += 1
        else:
            # explode
            radius = self.explosion_max_radius - self.ttl
            for i in range(-radius, radius + 1):
                if i == -radius or i == radius:
                    for j in range(-radius, radius + 1):
                        self.create_explosion(self.row + i, self.col + j)
                else:
                    self.create_explosion(self.row + i, self.col - radius)
                    self.create_explosion(self.row + i, self.col + radius)

        self.ttl -= 1

    def character(self):
        if self.ttl > self.explosion_max_radius:
            match self.direction:
                case "up":
                    return "▵"
                case "down":
                    return "▿"
                case "left":
                    return "◃"
                case "right":
                    return "▹"
        else:
            return "◌"

    def damage(self):
        return 15


class GameHomingMissile(GameProjectile):
    interval = GameProjectile.interval * 1.5

    def __init__(self, game, player, row, col, direction, ttl=20, target=None):
        print("new homing missile")
        super().__init__(game, player, row, col, direction, ttl)
        self.move_ticker = False
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
            if self.move_ticker:
                if self.row < self.target.row:
                    self.row += 1
                elif self.row > self.target.row:
                    self.row -= 1
                elif self.col < self.target.col:
                    self.col += 1
                elif self.col > self.target.col:
                    self.col -= 1
            else:
                if self.col < self.target.col:
                    self.col += 1
                elif self.col > self.target.col:
                    self.col -= 1
                elif self.row < self.target.row:
                    self.row += 1
                elif self.row > self.target.row:
                    self.row -= 1

            self.move_ticker = not self.move_ticker
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
        return 136  # purple


class StatusEffect:
    def __init__(self, player, ttl):
        self.ttl = ttl
        self.player = player
        player.status_effects.add(self)
        self.start()

    def start(self):
        print("Status effect started")

    def step(self):
        self.ttl -= 1

        if self.ttl <= 0:
            self.end()
            return

    def end(self):
        print("Status effect ended")


class SpeedBoostStatusEffect(StatusEffect):
    def __init__(self, player, ttl=150):
        super().__init__(player, ttl)

    def start(self):
        print(f"Speed boost for {self.player}")
        self.player.step_size *= 2

    def step(self):
        super().step()

    def end(self):
        print(f"Speed boost ended for {self.player}")
        self.player.step_size /= 2


class GamePlayer:
    def __init__(self, character, row, col, projectile_type=GameBullet):
        self.character = character
        self.row = row
        self.col = col
        self.projectile_type = projectile_type
        self.health = 100
        self.step_size = 1
        self.last_move_time = time.time()
        self.last_shot_time = time.time()
        self.move_interval = MOVE_INTERVAL
        self.status_effects = set()

    def color(self):
        return 0

    def apply_statuses(self):
        for status in list(self.status_effects):
            status.step()

            if status.ttl <= 0:
                self.status_effects.remove(status)


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
        return 197  # red


class GameHomingMissilePowerup(GamePowerup):
    def apply(self, player):
        player.projectile_type = GameHomingMissile

    def character(self):
        return "⌾"

    def color(self):
        return 136  # purple


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
        return 204  # pale red


class GameExplosiveBulletPowerup(GamePowerup):
    def apply(self, player):
        player.projectile_type = GameExplosiveBullet

    def character(self):
        return "✢"


class GameSpeedBoostPowerup(GamePowerup):
    def apply(self, player):
        SpeedBoostStatusEffect(player)

    def character(self):
        return "⇑"

    def color(self):
        return 229  # yellow


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
        if player_name in self.players:
            del self.players[player_name]

    def update(self):
        # give a small chance for a powerup to spawn
        if random.random() < POWERUP_SPAWN_CHANCE:
            row = random.randint(0, self.rows - 1)
            col = random.randint(0, self.cols - 1)
            powerup_ttl = random.randint(100, 200)
            powerup = random.choice([GameHealthPowerup,
                                     GameHomingMissilePowerup,
                                     GameBigBulletPowerup,
                                     GameLazerPowerup,
                                     GameExplosiveBulletPowerup,
                                     GameSpeedBoostPowerup])(row, col, powerup_ttl)
            self.powerups.append(powerup)

        for projectile in self.projectiles:
            projectile.advance()
            if projectile.ttl <= 0:
                continue
            if projectile.row < 0 or projectile.row >= self.rows or projectile.col < 0 or projectile.col >= self.cols:
                self.projectiles.remove(projectile)
                continue
            for player_name, player in list(self.players.items()):
                if player.row == projectile.row and player.col == projectile.col:
                    player.health -= projectile.damage()
                    if projectile in self.projectiles:
                        self.projectiles.remove(projectile)
                    self.status = f"{player_name} was hit by a projectile!"

        for powerup in self.powerups:
            powerup.ttl -= 1
            if powerup.ttl <= 0:
                continue
            for player_name, player in list(self.players.items()):
                if player.row == powerup.row and player.col == powerup.col:
                    powerup.apply(player)
                    if powerup in self.powerups:
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

            player.apply_statuses()

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
            else:  # it's a list
                game_state.append(projectile_character)
        for powerup in self.powerups:
            game_state.append((int(powerup.row), int(powerup.col), powerup.character(), powerup.color()))
        return game_state, players_health, self.status

    def player_action(self, player, action):
        cur_time = time.time()
        player_obj = self.players[player]
        can_move = cur_time - player_obj.last_move_time >= player_obj.move_interval
        can_shoot = cur_time - player_obj.last_shot_time >= player_obj.projectile_type.interval
        match action:
            case keys.MOVE_UP:
                if player_obj.row > 0 and can_move:
                    player_obj.row -= player_obj.step_size
                    if player_obj.row < 0:
                        player_obj.row = 0
                    player_obj.last_move_time = cur_time
                    print(f"{player} moved up ({player_obj.row}, {player_obj.col})")

            case keys.MOVE_DOWN:
                if player_obj.row < self.rows - 1 and can_move:
                    player_obj.row += player_obj.step_size
                    if player_obj.row >= self.rows:
                        player_obj.row = self.rows - 1
                    player_obj.last_move_time = cur_time
                    print(f"{player} moved down ({player_obj.row}, {player_obj.col})")

            case keys.MOVE_LEFT:
                if player_obj.col > 0 and can_move:
                    player_obj.col -= player_obj.step_size
                    if player_obj.col < 0:
                        player_obj.col = 0
                    player_obj.last_move_time = cur_time
                    print(f"{player} moved left ({player_obj.row}, {player_obj.col})")

            case keys.MOVE_RIGHT:
                if player_obj.col < self.cols - 1 and can_move:
                    player_obj.col += player_obj.step_size
                    if player_obj.col >= self.cols:
                        player_obj.col = self.cols - 1
                    player_obj.last_move_time = cur_time
                    print(f"{player} moved right ({player_obj.row}, {player_obj.col})")

            case keys.SHOOT_UP if can_shoot:
                projectile = player_obj.projectile_type(self, player, player_obj.row - 1, player_obj.col, "up")
                projectile.fire()

            case keys.SHOOT_DOWN if can_shoot:
                projectile = player_obj.projectile_type(self, player, player_obj.row + 1, player_obj.col, "down")
                projectile.fire()

            case keys.SHOOT_LEFT if can_shoot:
                projectile = player_obj.projectile_type(self, player, player_obj.row, player_obj.col - 1, "left")
                projectile.fire()

            case keys.SHOOT_RIGHT if can_shoot:
                projectile = player_obj.projectile_type(self, player, player_obj.row, player_obj.col + 1, "right")
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
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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

        while not self.game_started:
            # wait for input, or just wait for the clients_acceptor to finish
            starter_selector = selectors.DefaultSelector()
            starter_selector.register(0, selectors.EVENT_READ)
            events = starter_selector.select(timeout=1)

            for key, mask in events:
                input()
                self.game_started = True

        print("Starting...")
        self.clients_acceptor.join()
        for client in self.clients.values():
            client.client_socket.send_json({
                "type": "game_start"
            })
        selector_timeout = 0.01
        last_update_time = time.time()

        while True:
            clients_selector = selectors.DefaultSelector()
            cur_clients = self.clients

            for client in cur_clients.values():
                clients_selector.register(client.client_socket, selectors.EVENT_READ, client)

            events = clients_selector.select(timeout=selector_timeout)
            current_time = time.time()

            for key, mask in events:
                client = key.data
                try:
                    data = client.client_socket.recv_json()
                except Exception as e:
                    error_type = type(e).__name__
                    print(
                        f"Something went wrong with {client.client_name}@{client.client_address[0]}:{client.client_address[1]}: {error_type}: {e}")
                    print(f"Closing connection with {client.client_name}")
                    client.client_socket.close()
                    if client.client_name in cur_clients:
                        del cur_clients[client.client_name]
                    self.game_board.players[client.client_name].health = 0
                    self.game_board.status = f"{client.client_name} disconnected"
                    with self.clients_lock:
                        if client.client_name in self.clients:
                            del self.clients[client.client_name]
                    continue
                # print(f"Received data from {client.client_name}: {data}")
                tid = tuple(data["tid"])
                if tid in self.transactions:
                    # print(f"Continuing transaction {tid}")
                    transaction = self.transactions[tid]
                    transaction.handle(data)
                else:
                    # print(f"New transaction {tid}")
                    try:
                        transaction = Transaction(self, tid[1], client.client_socket, date_type_handlers[data["type"]],
                                                  tid=tid[0])
                        self.transactions[tid] = transaction
                        transaction.handle(data)
                    except KeyError:
                        print(f"Unknown message type: {data['type']}")
                        response = {
                            "tid": data["tid"],
                            "type": "unknown_message"
                        }
                        client.client_socket.send_json(response)

            if current_time - last_update_time >= GAME_REFRESH_INTERVAL:
                self.game_board.update()
                game_state = self.game_board.get_game_state()
                for client_name, client in list(cur_clients.items()):
                    transaction = Transaction(self, "self", client.client_socket, send_game_state)
                    self.transactions[(transaction.transaction_id, "self")] = transaction
                    try:
                        transaction.handle(game_state)
                    except Exception as e:
                        print(f"Error sending game state to {client_name}: {e}")
                        print(f"Closing connection with {client_name}")
                        self.game_board.status = f"{client_name} disconnected"
                        client.client_socket.close()
                        if client_name in cur_clients:
                            del cur_clients[client_name]
                        self.game_board.players[client.client_name].health = 0
                        with self.clients_lock:
                            if client_name in self.clients:
                                del self.clients[client_name]
                last_update_time = current_time

                if END_GAME_ON_SINGLE_PLAYER and len(self.game_board.players) == 1:
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
                    handshake_res = client_handler.handshake()
                    if not handshake_res:
                        client_socket.close()
                        continue
                    self.clients[client_handler.client_name] = client_handler
                    self.game_board.add_player(client_handler.client_name, client_handler.client_character,
                                               random.randint(0, self.game_size[0] - 1),
                                               random.randint(0, self.game_size[1] - 1))
                print(f"Accepted connection from {client_address}")
            except TimeoutError:
                continue

            if len(self.clients) == self.max_players:
                self.game_started = True


def parse_args():
    parser = argparse.ArgumentParser(description="Run a game server")
    parser.add_argument("--ip", default="0.0.0.0", type=str, help="The IP address of the server")
    parser.add_argument("--port", default=12345, type=int, help="The port of the server")
    parser.add_argument("--max-players", default=10, type=int, help="The maximum number of players")
    parser.add_argument("--game-size", default=[30, 80], type=int, nargs=2,
                        help="The size of the game board, in format rows cols")

    return parser.parse_args()


def main():
    args = parse_args()

    server = GameServer(args.ip, args.port, args.max_players, args.game_size)

    server.run()


if __name__ == "__main__":
    main()
