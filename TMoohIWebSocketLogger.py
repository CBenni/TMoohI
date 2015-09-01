import json
import asyncio
import threading

import MoohLog
from autobahn.asyncio.websocket import WebSocketServerProtocol, WebSocketServerFactory

class TMoohIWebsocketServer:
    def __init__(self, logger, host, port):
        self.logger = logger
        self.host = host
        self.port = port
        
        self.factory = WebSocketServerFactory()
        self.factory.protocol = MyServerProtocol
        self.factory.connections = []
        self.factory.server = self
        self.factory.logger = self.logger
        self.logger.info(MoohLog.eventmessage("general","WebSocketServer loading up!"))
        
        self.serverthread = threading.Thread(self.runserver)
        self.serverthread.start()
    
    def broadcast(self,level,message):
        for conn in self.factory.connections:
            conn.postMessage(level,message)
    
    def runserver(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        coro = loop.create_server(self.factory, self.host, self.port)
        server = loop.run_until_complete(coro)

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()
            loop.close()

class MyServerProtocol(WebSocketServerProtocol,MoohLog.logwriter):
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
