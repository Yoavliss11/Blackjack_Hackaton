# client.py
import socket
from protocol import *

SERVER_PAYLOAD_SIZE = 9  # 4 + 1 + 1 + 2 + 1

# -----------------------------
# Configuration
# -----------------------------
CLIENT_NAME = "BlackijeckyClient"

# -----------------------------
# Helpers
# -----------------------------
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
        int: The sum of the values of all cards in the hand,
        computed using card_value.
    """
    return sum(card_value(rank) for rank, _ in hand)


def rank_to_name(rank: int) -> str:
    """
    Converts a card rank to a human-readable name.

    Input:
        rank (int): The rank of the card (1–13).

    Output:
        str: The name of the rank.
            1 returns "Ace",
            11 returns "Jack",
            12 returns "Queen",
            13 returns "King",
            otherwise the numeric rank as a string.
    """
    if rank == 1:
        return "Ace"
    if rank == 11:
        return "Jack"
    if rank == 12:
        return "Queen"
    if rank == 13:
        return "King"
    return str(rank)


def suit_to_name(suit: int) -> str:
    """
    Converts a suit identifier to a human-readable suit name.

    Input:
        suit (int): The suit identifier.
            0 for Hearts,
            1 for Diamonds,
            2 for Clubs,
            3 for Spades.

    Output:
        str: The name of the suit in English,
        or "Unknown" if the identifier is invalid.
    """
    if suit == 0:
        return "Hearts"
    if suit == 1:
        return "Diamonds"
    if suit == 2:
        return "Clubs"
    if suit == 3:
        return "Spades"
    return "Unknown"


def format_card(card) -> str:
    """
    Formats a single card as a readable string.

    Input:
        card (tuple[int, int]): A card represented as (rank, suit).

    Output:
        str: A string describing the card in the format
        "<Rank Name> of <Suit Name>".
        Example: "King of Hearts".
    """
    rank, suit = card
    return f"{rank_to_name(rank)} of {suit_to_name(suit)}"


def format_hand(hand) -> str:
    """
    Formats an entire hand of cards as a readable string.

    Input:
        hand (list[tuple[int, int]]): A list of cards,
        where each card is represented as (rank, suit).

    Output:
        str: A comma-separated string describing all cards in the hand.
        Example: "Ace of Spades, 10 of Hearts".
    """
    return ", ".join(format_card(c) for c in hand)

# -----------------------------
# Main
# -----------------------------
def main():

    while True:
        user_input = input("Enter number of rounds to play (1-255): ").strip()

        if not user_input.isdigit():
            print("Please enter a valid number")
            continue

        rounds = int(user_input)

        if not (1 <= rounds <= 255):
            print("Number of rounds must be between 1 and 255")
            continue

        break

    # Create UDP socket to listen for broadcast offers from servers
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # Allow address/port reuse to avoid bind errors on restart
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except Exception:
        pass
    
    # Bind to the well-known UDP port to receive server offers
    udp_sock.bind(("", UDP_PORT))
    print("Client started, listening for offer requests...")

    while True:
        try:
            # Wait for a UDP offer packet from any server
            data, addr = udp_sock.recvfrom(1024)

            try:
                # Parse offer packet, ignore invalid or unrelated packets
                tcp_port, server_name = unpack_offer(data)
            except ValueError:
                continue

            server_ip = addr[0]
            print(f"Received offer from {server_ip} ({server_name})")

            # Connect to the server over TCP using the port from the offer
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_sock.connect((server_ip, tcp_port))

            # Send game request including number of rounds and client name
            tcp_sock.sendall(pack_request(rounds, CLIENT_NAME))
            print("Request sent to server")

            wins = 0
            losses = 0
            ties = 0

            for r in range(1, rounds + 1):
                print(f"\n--- Round {r}/{rounds} ---")

                player_hand = []
                dealer_hand = []

                # -------- Initial cards --------
                for _ in range(2):
                    _, rank, suit = unpack_server_payload(
                        recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                    )
                    player_hand.append((rank, suit))

                _, rank, suit = unpack_server_payload(
                    recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                )
                dealer_hand.append((rank, suit))

                print(f"Player cards: {format_hand(player_hand)}, total={hand_value(player_hand)}")
                print(f"Dealer shows: {format_card(dealer_hand[0])}")

                # -------- Player turn --------
                player_bust = False

                while True:
                    decision = input("Hit or Stand? ").strip().lower()
                    if decision not in ("hit", "stand"):
                        print("Invalid input")
                        continue
                    
                    # Send player's decision to the server
                    tcp_sock.sendall(pack_client_payload(decision))

                    if decision == "stand":
                        print("You chose to stand")
                        break

                    result, rank, suit = unpack_server_payload(
                        recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                    )

                    if result == RESULT_NOT_OVER:
                        player_hand.append((rank, suit))
                        total = hand_value(player_hand)
                        print(f"You drew {format_card((rank, suit))}, total={total}")

                        if total > 21:
                            print("Bust!")
                            player_bust = True
                            losses += 1
                            break

                # -------- Dealer stream--------
                if not player_bust:
                    print("Dealer turn:")

                while True:
                    result, rank, suit = unpack_server_payload(
                        recv_exact(tcp_sock, SERVER_PAYLOAD_SIZE)
                    )

                    if result in (RESULT_WIN, RESULT_LOSS, RESULT_TIE):
                        print(f"Dealer final hand: {format_hand(dealer_hand)}")

                        if result == RESULT_WIN:
                            print("You win!")
                            wins += 1
                        elif result == RESULT_LOSS:
                            if not player_bust:
                                losses += 1
                            print("You lose!")
                        else:
                            print("It's a tie!")
                            ties += 1
                        break

                    dealer_hand.append((rank, suit))
                    if not player_bust:
                        print(f"Dealer draws {format_card((rank, suit))}")

            win_rate = wins / rounds if rounds > 0 else 0.0
            print(
                f"\nFinished playing {rounds} rounds, "
                f"wins={wins}, losses={losses}, ties={ties}, "
                f"win rate={win_rate:.2f}"
            )

            tcp_sock.close()
            break

        except Exception as e:
            print(f"[Client] Error: {e}")

# -----------------------------
if __name__ == "__main__":
    main()
