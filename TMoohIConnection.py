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
    def __init__(self,parent,cluster,server,connid):
        self.connected = False
        self.killing = False
        self.dead = False
        self.ignoring = False
        self.connid = connid
        
        self.lastmessage = time.time()
        
        self.parent = parent
        self.manager = parent.parent
        self.logger = self.manager.parent.logger
        self.logger.info(eventmessage("connect","Connection ID %s created!"%(self.connid,)))
        
        # list of TMoohIChannels that are supposed to be joined by this connection.
        self.channels = []
        # list of TMoohIChannels that are actually joined by this connection.
        self.joinedchannels = []
        # list of unique channelnames that are joined by this connection.
        self.channelnames = []
        
        
        self.clustername = cluster
        srvinfo = re.split("[^\d\w\.]",server)
        self.port = 443
        self.server = server
        self.ip = self.server
        if len(srvinfo) == 2:
            self.port = int(srvinfo[1])
            self.ip = srvinfo[0]
        
        self.stats = {
            "server": "%s:%s"%(self.ip, self.port),
            "id": self.connid,
            "connected": self.getConnected,
            "channels": self.channels,
            "joinedchannels": self.joinedchannels
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
    
    def connect(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((self.ip, self.port))
        self._recvthread = threading.Thread(target=self.listen)
        self._recvthread.start()
        self.logger.info(eventmessage("connect","Connecting to %s/%s for %s"%(self.ip, self.port, self.connid)))
        if self.parent.oauth:
            self.sendraw("PASS %s"%(self.parent.oauth,))
        self.sendraw("USER %s %s %s :%s"%(self.parent.nick,self.parent.nick,self.parent.nick,self.parent.nick,))
        self.sendraw("NICK %s"%(self.parent.nick,))
        self.sendraw("CAP REQ :twitch.tv/tags\r\nCAP REQ :twitch.tv/commands")
    
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
                    self.logger.debug(eventmessage("raw","Got raw TMI message in connection %s: %s"%(self.connid,line)))
                    try:
                        ex = parseIRCMessage(line)
                    except Exception:
                        self.logger.exception()
                    if(ex[STATE_COMMAND]=="PING"):
                        self.sendraw("PONG")
                    elif ex[STATE_COMMAND]=="376":
                        self.connected = True
                        self.logger.info(eventmessage("connect","Connection ID %s connected!"%(self.connid,)))
                    elif ex[STATE_COMMAND]=="JOIN":
                        try:
                            self.joinedchannels.append(ex[STATE_PARAM][0])
                            self.parent.handleTMIMessage(self, ex)
                            self.logger.info(eventmessage("channel","Joined channel "+ex[STATE_PARAM][0]))
                        except Exception:
                            self.logger.exception()
                    else:
                        self.parent.handleTMIMessage(self, ex)
        except ConnectionAbortedError:
            pass
        except Exception:
            self.logger.exception()
        self.connected = False
        self.parent.connections[self.clustername].remove(self)
        if self.killing:
            self.logger.info(eventmessage("connect","Connection ID %s killed!"%(self.connid,)))
        else:
            self.logger.error(eventmessage("connect","Connection ID %s disconnected!"%(self.connid,)))
            for channel in self.channels:
                self.parent.part(channel.channelkey,announce = True)
                self.manager.resendqueue.append({"user":self.parent,"message":"JOIN %s"%(channel.channelkey,)})
    
    def sendraw(self,x):
        self.logger.debug(eventmessage("raw","Sending a RAW TMI message on bot %s: %s"%(self.connid,x)))
        self._socket.send((x+"\r\n").encode("utf-8"))
    
    def privmsg(self,channelname,message):
        if not self.connected:
            raise NotConnectedError()
        now = time.time()
        self._sentmessages = [i for i in self._sentmessages if i>now-30]
        if len(self._sentmessages)>15:
            raise RateLimitError('Sending "PRIVMSG %s :%s" on connection ID %s'%(channelname,message,self.connid))
        else:
            self.sendraw("PRIVMSG %s %s"%(channelname,message))
            self._sentmessages.append(now)
    
    # joins the channel if it isnt joined yet, else just adds it to the list
    def join(self,channelinfo):
        if not self.connected:
            raise NotConnectedError()
        if channelinfo.channelname in self.channelnames:
            self.channels.append(channelinfo)
        else:
            if len(self.channelnames)>=10:
                raise TooManyChannelsError(len(self.channels))
            else:
                self.sendraw("JOIN %s"%(channelinfo.channelname,))
                self.channels.append(channelinfo)
                self.channelnames.append(channelinfo.channelname)
    
    # actually parts the channelname
    def part(self,channelinfo):
        if not self.connected:
            raise NotConnectedError()
        if channelinfo not in self.channels:
            raise KeyError()
        self.sendraw("PART %s"%(channelinfo.channelname,))
        self.channels.remove(channelinfo)
        self.channelnames.remove(channelinfo.channelname)
    
    
    def _update(self):
        now = time.time()
        dt = now-self.lastmessage
        if dt > 30:
            self.logger.error(eventmessage("connect","Bot %s got silently disconnected. Enabling dead mode."%(self.connid,)))
            self.connected = False
            self.dead = True
            self._socket.close()
        elif dt > 15:
            self.logger.debug(eventmessage("connect","Bot %s has not received messages in %d seconds. Pinging TMI server."%(self.connid,int(dt))))
            self.sendraw("PING")
                
    
    def kill(self):
        """
        Simulates the socket getting killed
        """
        self.logger.info(eventmessage("kill","Killing bot %s"%(self.connid,)))
        self.killing = True
        self.connected = False
        self._socket.close()
    
    def disc(self):
        """
        Simulates the connection being closed
        """
        self.logger.info(eventmessage("kill","Disconnecting bot %s"%(self.connid,)))
        self.sendraw("PRIVMSG #jtv :/DISCONNECT")
    
    def die(self):
        """
        Simulates the server silently disconnecting us
        """
        self.logger.info(eventmessage("kill","Dieing bot %s"%(self.connid,)))
        self.ignoring = True
            
