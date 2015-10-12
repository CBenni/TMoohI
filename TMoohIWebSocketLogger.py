import json
import asyncio
import threading

import MoohLog
from autobahn.asyncio.websocket import WebSocketServerProtocol, WebSocketServerFactory
from MoohLog import statusmessage

class TMoohIWebsocketServer:
    def __init__(self, parent, host, port):
        self.parent = parent
        self.logger = parent.logger
        self.host = host
        self.port = port
        
        self.server = None
        self.loop = None
        
        self.factory = WebSocketServerFactory()
        self.factory.protocol = MyServerProtocol
        self.factory.connections = []
        self.factory.parent = self.parent
        self.factory.server = self
        self.factory.logger = self.logger
        self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer loading up!"))
        
        self.serverthread = threading.Thread(target = self.runserver)
        self.serverthread.start()
    
    def quit(self):
        self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer shutting down!"))
        self.server.close()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop.stop()
    
    def broadcast(self,level,message):
        for conn in self.factory.connections:
            conn.postMessage(level,message)
    
    def runserver(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        coro = self.loop.create_server(self.factory, self.host, self.port)
        self.server = self.loop.run_until_complete(coro)

        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.logger.info(MoohLog.eventmessage("websocket","WebSocketServer shut down!"))
            self.server.close()
            self.loop.close()

class MyServerProtocol(WebSocketServerProtocol,MoohLog.logwriter):
    def onConnect(self, request):
        self.factory.logger.writers.append(self)
        self.level = 0
        self.filters = []
        print("Client connecting: {}".format(request.peer))

    def onOpen(self):
        print("WebSocket connection open.")
        # when opening a connection, send the current state
        self.inner_write(statusmessage(self.factory.parent.manager.serialize()))

    def onMessage(self, payload, isBinary):
        if isBinary:
            print("Binary message received: {} bytes".format(len(payload)))
        else:
            print("Text message received: {}".format(payload.decode('utf8')))
            try:
                jsondecoded = json.loads(payload.decode('utf8'))
                if type(jsondecoded) == list:
                    for x in jsondecoded:
                        if type(x) != dict:
                            return
                    self.filters = jsondecoded
                    print("Filter updated to %s"%(self.filters))
            except:
                pass

    def inner_write(self,message):
        print("sending message via websocket")
        self.sendMessage(json.dumps(message.serialize()).encode("utf-8"))

    def onClose(self, wasClean, code, reason):
        self.factory.logger.writers.remove(self)
        print("WebSocket connection closed: {}".format(reason))
