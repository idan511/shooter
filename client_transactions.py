def pong_handler(game, transaction_id, originator, peer, messages):
    game.game_board.status_bar.clear()
    game.game_board.status_bar.addstr(0, 0, f"Ping!")
    game.game_board.status_bar.refresh()
    response = {
        "type": "pong"
    }
    yield response

def keypress_handler(game, transaction_id, originator, peer, messages):
    keypress = messages[-1]
    response = {
        "type": "keypress",
        "key": keypress
    }
    yield response

def handle_game_state(game, transaction_id, originator, peer, messages):
    game_state = messages[-1]["game_state"]
    status = messages[-1]["status"]
    players_health = messages[-1]["players_health"]
    game.game_board.update_game_state(game_state)
    game.game_board.status_bar.clear()
    game.game_board.status_bar.addstr(0, 0, status)
    game.game_board.status_bar.refresh()
    game.game_board.health_bar.clear()
    game.game_board.health_bar.addstr(0, 0, f"Players: {len(players_health)}, Your health: {max(players_health.get(game.player_name, 0), 0)}")
    game.game_board.health_bar.refresh()
    yield None

date_type_handlers = {
    "ping": pong_handler,
    "game_state": handle_game_state
}