# TMoohI

## About
TMoohI acts as a layer between your client applications and Twitch chat servers (Twitch Message Interface, "TMI").

It abstratcs the notion of the different chat clusters and manages all kinds of connections to all servers via a single client connection. Additionally, it handles rate limits, allowing bots to send an arbitrary amount of messages without being globally banned from twitch for 8 hours.

Additionally, it seeks to prevent excessive connection initiation (and therefore being kicked from twitchs servers) by keeping track of how many connections were created.

## Features
* Connect to twitch chat in an instant, without having to worry about connect/join rate limits
* Restart your client without needing to reconnect to twitch, all channels are available instantly
* Connect, send and receive messages from all chat clusters (normal chat, event chat, group chat) from a single connection, without any effort
* IRCv3.0
* realtime online statistics and debug output via WebSockets
* Connection crash/death/reconnect detection and handling
* IRC Client compatible

# How to use
Install python 3.4 (or compatible) with the required packages (list is coming soon™)

    python TMoohI.py

Connect the same way as you would for twitch

Join channels:
* JOIN #channel - automatically detect chat server
* JOIN #channel@normal - join on normal chat
* JOIN #channel@event - join on event chat
* JOIN #channel@group - join on group chat
