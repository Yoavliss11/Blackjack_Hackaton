# Blackjack Client-Server Application
Intro to Networks 2025 Hackathon

## Overview
This project implements a simplified Blackjack game as a client-server application,
developed as part of the Intro to Networks 2025 Hackathon assignment.

The system is fully network-based:
- The server acts as the dealer and hosts the game logic.
- The client discovers servers using UDP broadcast, connects via TCP,
  and allows the user to play multiple Blackjack rounds.

## Architecture
1. The server broadcasts UDP offer messages periodically.
2. Clients listen on a fixed UDP port for offers.
3. The client connects to the server via TCP.
4. The server runs the requested number of Blackjack rounds.
5. Results and statistics are sent back to the client.
6. The client prints the summary and may start a new session.

## Network Protocol
### UDP Offer Message
- Magic cookie: 0xabcddcba
- Message type: 0x2
- Server TCP port
- Server name (32 bytes)

### TCP Communication
After discovering a server, the client connects via TCP and sends
the number of requested rounds as a newline-terminated message.

## Game Rules
- Standard 52-card deck.
- Face cards are worth 10.
- Aces are worth 11 and may be reduced to 1 to avoid bust.
- Dealer hits until total is at least 17, including soft 17.
- No betting or splitting.

## Error Handling
- UDP timeouts are handled gracefully.
- Invalid or corrupted packets are ignored.
- Client and server handle timeouts and disconnections safely.
- One failing client does not affect others.

## How to Run

The server and the client must be run in two separate terminal windows. 
There can be more than one player but each player play in a seperate terminal

### Server
```bash
python server.py # Terminal 1
```
### Client
```bash
python client.py # Terminal 2
```


