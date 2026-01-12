# server.py
import socket
import threading
import time
import random
from protocol import *

# -----------------------------
# Fixed protocol sizes
# -----------------------------
REQUEST_SIZE = 38
CLIENT_PAYLOAD_SIZE = 10

# -----------------------------
# Card and Deck Logic
# -----------------------------
SUITS = [0, 1, 2, 3]
RANKS = list(range(1, 14))

class Deck:
    """
    Represents a standard shuffled deck of playing cards for Blackjack.

    The deck contains all combinations of ranks and suits and supports
    drawing cards one at a time.
    """
    def __init__(self):
        """
        Initializes a new shuffled deck.

        Input:
            None

        Output:
            None
        """
        self.cards = [(rank, suit) for suit in SUITS for rank in RANKS]
        random.shuffle(self.cards)

    def draw(self):
        """
        Draws and removes the top card from the deck.

        Input:
            None

        Output:
            tuple[int, int]: A card represented as (rank, suit).
        """
        return self.cards.pop()

def card_value(rank: int) -> int:
    """
    Calculates the Blackjack value of a card based on its rank.

    Input:
        rank (int): The rank of the card.
            1 represents Ace,
            11–13 represent Jack, Queen, King,
            2–10 represent numeric cards.

    Output:
        int: The Blackjack value of the card.
            Ace is counted as 11,
            face cards are counted as 10,
            numeric cards keep their numeric value.
    """
    if rank == 1:
        return 11
    if rank >= 11:
        return 10
    return rank

def hand_value(hand):
    """
    Calculates the total Blackjack value of a hand.

    Input:
        hand (list[tuple[int, int]]): A list of cards,
        where each card is represented as (rank, suit).

    Output:
        int: The sum of the Blackjack values of all cards in the hand.
    """
    return sum(card_value(rank) for rank, _ in hand)

# -----------------------------
# Configuration
# -----------------------------
SERVER_NAME = "BlackijeckyServer"
BROADCAST_IP = "<broadcast>"
TCP_BACKLOG = 20

# -----------------------------
# UDP Offer Broadcaster
# -----------------------------
def udp_broadcast_loop(tcp_port: int):
    """
    Periodically broadcasts UDP offer packets to announce the server's
    availability to potential clients.

    The function runs in an infinite loop and sends a broadcast message
    containing the TCP port and server name. Clients listening on the
    predefined UDP port can discover the server and initiate a TCP
    connection.

    Input:
        tcp_port (int): The TCP port on which the server is listening
        for incoming client connections.

    Output:
        None
    """

    # Create a UDP socket for broadcasting server offers
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Enable UDP broadcast on the socket
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # Prepare the offer packet once to avoid rebuilding it in every iteration
    offer_packet = pack_offer(tcp_port, SERVER_NAME)

    # Continuously broadcast the offer at a fixed interval
    while True:
        # Send the offer to the broadcast address and well-known UDP port
        udp_sock.sendto(offer_packet, (BROADCAST_IP, UDP_PORT))

        # Sleep to limit broadcast frequency and reduce network load
        time.sleep(1)


# -----------------------------
# One client session
# -----------------------------
def handle_client(client_sock: socket.socket, client_addr):
    """
    Handles a complete Blackjack session for a single connected client.

    This function runs on a dedicated thread per client. It receives the
    game request, manages multiple Blackjack rounds, streams all game
    events to the client according to the protocol, and determines the
    final outcome of each round.

    Input:
        client_sock (socket.socket): A connected TCP socket used for
        communication with the client.
        client_addr: The client's network address information
        (used for logging/debugging purposes).

    Output:
        None
    """
    try:
        # Set a timeout to prevent blocking indefinitely on a stalled client
        client_sock.settimeout(60)

        # Receive and unpack the initial game request from the client
        rounds, client_name = unpack_request(
            recv_exact(client_sock, REQUEST_SIZE)
        )
        print(f"[TCP] Request from '{client_name}', rounds={rounds}")

        # Iterate over the requested number of Blackjack rounds
        for r in range(1, rounds + 1):
            print(f"\n[ROUND {r}/{rounds}] Start")

            # Initialize a new shuffled deck and deal initial hands
            deck = Deck()
            player_hand = [deck.draw(), deck.draw()]
            dealer_hand = [deck.draw(), deck.draw()]

            # Log initial hands on the server side
            print(f"[ROUND {r}] Player initial hand: {player_hand} (total={hand_value(player_hand)})")
            print(f"[ROUND {r}] Dealer initial hand: {dealer_hand} (total={hand_value(dealer_hand)})")

            # Send initial cards to the client:
            # two cards for the player and one visible card for the dealer
            for rank, suit in player_hand:
                client_sock.sendall(pack_server_payload(RESULT_NOT_OVER, rank, suit))

            client_sock.sendall(
                pack_server_payload(RESULT_NOT_OVER, dealer_hand[0][0], dealer_hand[0][1])
            )

            # -------- Player turn --------
            # Track whether the player has busted
            player_bust = False

            while True:
                # Receive the player's decision (Hit or Stand)
                decision = unpack_client_payload(
                    recv_exact(client_sock, CLIENT_PAYLOAD_SIZE)
                )

                if decision == "Hit":
                    # Deal a card to the player
                    card = deck.draw()
                    player_hand.append(card)
                    total = hand_value(player_hand)

                    print(f"[ROUND {r}] Player hits and draws {card}, total={total}")

                    # Always send drawn cards with RESULT_NOT_OVER
                    client_sock.sendall(
                        pack_server_payload(RESULT_NOT_OVER, card[0], card[1])
                    )

                    # Check if the player busts
                    if total > 21:
                        print(f"[ROUND {r}] Player busts")
                        player_bust = True
                        break
                else:
                    # Player chooses to stand
                    print(f"[ROUND {r}] Player stands with total={hand_value(player_hand)}")
                    break

            # -------- Dealer full hand streaming (always) --------
            # Reveal the dealer's hidden card so the client can display the full hand
            hidden = dealer_hand[1]
            client_sock.sendall(pack_server_payload(RESULT_NOT_OVER, hidden[0], hidden[1]))
            print(f"[ROUND {r}] Dealer reveals hidden card {hidden}")

            # Draw additional dealer cards only if the player did not bust
            if not player_bust:
                while hand_value(dealer_hand) < 17:
                    card = deck.draw()
                    dealer_hand.append(card)
                    print(f"[ROUND {r}] Dealer draws {card}, total={hand_value(dealer_hand)}")
                    client_sock.sendall(pack_server_payload(RESULT_NOT_OVER, card[0], card[1]))

            # Compute final hand values
            dealer_total = hand_value(dealer_hand)
            player_total = hand_value(player_hand)

            # -------- Decide result --------
            # Determine the round outcome according to Blackjack rules
            if player_bust:
                result = RESULT_LOSS
            else:
                if dealer_total > 21:
                    result = RESULT_WIN
                elif dealer_total > player_total:
                    result = RESULT_LOSS
                elif dealer_total < player_total:
                    result = RESULT_WIN
                else:
                    result = RESULT_TIE

            # Send final result marker (no card data, only the result code)
            client_sock.sendall(pack_server_payload(result, 0, 0))

            # Log final state of the round
            print(f"[ROUND {r}] Final hands")
            print(f"[ROUND {r}] Player hand: {player_hand} (total={player_total})")
            print(f"[ROUND {r}] Dealer hand: {dealer_hand} (total={dealer_total})")
            print(f"[ROUND {r}] Result sent: {result}")

        # All rounds completed for this client
        print(f"\n[TCP] Finished session for '{client_name}'")

    finally:
        # Ensure the client socket is always closed
        client_sock.close()

# -----------------------------
# TCP Server
# -----------------------------
def start_tcp_server():
    """
    Starts the TCP server and listens for incoming client connections.

    This function creates a TCP socket, binds it to an available port,
    and begins listening for client connections. It also starts a
    background thread that periodically broadcasts UDP offer packets
    so that clients can discover the server.

    For each incoming TCP connection, a new thread is spawned to handle
    the client session independently.
    
    Input:
        None

    Output:
        None
    """

    # Create a TCP socket for client connections
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Allow address reuse to avoid bind errors when restarting the server
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind to an ephemeral port chosen by the operating system
    tcp_sock.bind(("", 0))

    # Start listening for incoming TCP connections
    tcp_sock.listen(TCP_BACKLOG)

    # Retrieve and display the assigned TCP port
    tcp_port = tcp_sock.getsockname()[1]
    print(f"Server started, TCP port {tcp_port}")

    # Start a background thread to broadcast UDP offers for server discovery
    threading.Thread(
        target=udp_broadcast_loop,
        args=(tcp_port,),
        daemon=True
    ).start()

    # Main accept loop: handle each client in a separate thread
    while True:
        # Accept a new client connection
        client_sock, client_addr = tcp_sock.accept()

        # Spawn a dedicated thread to handle the connected client
        threading.Thread(
            target=handle_client,
            args=(client_sock, client_addr),
            daemon=True
        ).start()


# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    start_tcp_server()

