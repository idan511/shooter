class Transaction:
    transaction_counter = 0
    def __init__(self, game_server, originator, peer_socket, handler, tid=None):
        print(f"Creating transaction {Transaction.transaction_counter} from {originator} to {peer_socket}")
        self.transaction_id = tid if tid else Transaction.transaction_counter
        Transaction.transaction_counter += 1
        self.originator = originator
        self.peer_socket = peer_socket
        self.transaction_live = True
        self.messages = []
        self.handler = handler(game_server, self.transaction_id, originator, peer_socket, self.messages)
        self.game_server = game_server

    def handle(self, data=None):
        self.messages.append(data)
        try:
            response = next(self.handler)
            if response is not None:
                response["tid"] = [self.transaction_id, self.originator]
                self.peer_socket.send_json(response)
            else:
                self.transaction_live = False
                self.game_server.transactions.pop((self.transaction_id, self.originator))
        except StopIteration:
            self.transaction_live = False
            self.game_server.transactions.pop((self.transaction_id, self.originator))

    def __hash__(self):
        return hash((self.transaction_id, self.originator))

    def __eq__(self, other):
        return self.transaction_id == other.transaction_id and self.originator == other.originator