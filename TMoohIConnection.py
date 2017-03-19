import re
import time
import socket
import threading
from TMoohIStatTrack import TMoohIStatTrack
from MoohLog import eventmessage
from TMoohIMessageParser import parseIRCMessage, STATE_COMMAND, STATE_PARAM
from TMoohIErrors import NotConnectedError, RateLimitError, TooManyChannelsError

#This class represents an actual connection to TMI servers. It is owned by a TMoohIUser
class TMoohIConnection(TMoohIStatTrack):
	def __init__(self,parent,server,connid):
		self.connected = False
		self.killing = False
		self.dead = False
		self.ignoring = False
		self.isshutdown = False
		self.connid = connid
		
		self.lastmessage = time.time()
		
		self.parent = parent
		self.manager = parent.parent
		self.logger = self.manager.parent.logger
		self.logger.info(eventmessage("connection","Connection ID %s created!"%(self.connid,)))
		
		# list of TMoohIChannels that are supposed to be joined by this connection.
		self.channels = []
		
		
		srvinfo = re.split("[^\d\w\.]",server)
		self.port = 6667
		self.server = server
		self.ip = self.server
		if len(srvinfo) == 2:
			self.port = int(srvinfo[1])
			self.ip = srvinfo[0]
		
		self.stats = {
			"server": "%s:%s"%(self.ip, self.port),
			"id": self.connid,
			"connected": self.getConnected,
			"channels": self.getChannels
		}
		
		# internals:
		self._socket = None
		self._recvthread = None
		self._recvthreadid = 0
		self._sentmessages = []
		self._messagebuffer = ""
		self._authed = False
		# we automatically connect to said server.
		self.connect()
	
	def quit(self):
		self.kill()
	
	def getConnected(self):
		return self.connected
	
	def getChannels(self):
		return [c.name for c in self.channels]
	
	def connect(self):
		self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self._socket.connect((self.ip, self.port))
		self._recvthread = threading.Thread(target=self.listen)
		self._recvthread.start()
		self.logger.info(eventmessage("connection","Connecting to %s/%s for %s"%(self.ip, self.port, self.connid)))
		self.sendraw("CAP REQ :twitch.tv/tags\r\nCAP REQ :twitch.tv/commands")
		if self.parent.oauth:
			self.sendraw("PASS %s"%(self.parent.oauth,))
		self.sendraw("USER %s %s %s :%s"%(self.parent.nick,self.parent.nick,self.parent.nick,self.parent.nick,))
		self.sendraw("NICK %s"%(self.parent.nick,))
	
	def listen(self):
		try:
			while True:
				buf = self._socket.recv(2048).decode("utf-8")
				if not buf:
					break
				if self.killing:
					break
				if self.dead:
					break
				if self.ignoring:
					continue
				self.lastmessage = time.time()
				self._messagebuffer += buf
				s = self._messagebuffer.split("\r\n")
				self._messagebuffer = s[-1]
				for line in s[:-1]:
					self.logger.debug(eventmessage("connection","Got raw TMI message in connection %s: %s"%(self.connid,line)))
					try:
						ex = parseIRCMessage(line)
					except Exception:
						self.logger.exception()
					if(ex[STATE_COMMAND]=="PING"):
						self.sendraw("PONG")
					elif ex[STATE_COMMAND]=="376":
						self.connected = True
						self.logger.info(eventmessage("connection","Connection ID %s connected!"%(self.connid,)))
					elif ex[STATE_COMMAND]=="JOIN":
						try:
							self.parent.handleTMIMessage(self, ex)
							self.logger.info(eventmessage("connection","Joined channel "+ex[STATE_PARAM][0]))
						except Exception:
							self.logger.exception()
					elif ex[STATE_COMMAND]=="PART":
						try:
							self.parent.handleTMIMessage(self, ex)
							self.logger.info(eventmessage("connection","Left channel "+ex[STATE_PARAM][0]))
						except Exception:
							self.logger.exception()
					else:
						self.parent.handleTMIMessage(self, ex)
		except ConnectionAbortedError:
			pass
		except Exception:
			self.logger.exception()
		self.shutdown()
		
	
	def shutdown(self):
		if self.isshutdown:
			self.logger.warning(eventmessage("connection","Tried to shutdown a non-connected socket."))
		else:
			self.isshutdown = True
			self.connected = False
			try:
				self.parent.connections.remove(self)
			except KeyError:
				# we have already warned about this.
				pass
			if self.killing:
				self.logger.info(eventmessage("connection","Connection ID %s killed!"%(self.connid,)))
			else:
				self.logger.error(eventmessage("connection","Connection ID %s disconnected!"%(self.connid,)))
				# when the connection dies, rejoin the channels on different (or new) connections
				for channel in self.channels:
					self.logger.warning(eventmessage("connection","Readding channel %s to the joinqueue!"%(channel.name,)))
					channel.conn = None
					self.manager.joinqueue.append({"user":self.parent,"channelinfo":channel})
				self.channels = []
			try:
				self._socket.shutdown(socket.SHUT_RDWR)
				self._socket.close()
			except OSError:
				# this will usually be thrown if the process is murdered or something, aka the connection was already cut, no need to shut down in that case.
				pass
	
	def sendraw(self,x):
		self.logger.debug(eventmessage("connection","Sending a RAW TMI message on bot %s: %s"%(self.connid,x)))
		self._socket.send((x+"\r\n").encode("utf-8"))
	
	def privmsg(self,channelname,message):
		if not self.connected:
			raise NotConnectedError()
		if self.manager.parent.config["ratelimit-commands"] == False and message[0] == "/" or message[0] == ".":
			self.sendraw("PRIVMSG %s %s"%(channelname,message))
			return
		now = time.time()
		self._sentmessages = [i for i in self._sentmessages if i>now-30]
		if len(self._sentmessages)>self.manager.parent.config["messages-per-30"]:
			raise RateLimitError('Sending "PRIVMSG %s :%s" on connection ID %s'%(channelname,message,self.connid))
		else:
			self.sendraw("PRIVMSG %s %s"%(channelname,message))
			self._sentmessages.append(now)
	
	# joins the channel if it isnt joined yet, else just adds it to the list
	def join(self,channelinfo):
		if not self.connected:
			raise NotConnectedError()
		if channelinfo.name in self.channels:
			# already joined. Do nothing
			pass
		else:
			if len(self.channels)>=self.manager.parent.config["channels-per-connection"]:
				raise TooManyChannelsError(len(self.channels))
			else:
				self.sendraw("JOIN %s"%(channelinfo.name,))
				self.channels.append(channelinfo)
				channelinfo.conn = self
	
	# actually parts the channelname
	def part(self,channelinfo):
		if not self.connected:
			raise NotConnectedError()
		if channelinfo not in self.channels:
			raise KeyError()
		self.sendraw("PART %s"%(channelinfo.name,))
		self.channels.remove(channelinfo)
	
	
	def _update(self):
		now = time.time()
		dt = now-self.lastmessage
		if dt > 30:
			self.logger.error(eventmessage("connection","Bot %s got silently disconnected. Enabling dead mode."%(self.connid,)))
			self.connected = False
			self.dead = True
			self.shutdown()
		elif dt > 10:
			if dt > 20:
				self.logger.warning(eventmessage("connection","Bot %s has not received messages in %d seconds. Pinging TMI server."%(self.connid,int(dt))))
			else:
				self.logger.debug(eventmessage("connection","Bot %s has not received messages in %d seconds. Pinging TMI server."%(self.connid,int(dt))))
			self.sendraw("PING")
				
	
	def kill(self):
		"""
		Simulates the socket getting killed
		"""
		self.logger.info(eventmessage("connection","Killing bot %s"%(self.connid,)))
		self.killing = True
		self.connected = False
		self._socket.close()
	
	def disc(self):
		"""
		Simulates the connection being closed
		"""
		self.logger.info(eventmessage("connection","Disconnecting bot %s"%(self.connid,)))
		self.sendraw("PRIVMSG #jtv :/DISCONNECT")
	
	def die(self):
		"""
		Simulates the server silently disconnecting us
		"""
		self.logger.info(eventmessage("connection","Dieing bot %s"%(self.connid,)))
		self.ignoring = True
			
