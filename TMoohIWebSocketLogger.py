import json
import copy
import asyncio
import threading

import MoohLog
from MoohLog import statusmessage, eventmessage, MoohLogger
from autobahn.asyncio.websocket import WebSocketServerProtocol, WebSocketServerFactory

class TMoohIWebsocketServer:
    def __init__(self, logger, host, port, defaultfilter = []):
        self.logger = logger
        self.host = host
        self.port = port
        
        
        self.server = None
        self.loop = None
        
        self.factory = WebSocketServerFactory()
        self.factory.protocol = websocketlogger
        self.factory.connections = []
        self.factory.server = self
        self.factory.logger = self.logger
        self.factory.defaultfilter = defaultfilter
        self.factory.neweststatus = None
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

class websocketlogger(WebSocketServerProtocol,MoohLog.logwriter):
    def onConnect(self, request):
        self.factory.logger.writers.append(self)
        self.level = 0
        self.filters = copy.deepcopy(self.factory.defaultfilter)
        self.factory.logger.debug(eventmessage("websocket","Websocket connecting: {}".format(request.peer)))

    def onOpen(self):
        self.factory.logger.debug(eventmessage("websocket","WebSocket connection open."))
        # when opening a connection, send the current state
        self.inner_write(statusmessage(self.factory.neweststatus))

    def onMessage(self, payload, isBinary):
        if isBinary:
            self.factory.logger.debug(eventmessage("websocket","Binary websocket message received: {} bytes".format(len(payload))))
        else:
            self.factory.logger.debug(eventmessage("websocket","Websocket text message received: {}".format(payload.decode('utf8'))))
            try:
                res = payload.decode('utf8').split(" ",1)
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
                self.factory.logger.exception()

    def inner_write(self,message):
        self.sendMessage(json.dumps(message.serialize()).encode("utf-8"))

    def onClose(self, wasClean, code, reason):
        try:
            self.factory.logger.writers.remove(self)
        except ValueError:
            pass
        if wasClean:
            self.factory.logger.debug(eventmessage("websocket","WebSocket connection closed: {}".format(reason)))
        else:
            self.factory.logger.debug(eventmessage("websocket","WebSocket connection closed unexpectedly: {}".format(reason)))
