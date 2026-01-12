# protocol.py
import struct
import socket

# -----------------------------
# Constants
# -----------------------------
MAGIC_COOKIE = 0xabcddcba

OFFER_TYPE   = 0x2
REQUEST_TYPE = 0x3
PAYLOAD_TYPE = 0x4

UDP_PORT = 13122
TEAM_NAME_LEN = 32

# Results
RESULT_NOT_OVER = 0x0
RESULT_TIE      = 0x1
RESULT_LOSS     = 0x2
RESULT_WIN      = 0x3

# Decisions
DECISION_HIT   = b"Hittt"
DECISION_STAND = b"Stand"

# -----------------------------
# Helpers
# -----------------------------
def encode_team_name(name: str) -> bytes:
    """
    Encodes a team or client name into a fixed-length byte sequence.

    The name is encoded using UTF-8, truncated if it exceeds the maximum
    allowed length, or padded with null bytes if it is shorter. This
    ensures a consistent field size in protocol packets.

    Input:
        name (str): The team or client name to encode.

    Output:
        bytes: A byte sequence of length TEAM_NAME_LEN representing
        the encoded name.
    """
    # Encode the name using UTF-8, ignoring invalid characters
    raw = name.encode("utf-8", errors="ignore")

    # Truncate the name if it exceeds the maximum allowed length
    if len(raw) > TEAM_NAME_LEN:
        return raw[:TEAM_NAME_LEN]

    # Pad the name with null bytes to reach the fixed length
    return raw.ljust(TEAM_NAME_LEN, b"\x00")


def decode_team_name(raw: bytes) -> str:
    """
    Decodes a fixed-length team or client name from a byte sequence.

    The function removes any trailing null-byte padding and decodes
    the remaining bytes using UTF-8.

    Input:
        raw (bytes): A fixed-length byte sequence containing an encoded
        team or client name.

    Output:
        str: The decoded team or client name as a string.
    """
    # Remove null-byte padding and decode the name
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """
    Receives exactly n bytes from a socket.

    This function repeatedly reads from the socket until the requested
    number of bytes has been received or the connection is closed. It is
    used to safely handle TCP streams, where a single recv call may return
    fewer bytes than requested.

    Input:
        sock (socket.socket): The socket from which to receive data.
        n (int): The exact number of bytes to receive.

    Output:
        bytes: A byte sequence of length n containing the received data.

    Raises:
        ConnectionError: If the socket is closed before all bytes are received.
    """
    # Accumulate received data until the required length is reached
    data = b""
    while len(data) < n:
        # Receive the remaining number of bytes
        chunk = sock.recv(n - len(data))

        # If recv returns no data, the connection has been closed
        if not chunk:
            raise ConnectionError("Socket closed while receiving data")

        # Append the newly received chunk
        data += chunk

    return data


# -----------------------------
# Offer (UDP)
# -----------------------------
# Format: cookie(4) | type(1) | tcp_port(2) | server_name(32)
_OFFER_FMT = "!I B H 32s"
_OFFER_SIZE = struct.calcsize(_OFFER_FMT)

def pack_offer(tcp_port: int, server_name: str) -> bytes:
    """
    Packs a server offer into a binary UDP packet for broadcast.

    The offer packet advertises the server's availability and provides
    clients with the TCP port and server name needed to establish a
    connection.

    Input:
        tcp_port (int): The TCP port on which the server is listening
        for incoming client connections.
        server_name (str): The server's name or team identifier.

    Output:
        bytes: A packed byte sequence representing the offer packet,
        formatted according to _OFFER_FMT and ready to be sent over UDP.
    """
    return struct.pack(
        _OFFER_FMT,
        MAGIC_COOKIE,
        OFFER_TYPE,
        tcp_port,
        encode_team_name(server_name)
    )


def unpack_offer(data: bytes):
    """
    Unpacks and validates a server offer packet received over UDP.

    This function parses a fixed-size offer packet, verifies protocol
    identifiers, and extracts the TCP port and server name advertised
    by the server.

    Input:
        data (bytes): Raw bytes received from a UDP socket that are
        expected to contain a complete offer packet.

    Output:
        tuple[int, str]: A tuple containing:
            - tcp_port (int): The TCP port on which the server accepts
              client connections.
            - server_name (str): The decoded server name.

    Raises:
        ValueError: If the offer packet is too short or does not match
        the expected protocol format.
    """
    # Ensure the received data contains a full offer packet
    if len(data) < _OFFER_SIZE:
        raise ValueError("Offer packet too short")

    # Unpack the offer packet according to the defined format
    cookie, msg_type, tcp_port, raw_name = struct.unpack(
        _OFFER_FMT, data[:_OFFER_SIZE]
    )

    # Validate protocol identifiers
    if cookie != MAGIC_COOKIE or msg_type != OFFER_TYPE:
        raise ValueError("Invalid offer packet")

    # Decode and return the advertised TCP port and server name
    return tcp_port, decode_team_name(raw_name)

# -----------------------------
# Request (TCP)
# -----------------------------
# Format: cookie(4) | type(1) | rounds(1) | client_name(32)
_REQUEST_FMT = "!I B B 32s"
_REQUEST_SIZE = struct.calcsize(_REQUEST_FMT)

def pack_request(rounds: int, client_name: str) -> bytes:
    """
    Packs a client game request into a binary request packet for
    transmission to the server over TCP.

    The request includes the number of rounds the client wishes to play
    and the client's team name, encoded according to the protocol
    specification.

    Input:
        rounds (int): The number of Blackjack rounds requested by the client.
        client_name (str): The client's team or player name.

    Output:
        bytes: A packed byte sequence representing the request packet,
        formatted according to _REQUEST_FMT and ready to be sent over a
        TCP socket.
    """
    return struct.pack(
        _REQUEST_FMT,
        MAGIC_COOKIE,
        REQUEST_TYPE,
        rounds,
        encode_team_name(client_name)
    )


def unpack_request(data: bytes):
    """
    Unpacks and validates a client game request received over TCP.

    This function parses a fixed-size request packet, verifies protocol
    identifiers, and extracts the requested number of rounds along with
    the client's team name.

    Input:
        data (bytes): Raw bytes received from the TCP socket that are
        expected to contain a complete request packet.

    Output:
        tuple[int, str]: A tuple containing:
            - rounds (int): The number of game rounds requested by the client.
            - client_name (str): The decoded client or team name.

    Raises:
        ValueError: If the request packet is too short or does not match
        the expected protocol format.
    """
    # Ensure the received data contains a full request packet
    if len(data) < _REQUEST_SIZE:
        raise ValueError("Request packet too short")

    # Unpack the request packet according to the defined format
    cookie, msg_type, rounds, raw_name = struct.unpack(
        _REQUEST_FMT, data[:_REQUEST_SIZE]
    )

    # Validate protocol identifiers
    if cookie != MAGIC_COOKIE or msg_type != REQUEST_TYPE:
        raise ValueError("Invalid request packet")

    # Decode and return the request parameters
    return rounds, decode_team_name(raw_name)


# -----------------------------
# Client Payload (TCP)
# -----------------------------
# Format: cookie(4) | type(1) | decision(5)
_CLIENT_PAYLOAD_FMT = "!I B 5s"
_CLIENT_PAYLOAD_SIZE = struct.calcsize(_CLIENT_PAYLOAD_FMT)

def pack_client_payload(decision: str) -> bytes:
    """
    Packs a player's decision into a client payload for transmission
    to the server over TCP.

    This function converts a human-readable decision string into the
    fixed-size binary format defined by the protocol.

    Input:
        decision (str): The player's decision.
            Accepted values are "hit" or "stand" (case-insensitive).

    Output:
        bytes: A packed byte sequence representing the client payload,
        formatted according to _CLIENT_PAYLOAD_FMT and ready to be sent
        over a TCP socket.

    Raises:
        ValueError: If the provided decision is not valid.
    """
    # Convert the decision string to the corresponding protocol constant
    if decision.lower() == "hit":
        d = DECISION_HIT
    elif decision.lower() == "stand":
        d = DECISION_STAND
    else:
        raise ValueError("Invalid decision")

    # Pack the payload according to the client payload format
    return struct.pack(
        _CLIENT_PAYLOAD_FMT,
        MAGIC_COOKIE,
        PAYLOAD_TYPE,
        d
    )


def unpack_client_payload(data: bytes) -> str:
    """
    Unpacks and validates a client decision payload received over TCP.

    This function parses a fixed-size client payload, verifies protocol
    identifiers, and extracts the player's decision for the current turn.

    Input:
        data (bytes): Raw bytes received from the TCP socket that are
        expected to contain a complete client payload.

    Output:
        str: The player's decision as a string.
            Returns "Hit" or "Stand".

    Raises:
        ValueError: If the payload is too short, does not match the
        expected protocol format, or contains an unknown decision.
    """
    # Ensure the received data contains a full client payload
    if len(data) < _CLIENT_PAYLOAD_SIZE:
        raise ValueError("Client payload too short")

    # Unpack the client payload according to the defined format
    cookie, msg_type, raw_decision = struct.unpack(
        _CLIENT_PAYLOAD_FMT, data[:_CLIENT_PAYLOAD_SIZE]
    )

    # Validate protocol identifiers
    if cookie != MAGIC_COOKIE or msg_type != PAYLOAD_TYPE:
        raise ValueError("Invalid client payload")

    # Remove padding null bytes from the decision field
    decision = raw_decision.rstrip(b"\x00")

    # Decode the decision into a human-readable command
    if decision == DECISION_HIT:
        return "Hit"
    if decision == DECISION_STAND:
        return "Stand"

    # Decision value is not recognized
    raise ValueError("Unknown decision")


# -----------------------------
# Server Payload (TCP)
# -----------------------------
# Format: cookie(4) | type(1) | result(1) | rank(2) | suit(1)
_SERVER_PAYLOAD_FMT = "!I B B H B"
_SERVER_PAYLOAD_SIZE = struct.calcsize(_SERVER_PAYLOAD_FMT)

def pack_server_payload(result: int, rank: int, suit: int) -> bytes:
    """
    Packs game state information into a server payload for transmission
    to the client over TCP.

    The payload is used both for streaming card information during a round
    and for sending the final result marker at the end of a round.

    Input:
        result (int): The game state or final result code.
            RESULT_NOT_OVER indicates a regular card payload.
            RESULT_WIN, RESULT_LOSS, or RESULT_TIE indicate the final result.
        rank (int): The rank of the card being sent.
            Set to 0 when sending the final result marker.
        suit (int): The suit of the card being sent.
            Set to 0 when sending the final result marker.

    Output:
        bytes: A packed byte sequence representing the server payload,
        formatted according to _SERVER_PAYLOAD_FMT and ready to be sent
        over a TCP socket.
    """
    return struct.pack(
        _SERVER_PAYLOAD_FMT,
        MAGIC_COOKIE,
        PAYLOAD_TYPE,
        result,
        rank,
        suit
    )


def unpack_server_payload(data: bytes):
    """
    Unpacks and validates a server payload received over TCP.

    This function parses a fixed-size server payload, verifies that it
    contains the correct magic cookie and message type, and extracts
    the game-related fields.

    Input:
        data (bytes): Raw bytes received from the TCP socket that are
        expected to contain a complete server payload.

    Output:
        tuple[int, int, int]: A tuple containing:
            - result (int): The game state or final result code
              (RESULT_NOT_OVER, RESULT_WIN, RESULT_LOSS, RESULT_TIE).
            - rank (int): The rank of the card (valid when result is
              RESULT_NOT_OVER).
            - suit (int): The suit of the card (valid when result is
              RESULT_NOT_OVER).

    Raises:
        ValueError: If the payload is too short or does not match the
        expected protocol format.
    """
    # Ensure the received data contains a full server payload
    if len(data) < _SERVER_PAYLOAD_SIZE:
        raise ValueError("Server payload too short")

    # Unpack the payload according to the server payload format
    cookie, msg_type, result, rank, suit = struct.unpack(
        _SERVER_PAYLOAD_FMT, data[:_SERVER_PAYLOAD_SIZE]
    )

    # Validate protocol identifiers
    if cookie != MAGIC_COOKIE or msg_type != PAYLOAD_TYPE:
        raise ValueError("Invalid server payload")

    # Return the parsed game result and card information
    return result, rank, suit

