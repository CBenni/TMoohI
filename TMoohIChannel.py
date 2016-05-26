from collections import OrderedDict
from TMoohIStatTrack import TMoohIStatTrack
from TMoohIMessageParser import getIRCv3Info
from TMoohIMessageParser import STATE_COMMAND, parseIRCMessage, STATE_V3
# represents a channel object. It is used to track the ROOMSTATE, USERSTATE etc, in order to properly welcome users.
# the parent is a TMoohIUser
class TMoohIChannel(TMoohIStatTrack):
	def __init__(self,parent,channelname):
		self.parent = parent
		self.manager = self.parent.parent
		# connection that has this channel joined. Is None if the channel isnt assigned to a connection yet/anymore.
		self.conn = None
		# 3 parents: user -> manager -> tmoohi
		self.name = channelname
		# maps a command type (ROOMSTATE, HOSTTARGET, USERSTATE, numeric) to a full message
		self.data = OrderedDict.fromkeys(["JOIN","353","366","USERSTATE","ROOMSTATE","HOSTTARGET"])
		
		self.stats = {
			"name": self.name,
			"data": self.dataDict,
			"connection": self.getConnId,
			"joined": self.getJoinStatus
		}
	
	def getConnId(self):
		if self.conn:
			return self.conn.connid
		else:
			return None
	
	def getJoinStatus(self):
		if self.conn:
			if self.data["JOIN"]:
				return True
			else:
				return False
		else:
			return False
	
	def setData(self,ex):
		if ex[STATE_COMMAND] == "ROOMSTATE":
			currentex = self.data["ROOMSTATE"]
			if currentex:
				currentex = parseIRCMessage(currentex)
				currentv3tags = getIRCv3Info(currentex)
				v3tags = getIRCv3Info(ex)
				currentv3tags.update(v3tags)
				newv3info = "@"+(";".join(["%s=%s"%(key,val) for key,val in currentv3tags.items()]))
				self.data["ROOMSTATE"] = newv3info + " " + self.data["ROOMSTATE"].split(" ",1)[1]
				return
		self.data[ex[STATE_COMMAND]] = ex[0]
		
	def dataDict(self):
		return dict(self.data)
		
	def welcome(self,client):
		for key,val in self.data.items():  # @UnusedVariable
			if val:
				client.request.sendall((val+"\r\n").encode("utf-8")) #.replace(self.channelname,self.channelname)
	
	def part(self):
		if self.conn:
			self.conn.part(self)
	
	def join(self):
		if self.conn:
			self.conn.join(self)
