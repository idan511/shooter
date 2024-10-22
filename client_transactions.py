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
    game.game_board.update_status(status)
    game.game_board.update_players_health(players_health)
    yield None

def endgame_handler(game, transaction_id, originator, peer, messages):
    winner = messages[-1]["winner"]
    game.game_board.main_board.clear()
    # add endgame message in middle of screen
    message = f"Game over! {winner} wins!"
    game.game_board.main_board.addstr(game.game_board.main_board.getmaxyx()[0] // 2,
                                      game.game_board.main_board.getmaxyx()[1] // 2 - len(message) // 2,
                                      message)
    game.game_board.main_board.refresh()
    game.game_board.status_bar.clear()
    game.game_board.debug_bar.clear()
    game.game_board.debug_bar.refresh()
    game.game_board.status_bar.refresh()
    game.is_game_over = True
    yield None

date_type_handlers = {
    "ping": pong_handler,
    "game_state": handle_game_state,
    "endgame": endgame_handler
}