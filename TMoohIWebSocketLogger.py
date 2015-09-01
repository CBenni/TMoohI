from MoohLog import *
import sys
import pdb
import time
import json
import asyncio
import threading
import MoohLog
from autobahn.asyncio.websocket import WebSocketServerProtocol, WebSocketServerFactory

class TMoohIWebsocketServer:
	def __init__(self, logger, host, port):
		self.server = websockets.serve(self.handler, host, port)
		self.logger = logger
		
		self.serverthread = threading.Thread(runserver)
		self.serverthread.start()
	
	def runserver(self):
		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)
		
		self.factory = WebSocketServerFactory()
		self.factory.protocol = MyServerProtocol
		self.factory.connections = []
		self.factory.server = self
		self.factory.logger = self.logger
		self.logger.info(eventmessage("general","WebSocketServer loading up!"))
		
		coro = loop.create_server(self.factory, '127.0.0.1', 8765)
		server = loop.run_until_complete(coro)

		try:
			loop.run_forever()
		except KeyboardInterrupt:
			pass
		finally:
			server.close()
			loop.close()

class MyServerProtocol(WebSocketServerProtocol,logwriter):
	def onConnect(self, request):
		self.factory.logger.writers.append(self)
		self.level = 0
		self.filter = [{"type":"stats"}]
		print("Client connecting: {}".format(request.peer))

	def onOpen(self):
		print("WebSocket connection open.")

	def onMessage(self, payload, isBinary):
		if isBinary:
			print("Binary message received: {} bytes".format(len(payload)))
		else:
			print("Text message received: {}".format(payload.decode('utf8')))
			try:
				self.filter = json.loads(payload.decode('utf8'))
			except:
				pass

	def inner_write(self,message):
		self.sendMessage(message.encode("utf-8"))

	def onClose(self, wasClean, code, reason):
		self.factory.logger.writers.remove(self)
		print("WebSocket connection closed: {}".format(reason))
