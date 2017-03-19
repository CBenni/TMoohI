import time
import json
import random
import threading
from collections import deque
import urllib.request as urllib2

import MoohLog
import TMoohIUser
import TMoohIConnection
from MoohLog import eventmessage
from TMoohIErrors import RateLimitError, TooManyChannelsError, NotConnectedError
from TMoohIStatTrack import TMoohIStatTrack

# This is the main manager for anything TMI/twitch API related. It will also bootstrap all the connections that have to be created when the server boots.
# Its parent is the main TMoohI class.
class TMoohIManager(TMoohIStatTrack):
	def __init__(self,parent):
		self.quitting = False
		self.started = time.time()
		self.cachedJSONresponses = dict()
		self.users = {}
		self.parent = parent
		self.logger = parent.logger

		self.stats = { "users":self.users, "queue":self.getResendQueueLength, "since":time.time(), "build": self.parent.BuildInfo.__dict__ }

		# contains all the messages that couldnt be sent at the given point in time as a tuple (user,client,message)
		self.joinqueue = deque()

		self._createdconnections = []
		# times at which we created a connection or joined a channel
		self._conn_join_times = []
		self._connectionIDcounter = {}
		self._queuethread = threading.Thread(target=self.handleJoinQueue)
		self._queuethread.daemon = True
		self._queuethread.start()

		self._updatestatusthread = threading.Thread(target=self.updateStatus)
		self._updatestatusthread.daemon = True
		self._updatestatusthread.start()

	def quit(self):
		self.quitting = True
		for userkey,usr in self.users.items():
			usr.quit()



	def TMIConnectionFactory(self,user):
		now = time.time()
		self._conn_join_times = [i for i in self._conn_join_times if i>now-10]
		if len(self._conn_join_times)>40:
			raise RateLimitError('Creating connection for user ' + user.nick)
		else:
			self._conn_join_times.append(now)
			#create a connection
			try:
				self._connectionIDcounter[user.nick] += 1
			except Exception:
				self._connectionIDcounter[user.nick] = 1
			return TMoohIConnection.TMoohIConnection(user,"irc.chat.twitch.tv","%s/%d"%(user.nick,self._connectionIDcounter[user.nick]))

	def connect(self, client):
		for userkey,usr in self.users.items():
			if usr.nick == client.nick and usr.oauth == client.oauth:
				usr.welcome(client)
				return usr
		usr = TMoohIUser.TMoohIUser(self,client.nick,client.oauth)
		self.users[usr.key] = usr
		usr.welcome(client)
		return usr

	def disconnect(self, client):
		try:
			client.user.clients.remove(client)
		except Exception:
			self.logger.exception()

	def getJSON(self,url,cooldown=3600):
		try:
			if time.time() < self.cachedJSONresponses[url][0]+cooldown:
				self.logger.debug(eventmessage("manager","JSON response from cache: %s"%(url,)))
				return self.cachedJSONresponses[url][1]
		except KeyError:
			pass
		self.logger.debug(eventmessage("manager","Downloading JSON from %s"%(url,)))
		res = urllib2.urlopen(url)
		jsdata = res.read().decode("utf-8")
		data = json.loads(jsdata)
		self.cachedJSONresponses[url] = (time.time(), data)
		return data
	
	def join(self, user, channelinfo):
		# try joining this channel
		for conn in user.connections:
			try:
				if len(self._conn_join_times) < 45:
					conn.join(channelinfo)
					self._conn_join_times.append(time.time())
					self.logger.debug(eventmessage("manager","Channel %s joined on connection %s"%(channelinfo.name,conn.connid)))
					break
			except (TooManyChannelsError, NotConnectedError):
				pass
		else:
			self.logger.debug(eventmessage("manager","Channel %s could not be joined, enqueueing"%(channelinfo.name,)))
			self.joinqueue.append({"user":user,"channelinfo":channelinfo})
			

	def handleJoinQueue(self):
		while not self.quitting:
			try:
				# in each iteration, handle the joinQueue
				now = time.time()
				self._conn_join_times = [i for i in self._conn_join_times if i>now-10]
				# check all users on connection deficit
				try:
					for userkey,user in self.users.items():
						if self.quitting:
							return
						if len(self._conn_join_times) < 40:
							if user.getTotalChannels() >= 0.75 * user.getCapacity():
								self.logger.debug(eventmessage("manager","Requesting new connection for %s because of exceeded capacity"%(user.key,)))
								# request new connection
								user.connections.append(self.TMIConnectionFactory(user))
						# handle message queues
						user.handleMessageQueue()
				except RuntimeError:
					# Dict changed size during iteration. Nbd, well check again in .1 secs anyways.
					pass
				
				# check join queue
				iterator = 0
				while iterator < len(self.joinqueue):
					if self.quitting:
						return
					if len(self._conn_join_times) >= 45:
						break
					
					# dequeue a channel and try to join it
					channeljoininfo = self.joinqueue.pop()
					user = channeljoininfo["user"]
					channelinfo = channeljoininfo["channelinfo"]
					self.logger.debug(eventmessage("manager","Dequeing channel %s for %s from join queue"%(channelinfo.name,user.key)))
					# try joining this channel
					seed = random.randint(0,len(user.connections))
					for index in range(len(user.connections)):
						try:
							conn = user.connections[(index+seed)%len(user.connections)]
							conn.join(channelinfo)
							self._conn_join_times.append(time.time())
							self.logger.debug(eventmessage("manager","Channel %s joined on connection %s"%(channelinfo.name,conn.connid)))
							break
						except (TooManyChannelsError, NotConnectedError):
							pass
					else:
						# put it back into the deque
						self.joinqueue.append(channeljoininfo)
						iterator += 1
						self.logger.debug(eventmessage("manager","Channel %s could not be joined, requeueing"%(channelinfo.name,)))
				time.sleep(0.1)
			except Exception:
				self.logger.exception()

	def getResendQueueLength(self):
		return len(self.joinqueue)

	def getUptime(self):
		return time.time()-self.started

	def updateStatus(self):
		cnt = 0
		while not self.quitting:
			if cnt%10==0:
				try:
					serialized = self.serialize()
					self.parent.websocketserver.neweststatus = serialized
					self.logger.log(1,MoohLog.statusmessage(serialized))
				except Exception:
					self.logger.exception()
			cnt += 1
			time.sleep(1)
