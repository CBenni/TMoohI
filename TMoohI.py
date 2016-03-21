#!/usr/bin/env python
#TMoohI
# (c) CBenni 2015
import re
import sys
import time
import json
import yaml
import argparse
import threading
import socketserver

import TMoohIWebSocketLogger
import BuildCounter as BuildCounter
import TMoohIManager as TMoohIManager
from TMoohIStatTrack import TMoohIStatTrack
from MoohLog import MoohLogger, filewriter, consolewriter, eventmessage


# This is the main TMoohIServer class. It manages the different clients coming in, the MultiBotManager, the control channel 
# as well as initialisation and message processing.
# Note that it will not interact with IRC directly
class TMoohIServer():
    def __init__(self,config):
        self.BuildInfo = BuildCounter.getVersionInfo("TMoohI",["py","html","css","js"])
        
        self.quitting = False
        #config options
        # host+port: where TMoohI listens for client connections on
        # reference channel: the channel to gather chat_properties from
        # logfile: file to log status messages to
        # status-: status files in the formats specified
        # ref-channel-: channel to check chat_properties for
        
        self.config = {
            "port": 6667,
            "host":"localhost",
            "websockethost": "localhost",
            "websocketport": 3141,
            "logfile":"tmoohi_%Y_%m_%d.log",
            "logfile-loglevel": 10,
            "console-loglevel": 10,
            "status-json":"tmoohi-status.json",
            "cluster-seperator": "@",
			"channels-per-connection": 10
        }
        
        for k in config.__dict__:
            if k in ["servers"]:
                self.config[k] = json.loads(config.__dict__[k])
            else:
                self.config[k] = config.__dict__[k]
        
        if config.config:
            with open(config.config) as f:
                data = yaml.load(f)
                for k in data:
                    self.config[k] = data[k]
        
        self.logger = MoohLogger()
        self.filelogger = filewriter(self.config["logfile"])
        self.filelogger.filters = [{ "level__ge": MoohLogger.DEBUG }]
        self.consolelogger = consolewriter()
        self.consolelogger.filters = [{ "level__ge": MoohLogger.DEBUG }]
        self.logger.writers.append(self.filelogger)
        self.logger.writers.append(self.consolelogger)
        self.logger.info(eventmessage("general","%s loaded"%(self.BuildInfo,)))
        self.logger.info(eventmessage("general","Starting TMoohI server on port %d - CTRL+C to stop"%(self.config["port"],)))
        
        self.websocketserver = TMoohIWebSocketLogger.TMoohIWebsocketServer(self.logger, self.config["websockethost"], self.config["websocketport"])
        
        self.manager = TMoohIManager.TMoohIManager(self)
    
    def quit(self):
        self.quitting = True
        self.manager.quit()
        self.websocketserver.quit()
        self.server.shutdown()
        self.server.server_close()
        
    def run(self):
        self.server = ThreadedTCPServer((self.config["host"],self.config["port"]), TMoohITCPHandler)
        self.server.daemon_threads = True
        self.server.TMoohIParent = self
        self.server.serve_forever()
        #server_thread = threading.Thread(target=self.server.serve_forever)
        #server_thread.daemon = True
        #server_thread.start()

    def __del__(self):
        self.logger.info(eventmessage("general","Stopped TMoohI server."))
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass
class TMoohITCPHandler(socketserver.BaseRequestHandler,TMoohIStatTrack):
    def handle(self):
        self.buffer = ""
        self.nick = ""
        self.oauth = ""
        self.welcomed = False
        self.user = None
        self.starttime = time.time()
        self.commandsent = 0
        linesep = None
        self.stats = {
            "since": time.time(),
            "sent": self.getCommandsSent,
        }
        self.data = None;
        while not self.server.TMoohIParent.quitting:
            try:
                self.data = self.request.recv(1024)
                if not self.data:
                    # client disconnected
                    break
                if self.server.TMoohIParent.quitting:
                    break
                self.server.TMoohIParent.logger.debug(eventmessage("client","Got raw client message from %s (sock ID %d): %s"%(self.client_address[0],self.client_address[1],self.data)))
                self.buffer += self.data.decode("utf-8")
                if not linesep:
                    if "\r\n" in self.buffer:
                        linesep = "\r\n"
                    elif "\r" in self.buffer:
                        linesep = "\r"
                    elif "\n" in self.buffer:
                        linesep = "\n"
                    else:
                        continue
                lines = self.buffer.split(linesep)
                self.buffer = lines[-1]
                for line in lines[:-1]:
                    ex = line.split(" ")
                    if len(ex)>1:
                        if ex[0].upper() == "QUIT":
                            break
                    if self.user:
                        if ex[0].upper() == "PRIVMSG":
                            self.commandsent += 1
                        self.user.handleClientMessage(self, line, True)
                    else:
                        if ex[0] == "NICK":
                            m=re.match("^NICK (\w+)$",line)
                            if m:
                                self.nick = m.group(1)
                                self.server.TMoohIParent.logger.debug(eventmessage("client","NICK command %s"%(m.group(1),)))
                                if self.oauth:
                                    self.user = self.server.TMoohIParent.manager.connect(self)
                            else:
                                self.request.sendall(b"Invalid NICK command!\r\n")
                        elif ex[0] == "PASS":
                            m=re.match("^PASS (oauth:[a-z0-9]+)$",line)
                            if m:
                                self.oauth = m.group(1)
                                self.server.TMoohIParent.logger.debug(eventmessage("client","PASS command %s"%(self.oauth,)))
                                if self.nick:
                                    self.user = self.server.TMoohIParent.manager.connect(self)
                            else:
                                self.request.sendall(b"Invalid PASS command!\r\n")
                                continue
                        else:
                            self.request.sendall(b"No user connected to!\r\n")
            except ConnectionResetError:
                break
            except Exception:
                self.server.TMoohIParent.logger.exception()
        try:
            self.server.TMoohIParent.manager.disconnect(self)
        except Exception:
            self.server.TMoohIParent.logger.exception()
        if self.data:
            self.server.TMoohIParent.logger.debug(eventmessage("client","Client %s disconnected (sock ID %d): %s"%(self.client_address[0],self.client_address[1],self.data)))
        else:
            self.server.TMoohIParent.logger.debug(eventmessage("client","Client %s disconnected (sock ID %d)"%(self.client_address[0],self.client_address[1])))
    
    def getUptime(self):
        return time.time()-self.starttime
    def getCommandsSent(self):
        return self.commandsent

def main(argv):
    parser = argparse.ArgumentParser(description="TMoohI Server")
    parser.add_argument("--config",default="",help="Config file in YAML format")
    args = parser.parse_args()
    srv = TMoohIServer(args)
    uninterrupted = True
    crashtime = 1
    lastcrash = 0
    while uninterrupted:
        try:
            srv.run()
            #while True:
            #    time.sleep(1000)
        except (KeyboardInterrupt,SystemExit):
            uninterrupted = False
            srv.logger.info(eventmessage("general","Stopping TMoohI server."))
            # create a quitter thread
            srv.quit()
            break
        except Exception:
            srv.logger.exception()
            if time.time()-lastcrash < 60*10:
                crashtime *= 8
            else:
                crashtime = 1
            srv.logger.info(eventmessage("general","Restarting TMoohI server in %d seconds."%(crashtime,)))
            time.sleep(crashtime)
            lastcrash = time.time()
if __name__ == '__main__':
    main(sys.argv)
