import json
import copy
import asyncio
import threading

import MoohLog
from MoohLog import statusmessage, eventmessage, MoohLogger
from SimpleWebSocketServer import SimpleWebSocketServer, WebSocket
TEXT = 0x01
from TMoohIErrors import AlreadyDefinedError
websocketServer = None
class TMoohIWebsocketServer:
	def __init__(self, logger, host, port, defaultfilter = []):
		global websocketServer
		if websocketServer != None:
			raise AlreadyDefinedError("Websocket server already created.")
		websocketServer = self
		
		self.logger = logger
		self.host = host
		self.port = port
		self.defaultfilter = defaultfilter
		self.killing = False
		
		self.clients = []
		
		
		self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer loading up on %s:%s!"%(self.host, self.port)))
		self.server = SimpleWebSocketServer(self.host, self.port, websocketlogger)
		
		self.serverthread = threading.Thread(target = self.runserver)
		self.serverthread.start()
		self.neweststatus = {}
	
	def quit(self):
		self.killing = True
		self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer shutting down!"))
		self.server.close()
	
	def runserver(self):
		while not self.killing:
			try:
				self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer starting!"))
				self.server.serveforever()
			except (KeyboardInterrupt):
				self.killing = True
			except OSError:
				if not self.killing: # swallow errors when closing
					self.logger.exception() 
			except Exception:
				self.logger.exception()
			finally:
				self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer shut down!"))
				try:
					self.server.close()
				except OSError:
					pass # swallow "An operation was attempted on something that is not a socket" errors

class websocketlogger(WebSocket, MoohLog.logwriter):
	#def __init__(self, svr, sock, adr):
	#	super().__init__(svr, sock, adr)
	#	websocketServer.logger.debug(eventmessage("websocket","Websocket connecting: {}".format(adr)))
	#	self.filters = copy.deepcopy(websocketServer.defaultfilter)
		
	def handleConnected(self):
		self.filters = copy.deepcopy(websocketServer.defaultfilter)
		websocketServer.clients.append(self)
		websocketServer.logger.writers.append(self)
		websocketServer.logger.debug(eventmessage("websocket","Websocket connected: {}".format(self.address[0])))
		# when opening a connection, send the current state
		self.inner_write(statusmessage(websocketServer.neweststatus,"status"))
	
	def handleMessage(self):
		if self.opcode != TEXT:
			websocketServer.logger.debug(eventmessage("websocket","Websocket message received: {} bytes".format(len(self.data))))
		else:
			websocketServer.logger.debug(eventmessage("websocket","Websocket text message received: {}".format(self.data)))
			try:
				res = self.data.split(" ",1)
				command = res[0]
				data = ""
				if len(res) == 2:
					data = res[1]
					jsondecoded = json.loads(data)
				if command == "SETFILTER":
					if data:
						ok = True
						if type(jsondecoded) == list:
							for x in jsondecoded:
								if type(x) != dict:
									ok = False
							if ok:
								self.filters = jsondecoded
								
								response = eventmessage("websocket","Filter updated to %s"%(self.filters,))
								response.level = MoohLogger.DEBUG
								self.inner_write(response)
						else:
							ok = False
						if not ok:
							response = eventmessage("websocket","Could not process filter %s"%(data,))
							response.level = MoohLogger.ERROR
							self.inner_write(response)
					else:
						response = eventmessage("websocket","Could not process empty filter")
						response.level = MoohLogger.ERROR
						self.inner_write(response)
				else:
					response = eventmessage("websocket","Unknown command %s"%(command,))
					response.level = MoohLogger.ERROR
					self.inner_write(response)
			except Exception:
				websocketServer.logger.exception()

	def inner_write(self,message):
		try:
			self.sendMessage(json.dumps(message.serialize()))#.encode("utf-8")
		except Exception:
			pass

	def handleClose(self):
		try:
			websocketServer.logger.writers.remove(self)
			websocketServer.clients.remove(self)
		except ValueError:
			pass
		websocketServer.logger.debug(eventmessage("websocket","WebSocket connection closed"))
		#else:
		#	websocketServer.logger.debug(eventmessage("websocket","WebSocket connection closed unexpectedly: {}".format(reason)))
