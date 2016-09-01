import time

import TMoohIChannel
from MoohLog import eventmessage
from TMoohIStatTrack import TMoohIStatTrack
from TMoohIErrors import NotConnectedError, TooManyChannelsError, RateLimitError,\
	InvalidChannelError
from TMoohIMessageParser import parseIRCMessage, STATE_PREFIX, STATE_TRAILING, STATE_PARAM, STATE_COMMAND, STATE_V3
# This represents a username/oauth combo. It manages TMI connections, dispatches messages in both directions and manages channel joins/parts (the ratelimiter is global however)
# Its parent is the TMoohIManager.
class TMoohIUser(TMoohIStatTrack):
	def __init__(self,parent,nick,oauth):
		self.parent = parent
		self.tmoohi = parent.parent
		self.logger = parent.parent.logger
		self.nick = nick
		self.oauth = oauth
		self.key = "%s/%s"%(nick,id(self))
		self.clients = []

		# maps channelkeys (#channel) to a TMoohIChannel.
		self.channels = {}

		# list of TMoohIConnections. When a connection is created, it is added to this list. When a connection dies, it removes itself from this list
		self.connections = []

		# time when a connection was last requested
		self._lastNewConnectionRequest = 0

		self.globaluserstate = ""

		self.stats = {
			"nick": self.nick,
			"channels": self.channels,
			"clients":self.clients,
			"connections": self.connections,
			"TMIMessages": 0,
			"ClientMessages": 0,
		}

		self.messagequeue = []


	def handleMessageQueue(self):
		while self.messagequeue:
			# dequeue messages and handle them until we meet one that we cannot handle yet
			message = self.messagequeue.pop(0)
			user = message["user"]
			try:
				client = message["client"]
			except KeyError:
				client = None
			data = message["message"]
			self.logger.debug(eventmessage("user","Dequeing message %s for %s"%(data,user.key)))
			successfulsend = self.handleClientMessage(client,data, False)
			self.logger.debug(eventmessage("user","handleClientMessage returned with value %s"%(successfulsend,)))
			if successfulsend:
				self.logger.debug(eventmessage("user","handleClientMessage was successful! Queue length: %d"%(len(self.messagequeue),)))
			else:
				self.logger.debug(eventmessage("user","handleClientMessage added a new item to the queue. Queue length: %d"%(len(self.messagequeue),)))
				return False
			time.sleep(0.01)
		return True

	def quit(self):
		for connection in self.connections:
			connection.quit()

	def join(self, client, channelname, appendtoqueue):
		channelinfo = None
		if channelname[0] != "#":
			raise TypeError("PRIVMSG: Invalid channel %s."%(channelname,))
		self.logger.debug(eventmessage("user","Trying to join channel %s for client %s/%s"%(channelname, client.nick, client.oauth)))
		if channelname in self.channels:
			self.logger.debug(eventmessage("user","Channel %s already joined. Welcoming client %s/%s"%(channelname, client.nick, client.oauth)))
			channelinfo = self.channels[channelname]
			channelinfo.welcome(client)
		else:
			channelinfo = TMoohIChannel.TMoohIChannel(self,channelname)
			self.channels[channelname] = channelinfo
			# try to join the channel, if we are ratelimited, add to joinqueue
			self.parent.join(self, channelinfo)
		client.channels[channelname] = channelinfo

	def part(self, client, channelname):
		try:
			# remove from the channel
			del client.channels[channelname]
			client.request.sendall((":{nick}!{nick}@{nick}.tmi.twitch.tv PART {chan}\n".format(nick=self.nick,chan=channelname)).encode("utf-8"))
		except KeyError:
			self.logger.warning(eventmessage("user","Client %s/%s tried to leave channel %s, but it wasnt joined."%(client.nick, client.oauth, channelname)))
		# if there are no clients for this channel left, we leave the channel
		for otherclient in self.clients:
			if(channelname in otherclient.channels):
				return
		if channelname in self.channels:
			self.channels[channelname].part()
			# remove from channels
			del self.channels[channelname]
		else:
			self.logger.warning(eventmessage("user","Tried to leave channel %s, but it wasnt joined."%(channelname,)))

	def privmsg(self, message, appendtoqueue):
		if not message[STATE_TRAILING]:
			raise TypeError("PRIVMSG: Trailing data expected")

		channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
		allok = True
		for channel in channels:
			if channel[0] != "#":
				raise InvalidChannelError("PRIVMSG: Invalid channel %s."%(channel,))
			for conn in self.connections:
				try:
					conn.privmsg(channel,message[STATE_TRAILING])
					break
				except (RateLimitError, NotConnectedError):
					pass
			else:
				# If we reach this, all available connections (if any) were unable to send the message.
				# We create a new one (cooldown: 3 seconds) and send the message to the messagequeue.
				self.logger.debug(eventmessage("user","Requesting new connection because of %s"%(message[0],)))
				now = time.time()
				if now-self._lastNewConnectionRequest>3:
					self.connections.append(self.parent.TMIConnectionFactory(self))
					self._lastNewConnectionRequest = now
				# (re)add to messagequeue. message[0] is the original message
				if appendtoqueue:
					self.messagequeue.append({"user":self,"message":message[0]})
				else:
					self.messagequeue.insert(0,{"user":self,"message":message[0]})
				allok = False
		return allok

	def handle_client_privmsg(self,client,message, appendtoqueue):
		self.stats["ClientMessages"] += 1
		try:
			return self.privmsg(message, appendtoqueue)
		except InvalidChannelError:
			client.request.sendall((":tmi.twitch.tv 421 tmi.twitch.tv :Invalid PRIVMSG command. Use PRIVMSG #channel :message instead\r\n").encode("utf-8"))

	def handle_client_cap(self, client, message, appendtoqueue):
		client.request.sendall(b":tmi.twitch.tv 410 tmi.twitch.tv :Invalid CAP command. TMoohI always runs twitch.tv/commands and twitch.tv/tags\r\n")

	def handle_client_ping(self, client, message, appendtoqueue):
		if message[STATE_PARAM]:
			client.request.sendall((":tmi.twitch.tv PONG tmi.twitch.tv :%s\r\n"%(message[STATE_PARAM][0],)).encode("utf-8"))
		else:
			client.request.sendall((":tmi.twitch.tv PONG tmi.twitch.tv :%s\r\n"%(int(time.time()),)).encode("utf-8"))
		return True

	def handle_client_join(self, client, message, appendtoqueue):
		if message[STATE_PARAM]:
			allok = True
			try:
				channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
				for channel in channels:
					ok = self.join(client, channel, appendtoqueue)
					allok = ok and allok
			except TypeError:
				self.logger.exception()
				client.request.sendall((":tmi.twitch.tv 420 tmi.twitch.tv :Invalid JOIN command. Use JOIN #channel instead\r\n").encode("utf-8"))
			return allok
		else:
			client.request.sendall((":tmi.twitch.tv 420 tmi.twitch.tv :Invalid JOIN command. Use JOIN #channel instead\r\n").encode("utf-8"))
		return True

	def handle_client_part(self,client,message, appendtoqueue):
		ok = True
		if message[STATE_PARAM]:
			channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
			for channel in channels:
				if channel[0] == "#":
					self.part(client, channel)
				else:
					ok = False
		else:
			ok = False
		if not ok:
			client.request.sendall((":tmi.twitch.tv 421 tmi.twitch.tv :Invalid PART command. Use PART #channel instead\r\n").encode("utf-8"))
		return True


	def handle_client_mode(self,client,message, appendtoqueue):
		client.request.sendall((":tmi.twitch.tv 421 %s %s :Unknown command\r\n"%(self.nick,message[STATE_COMMAND])).encode("utf-8"))
		return True


	def handle_client_who(self,client,message, appendtoqueue):
		client.request.sendall((":tmi.twitch.tv 421 %s %s :Unknown command\r\n"%(self.nick,message[STATE_COMMAND])).encode("utf-8"))
		return True

	def handle_client_conndisc(self,client,message, appendtoqueue):
		for conn in self.connections:
			if conn.getConnected():
				conn.disc()
				break
		client.request.sendall((":tmi.twitch.tv 421 %s :Cutting a bot\r\n"%(self.nick,)).encode("utf-8"))
		return True

	def handle_client_connkill(self,client,message, appendtoqueue):
		for conn in self.connections:
			if conn.getConnected():
				conn.kill()
				break
		client.request.sendall((":tmi.twitch.tv 421 %s :Killing a bot\r\n"%(self.nick,)).encode("utf-8"))
		return True

	def handle_client_conndie(self,client,message, appendtoqueue):
		for conn in self.connections:
			if conn.getConnected():
				conn.die()
				break
		client.request.sendall((":tmi.twitch.tv 421 %s :A bot passed away...\r\n"%(self.nick,)).encode("utf-8"))
		return True


	#this takes a client message and handles it. It manages connection counts, channel limits, ratelimits. If it cant send a message at the current point in time,
	#because of ratelimits or the like, it pushes the message into the TMoohIManager's messagequeue/joinqueue
	# returns True if no message was added to the resentqueue, False if there was.
	def handleClientMessage(self, client, data, appendtoqueue):
		self.logger.debug(eventmessage("user","Handling message %s for %s"%(data,self.key)))
		# parse the message
		message = parseIRCMessage(data)
		cmd = message[STATE_COMMAND].lower()

		handler = None
		try:
			handler = getattr(self,"handle_client_%s"%(cmd,))
		except AttributeError:
			pass
		else:
			# they return True if the message could be handled.
			try:
				return handler(client, message, appendtoqueue)
			except Exception:
				self.logger.exception()

		return True

	# Swallows messages from the user himself and dispatches them
	def handleTMIMessage(self,connection,message):
		ownhostmask = ":{nick}!{nick}@{nick}.tmi.twitch.tv".format(nick=self.nick)
		if message[STATE_PREFIX] == ownhostmask and message[STATE_COMMAND] in ["PRIVMSG",]:
			# eat messages from "myself".
			return
		if message[STATE_COMMAND] in ["001","002","003","004","375","372","376","PONG","CAP","PART"]:
			# eat numeric "welcome" messages as well as pongs and caps, as well as parts.
			return
		if message[STATE_COMMAND] == "GLOBALUSERSTATE":
			self.globaluserstate = message[0]
		if message[STATE_COMMAND] == "WHISPER": 
			# eat all whispers except from the first connection
			if connection != self.connections[0]:
				return
		params = message[STATE_PARAM]
		if message[STATE_COMMAND] == "PRIVMSG":
			self.stats["TMIMessages"] += 1
		# check if the message is channelbound.
		channel = None
		for param in params:
			if param in self.channels:
				try:
					channel = self.channels[param]
				except KeyError:
					pass
				break
		if channel:
			if message[STATE_COMMAND] in channel.data:
				channel.setData(message)
		# broadcast message.
		self.broadcast(channel, message[0])

	# Sends the message to all connected clients of this user
	def broadcast(self, channel, message):
		try:
			for client in self.clients:
				if channel == None or channel.name in client.channels:
					try:
						client.request.sendall((message+"\r\n").encode("utf-8"))
					except BrokenPipeError:
						self.logger.error(eventmessage("user","Client %s/%s disconnected during broadcast"%(client.nick, client.oauth)))
		except Exception:
			self.logger.exception()

	# Welcomes a client after it connects.
	def welcome(self,client):
		client.request.sendall(":tmi.twitch.tv 001 {username} :Welcome, GLHF!\r\n:tmi.twitch.tv 002 {username} :Your host is tmi.twitch.tv\r\n:tmi.twitch.tv 003 {username} :This server is pretty old\r\n:tmi.twitch.tv 004 {username} :{buildinfo} loaded and running smoothly.\r\n:tmi.twitch.tv 375 {username} :-\r\n:tmi.twitch.tv 372 {username} :You are in a maze of dank memes, all alike.\r\n:tmi.twitch.tv 376 {username} :>\r\n".format(username=client.nick,buildinfo=self.parent.parent.BuildInfo).encode("utf-8"))
		client.request.sendall(":tmi.twitch.tv CAP * ACK :twitch.tv/tags\r\n:tmi.twitch.tv CAP * ACK :twitch.tv/commands\r\n".encode("utf-8"))
		if self.globaluserstate:
			client.request.sendall((self.globaluserstate+"\r\n").encode("utf-8"))
		self.clients.append(client)
	
	# Returns channelsperconnection * no. of connections
	def getCapacity(self):
		return len(self.connections) * self.tmoohi.config["channels-per-connection"]
	
	# Returns total no. of channels
	def getTotalChannels(self):
		return len(self.channels)