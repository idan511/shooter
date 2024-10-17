def ping_handler(game_server, transaction_id, originator, peer, messages):
    ping = {
        "type": "ping"
    }
    yield ping
    response = messages[-1]
    if response["type"] == "pong":
        print(f"{originator} is alive")
    else:
        print(f"{originator} is dead")
        game_server.clients[originator].client_socket.close()
        del game_server.clients[originator]

def pong_handler(game_server, transaction_id, originator, peer, messages):
    pong = {
        "type": "pong"
    }
    yield pong

def keypress_handler(game, transaction_id, originator, peer, messages):
    keypress = messages[-1]
    print(f"Received keypress: {keypress}")
    game.game_board.player_action(originator, keypress['key'])
    yield {
        "type": "keypress_ack"
    }

def send_game_state(game, transaction_id, originator, peer, messages):
    cur_game_state, players_health, status = messages[-1]
    yield {
        "type": "game_state",
        "game_state": cur_game_state,
        "players_health": players_health,
        "status": status
    }

def endgame_handler(game, transaction_id, originator, peer, messages):
    yield {
        "type": "endgame",
        "winner": messages[-1]
    }

date_type_handlers = {
    "ping": pong_handler,
    "pong": ping_handler,
    "keypress": keypress_handler
}