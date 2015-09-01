import codecs
import datetime
import re
import sys
import traceback

class MoohLogger(object):
	DEBUG = 0
	INFO = 10
	WARNING = 20
	ERROR = 30
	EXCEPTION = 40
	FATAL = 50
	LEVELS = { 0:"DEBUG", 10:"INFO", 20:"WARNING", 30:"ERROR", 40:"EXCEPTION", 50:"FATAL" }
	def __init__(self):
		self.writers = []
	def log(self,level,data):
		data.level = level
		for writer in self.writers:
			writer.write(data)
	def debug(self,x):
		self.log(MoohLogger.DEBUG,x)
	def info(self,x):
		self.log(MoohLogger.INFO,x)
	def warning(self,x):
		self.log(MoohLogger.WARNING,x)
	def error(self,x):
		self.log(MoohLogger.ERROR,x)
	def fatal(self,x):
		self.log(MoohLogger.FATAL,x)
	def exception(self):
		exc_type, exc_value, exc_traceback = sys.exc_info()
		self.error(eventmessage("exception","".join(traceback.format_exception(exc_type, exc_value,exc_traceback))))
		
class logwriter(object):
	def __init__(self):
		self.filters = []
	def write(self,message):
		if message.meets_filter(self.filters):
			self.inner_write(message)
	def inner_write(self,message):
		raise NotImplementedError
		
		
class filewriter(logwriter):
	def __init__(self,fileformat):
		super(filewriter,self).__init__()
		self.fileformat = fileformat
	def inner_write(self,message):
		try:
			with codecs.open(datetime.datetime.now().strftime(self.fileformat), "a", "utf-8") as myfile:
				myfile.write(str(message)+"\r\n")
		except:
			pass
class consolewriter(logwriter):
	def __init__(self):
		super(consolewriter,self).__init__()
	def inner_write(self,message):
		try:
			print(str(message))
		except:
			pass

class logmessage(object):
	def __init__(self,data,level=0):
		self.data = data
		self.level = level
		self.format = "%s"
		self.type = "generic"
	
	def meets_filter(self,filters):
		for disjunction in filters:
			fits = True
			for constraint,value in disjunction.items():
				f = constraint.lower()
				inv = f.startswith("!")
				if inv:
					f=f[1:]
				print("checking filter %s with value %s on data %s/level %s/type %s"%(f,value,self.data,self.level,self.type))
				
				# by XORing (!=) with the inversion value, we can invert the result
				if f=="level":
					fits &= (self.level>=int(value)) ^ inv
				elif f=="type":
					fits &= (self.type==value) ^ inv
				elif f in self.data:
					# check if regex or not (regex starts+ends with /)
					m = re.match("/([^/])/(i?)",value)
					if m:
						# check the regex in m.group(1)
						fits &= bool( re.search( m.group(1), self.data[f], re.IGNORECASE if m.group(2) else 0 ) ) ^ inv
					else:
						fits &= (self.data[f] == value) ^ inv
				if not fits:
					break
			if fits:
				return True
		return False
	def __str__(self):
		levelname = ""
		maxl = -10
		for l,n in MoohLogger.LEVELS.items():
			if l<=self.level:
				if l>maxl:
					levelname = "[%s] "%(n,)
					maxl = l
		return levelname+(self.format%self.data)

class chatmessage(logmessage):
	def __init__(self,server,ip,channel,id,nick,message):
		super(chatmessage,self).__init__({ "server":server, "ip":ip, "channel":channel,"id":id,"nick":nick,"message":message })
		self.type = "chat"
		self.format = "[%(server)s (%(ip)s)] #%(channel)s(%(id)s) <%(nick)s> %(message)s"
		
def reploauth(m):
	return "oauth:(%d)"%(len(m.group(1)),)
class eventmessage(logmessage):
	def __init__(self,event,message):
		message = re.sub("oauth:([a-z0-9]+)",reploauth,message)
		super(eventmessage,self).__init__({ "event":event, "message":message })
		self.type = "event"
		self.format = "[%(event)s] %(message)s"


class statsmessage(logmessage):
	def __init__(self,event,message):
		message = re.sub("oauth:([a-z0-9]+)",reploauth,message)
		super(eventmessage,self).__init__({ "event":event, "message":message })
		self.type = "stats"
		self.format = "[%(event)s] %(message)s"
