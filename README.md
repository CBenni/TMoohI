# TMoohI

## About
TMoohI acts as a layer between your client applications and Twitch chat servers (Twitch Message Interface, "TMI").

It abstratcs the notion of the different chat clusters and manages all kinds of connections to all servers via a single client connection. Additionally, it handles rate limits, allowing bots to send an arbitrary amount of messages without being globally banned from twitch for 2 hours.

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
Install python 3.4 (or compatible) with the required packages:

```shell
pip install -r requirements.txt
```

Then run with:

```shell
python TMoohI.py
```

Connect the same way as you would for twitch. Ignore rate limits. Be happy.

# License
[![Creative Commons License](https://i.creativecommons.org/l/by-nc/4.0/88x31.png)](http://creativecommons.org/licenses/by-nc/4.0/)
<span xmlns:dct="http://purl.org/dc/terms/" property="dct:title">TMoohI</span> by <span xmlns:cc="http://creativecommons.org/ns#" property="cc:attributionName">CBenni</span> is licensed under a [Creative Commons Attribution-NonCommercial 4.0 International License](http://creativecommons.org/licenses/by-nc/4.0/).
Permissions beyond the scope of this license may be available at [business@cbenni.com](business@cbenni.com).
