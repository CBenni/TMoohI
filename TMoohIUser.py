import time

import TMoohIChannel
from MoohLog import eventmessage
from TMoohIStatTrack import TMoohIStatTrack
from TMoohIErrors import NotConnectedError, TooManyChannelsError, RateLimitError
from TMoohIMessageParser import parseIRCMessage, STATE_PREFIX, STATE_TRAILING, STATE_PARAM, STATE_COMMAND
# This represents a username/oauth combo. It manages TMI connections to all clusters, dispatches messages in both directions and manages channel joins/parts (the ratelimiter is global however)
# Its parent is the TMoohIManager.
class TMoohIUser(TMoohIStatTrack):
    def __init__(self,parent,nick,oauth):
        self.parent = parent
        self.logger = parent.parent.logger
        self.nick = nick
        self.oauth = oauth
        self.key = "%s/%s"%(nick,id(self))
        self.clients = []
        # maps channelkeys (#channel or #channel@cluster) to a TMoohIChannel.
        self.channels = {}
        
        # maps clusters to a dictionary that maps channelnames (#channel) to a list of TMoohIChannels
        self.channelsByName = {"normal":{},"event":{},"group":{}}
        
        # maps cluster (normal,event,group) to a list of TMoohIConnections
        self.connections = {"normal":[],"event":[],"group":[]}
        
        # maps cluster (normal,event,group) to a time, when a connection for that cluster was last requested
        self._lastNewConnectionRequest = {"normal":0,"event":0,"group":0}
        
        self.stats = {
            "nick": self.nick,
            "channels": self.channels,
            "clients":self.clients,
            "connections": self.connections,
            "TMIMessages": 0,
            "ClientMessages": 0,
        }
        
    def join(self,channel):
        self.logger.debug(eventmessage("channel","Trying to join channel %s"%(channel,)))
        if channel in self.channels:
            self.logger.debug(eventmessage("channel","Couldnt join channel %s: already joined."%(channel,)))
            return True
        if channel[0] != "#":
            raise TypeError("PRIVMSG: Invalid channel %s."%(channel,))
        clusterinfo = self.parent.getClusterInfo(channel)
        # check the ratelimit
        now = time.time()
        self.parent._joinedchannels = [i for i in self.parent._joinedchannels if i>now-30]
        if len(self.parent._joinedchannels)<25:
            channelname = channel.split("@")[0]
            if channelname in self.channelsByName[clusterinfo[0]] and len(self.channelsByName[clusterinfo[0]][channelname])>0:
                # if the channelname is already joined, we use its connection, no need to ratelimit:
                refchannel = self.channelsByName[clusterinfo[0]][channelname][0]
                channelinfo = TMoohIChannel(self,channel,clusterinfo[0],refchannel.conn)
                # add the channelinfo to channels
                self.channels[channel] = channelinfo
                # add the channelinfo to channelsByName
                self.channelsByName[clusterinfo[0]][channelname].append(channelinfo)
                # now we need to welcome the channel.
                for key,value in refchannel.data.items():
                    try:
                        channelinfo.data[key] = value.replace(refchannel.channelkey,channelinfo.channelkey)
                    except Exception:
                        pass
                if channelinfo.is_welcomed():
                    for client in self.clients:
                        channelinfo.welcome(client)
                return True
            else:
                # find a connection to use
                for conn in self.connections[clusterinfo[0]]:
                    try:
                        # create channel object - also joins the channel
                        channelinfo = TMoohIChannel(self,channel,clusterinfo[0],conn)
                        # add to global ratelimiter
                        self.parent._joinedchannels.append(now)
                        # add the channelinfo to channels
                        self.channels[channel] = channelinfo
                        # add the channelinfo to channelsByName
                        self.channelsByName[channelinfo.cluster].setdefault(channelinfo.channelname,[]).append(channelinfo)
                        return True
                    except (NotConnectedError, TooManyChannelsError) as e:
                        self.logger.debug(eventmessage("channel","Couldnt join channel %s: %s."%(channel,e)))
                        pass
        else:
            self.logger.debug(eventmessage("channel","Couldnt join channel %s: ratelimit exceeded."%(channel,)))
        # If we reach this, all available connections (if any) were unable to send the join or the request was ratelimited.
        # We create a new one and send the join to the resendqueue. This is ratelimited with 1 connection request per second.
        now = time.time()
        if now-self._lastNewConnectionRequest[clusterinfo[0]]>1:
            self.logger.debug(eventmessage("connection","Requesting new connection"))
            self.connections[clusterinfo[0]].append(self.parent.TMIConnectionFactory(self,clusterinfo))
            self._lastNewConnectionRequest[clusterinfo[0]] = now
        self.logger.debug(eventmessage("channel","Adding JOIN %s to the resend queue. Queue length: %d"%(channel,len(self.parent.resendqueue))))
        self.parent.resendqueue.append((self,None,"JOIN %s"%(channel,)))
        return False
    
    # TODO: 
    def part(self,channel):
        channelinfo = self.channels[channel]
        # remove from channelsByName
        self.channelsByName[channelinfo.cluster][channelinfo.channelname].remove(channelinfo)
        # if there are no channels for this channelname left, we leave the channel 
        if len(self.channelsByName[channelinfo.cluster][channelinfo.channelname])==0:
            channelinfo.part()
        # remove from channels
        self.channels.pop(channelinfo.channelkey,None)
        # let the world know we left the channel
        self.broadcast(":{nick}!{nick}@{nick}.tmi.twitch.tv PART {chan}".format(nick=self.nick,chan=channel))
    
    def privmsg(self,message):
        if not message[STATE_TRAILING]:
            raise TypeError("PRIVMSG: Trailing data expected")
        
        channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
        allok = True
        for channel in channels:
            if channel[0] != "#":
                raise TypeError("PRIVMSG: Invalid channel %s."%(channel,))
            channelname = channel.split("@",1)[0]
            clusterinfo = self.parent.getClusterInfo(channel,self.oauth)
            for conn in self.connections[clusterinfo[0]]:
                try:
                    conn.privmsg(channelname,message[STATE_TRAILING])
                    break
                except (RateLimitError, NotConnectedError):
                    pass
            else:
                # If we reach this, all available connections (if any) were unable to send the message.
                # We create a new one (cooldown: 3 seconds) and send the message to the resendqueue.
                self.logger.debug(eventmessage("connection","Requesting new connection to %s because of %s"%(clusterinfo[0],message[0])))
                now = time.time()
                if now-self._lastNewConnectionRequest[clusterinfo[0]]>3:
                    self.connections[clusterinfo[0]].append(self.parent.TMIConnectionFactory(self,clusterinfo))
                    self._lastNewConnectionRequest[clusterinfo[0]] = now
                self.parent.resendqueue.append((self,None,message))
                allok = False
        return allok
    
    #this takes a client message and handles it. It manages connection counts, channel limits, ratelimits. If it cant send a message at the current point in time, 
    #because of ratelimits or the like, it pushes the message into the TMoohIManager's resendqueue
    # returns True if no message was added to the resentqueue, False if there was.
    def handleClientMessage(self,client,data):
        self.logger.debug(eventmessage("message","Handling message %s for %s"%(data,self.key)))
        # parse the message
        message = parseIRCMessage(data)
        cmd = message[STATE_COMMAND].upper()
        if cmd == "PRIVMSG":
            self.stats["ClientMessages"] += 1
        if cmd == "CAP":
            client.request.sendall(b":tmi.twitch.tv 410 tmi.twitch.tv :Invalid CAP command. TMoohI always runs twitch.tv/commands and twitch.tv/tags\r\n")
        elif cmd == "PING":
            if message[STATE_PARAM]:
                client.request.sendall((":tmi.twitch.tv PONG tmi.twitch.tv :%s\r\n"%(message[STATE_PARAM][0],)).encode("utf-8"))
            else:
                client.request.sendall((":tmi.twitch.tv PONG tmi.twitch.tv :%s\r\n"%(int(time.time()),)).encode("utf-8"))
        elif cmd == "JOIN":
            if message[STATE_PARAM]:
                allok = True
                try:
                    channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
                    for channel in channels:
                        ok = self.join(channel)
                        allok = ok and allok
                except TypeError:
                    self.logger.exception()
                    client.request.sendall(b":tmi.twitch.tv 420 tmi.twitch.tv :Invalid JOIN command. Use JOIN #channel or JOIN #channel@cluster where cluster is either 'normal', 'event' or 'group'\r\n")
                return allok
            else:
                client.request.sendall(b":tmi.twitch.tv 420 tmi.twitch.tv :Invalid JOIN command. Use JOIN #channel or JOIN #channel@cluster where cluster is either 'normal', 'event' or 'group'\r\n")
        elif cmd == "PART":
            ok = True
            if message[STATE_PARAM]:
                channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
                for channel in channels:
                    if channel[0] == "#":
                        self.part(channel)
                    else:
                        ok = False
            else:
                ok = False
            if not ok:
                client.request.sendall(b":tmi.twitch.tv 421 tmi.twitch.tv :Invalid PART command. Use PART #channel or PART #channel@cluster where cluster is either 'normal', 'event' or 'group'\r\n")
            return True
        elif cmd == "PRIVMSG":
            try:
                return self.privmsg(message)
            except Exception:
                client.request.sendall(b":tmi.twitch.tv 421 tmi.twitch.tv :Invalid PRIVMSG command. Use PRIVMSG #channel :message or PRIVMSG #channel@cluster :message where cluster is either 'normal', 'event' or 'group'\r\n")
        elif cmd in ["MODE","WHO"]:
            client.request.sendall((":tmi.twitch.tv 421 %s %s :Unknown command\r\n"%(self.nick,cmd)).encode("utf-8"))
        return True
    
    # Swallows messages from the user himself and dispatches them
    def handleTMIMessage(self,connection,message):
        ownhostmask = ":{nick}!{nick}@{nick}.tmi.twitch.tv".format(nick=self.nick)
        if message[STATE_PREFIX] == ownhostmask and message[STATE_COMMAND] in ["PRIVMSG",]:
            # eat messages from "myself".
            return
        if message[STATE_COMMAND] in ["001","002","003","004","375","372","376"]:
            # eat numeric "welcome" messages.
            return
        params = message[STATE_PARAM]
        if message[STATE_COMMAND] == "PRIVMSG":
            self.stats["TMIMessages"] += 1
        # we find the bound channels and replace them.
        for i in range(len(params)):
            if params[i] in self.channelsByName[connection.clustername]:
                messagemeta = " ".join([x for x in message[1:STATE_PARAM] if x])
                # replace the param for each channel and dispatch
                for targetchannelinfo in self.channelsByName[connection.clustername][params[i]]:
                    # if this is part of the welcoming process of the channel, we dont sent it, but keep it back for now.
                    params[i] = targetchannelinfo.channelkey
                    messageparams = " ".join(params)
                    messagetext = messagemeta
                    if messageparams:
                        messagetext += " "+messageparams 
                    if message[STATE_TRAILING]:
                        messagetext += " "+message[STATE_TRAILING]
                    if message[STATE_COMMAND] in targetchannelinfo.data:
                        waswelcomed = targetchannelinfo.is_welcomed()
                        targetchannelinfo.data[message[STATE_COMMAND]] = messagetext
                        # if the channel is welcomed now, we welcome the clients
                        if ((not waswelcomed) and targetchannelinfo.is_welcomed()):
                            for client in self.clients:
                                targetchannelinfo.welcome(client)
                            continue
                    self.broadcast(messagetext)
                return
        # no channelbound message. Just broadcast then.
        self.broadcast(message[0])
    
    # Sends the message to all connected clients of this user
    def broadcast(self,message):
        try:
            self.logger.debug(eventmessage("raw","Broadcasting message %s"%(message,)))
            for client in self.clients:
                client.request.sendall((message+"\r\n").encode("utf-8"))
        except Exception:
            self.logger.exception()
    
    
    def welcome(self,client):
        client.request.sendall(":tmi.twitch.tv 001 {username} :Welcome, GLHF!\r\n:tmi.twitch.tv 002 {username} :Your host is tmi.twitch.tv\r\n:tmi.twitch.tv 003 {username} :This server is pretty old\r\n:tmi.twitch.tv 004 {username} :{buildinfo} loaded and running smoothly.\r\n:tmi.twitch.tv 375 {username} :-\r\n:tmi.twitch.tv 372 {username} :You are in a maze of twisty passages, all alike.\r\n:tmi.twitch.tv 376 {username} :>\r\n".format(username=client.nick,buildinfo=self.parent.parent.BuildInfo).encode("utf-8"))
        for channelkey,channelobj in self.channels.items():  # @UnusedVariable
            if channelobj.is_welcomed():
                channelobj.welcome(client)
        self.clients.append(client)
