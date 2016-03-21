import time

import TMoohIChannel
from MoohLog import eventmessage
from TMoohIStatTrack import TMoohIStatTrack
from TMoohIErrors import NotConnectedError, TooManyChannelsError, RateLimitError,\
    InvalidChannelError
from TMoohIMessageParser import parseIRCMessage, STATE_PREFIX, STATE_TRAILING, STATE_PARAM, STATE_COMMAND, STATE_V3
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
        
        self.globaluserstate = ""
        
        self.stats = {
            "nick": self.nick,
            "channels": self.channels,
            "clients":self.clients,
            "connections": self.connections,
            "TMIMessages": 0,
            "ClientMessages": 0,
        }
        
        self.messagequeue = []
    
    
    def handleMessageQueue(self):
        while self.messagequeue:
            # dequeue messages and handle them until we meet one that we cannot handle yet
            message = self.messagequeue.pop(0)
            user = message["user"]
            try:
                client = message["client"]
            except KeyError:
                client = None
            data = message["message"]
            self.logger.debug(eventmessage("queue","Dequeing message %s for %s"%(data,user.key)))
            successfulsend = self.handleClientMessage(client,data, False)
            self.logger.debug(eventmessage("queue","handleClientMessage returned with value %s"%(successfulsend,)))
            if successfulsend:
                self.logger.debug(eventmessage("queue","handleClientMessage was successful! Queue length: %d"%(len(self.messagequeue),)))
            else:
                self.logger.debug(eventmessage("queue","handleClientMessage added a new item to the queue. Queue length: %d"%(len(self.messagequeue),)))
                return False
            time.sleep(0.01)
        return True
    
    def quit(self):
        for cluster, connections in self.connections.items():
            for connection in connections:
                connection.quit()
        
    def join(self,channel, appendtoqueue):
        self.logger.debug(eventmessage("channel","Trying to join channel %s"%(channel,)))
        if channel in self.channels:
            self.logger.debug(eventmessage("channel","Couldn't join channel %s: already joined."%(channel,)))
            return True
        if channel[0] != "#":
            raise TypeError("PRIVMSG: Invalid channel %s."%(channel,))
        clusterinfo = self.parent.getClusterInfo(channel)
        # check the ratelimit
        now = time.time()
        self.parent._joinedchannels = [i for i in self.parent._joinedchannels if i>now-10]
        if len(self.parent._joinedchannels)<40:
            channelname = channel.split(self.parent.parent.config["cluster-seperator"])[0]
            if channelname in self.channelsByName[clusterinfo[0]] and len(self.channelsByName[clusterinfo[0]][channelname])>0:
                # if the channelname is already joined, we use its connection, no need to ratelimit:
                refchannel = self.channelsByName[clusterinfo[0]][channelname][0]
                print("Channel "+channelname+ " already joined. Adding and welcoming. Data: %s"%(refchannel.data,))
                channelinfo = TMoohIChannel.TMoohIChannel(self,channel,clusterinfo[0],refchannel.conn)
                # add the channelinfo to channels
                self.channels[channel] = channelinfo
                # add the channelinfo to channelsByName
                self.channelsByName[clusterinfo[0]][channelname].append(channelinfo)
                # now we need to welcome the channel.
                for key,value in refchannel.data.items():
                    if value:
                        channelinfo.data[key] = replaceChannel(value,refchannel.channelkey,channelinfo.channelkey)
                for client in self.clients:
                    channelinfo.welcome(client)
                print("Channel "+channelname+ " already joined. Added and welcomed. Data: %s"%(channelinfo.data,))
                return True
            else:
                # find a connection to use
                for conn in self.connections[clusterinfo[0]]:
                    try:
                        # create channel object - also joins the channel
                        channelinfo = TMoohIChannel.TMoohIChannel(self,channel,clusterinfo[0],conn)
                        # add to global ratelimiter
                        self.parent._joinedchannels.append(now)
                        # add the channelinfo to channels
                        self.channels[channel] = channelinfo
                        # add the channelinfo to channelsByName
                        self.channelsByName[channelinfo.cluster].setdefault(channelinfo.channelname,[]).append(channelinfo)
                        return True
                    except (NotConnectedError, TooManyChannelsError) as e:
                        self.logger.debug(eventmessage("channel","Couldn't join channel %s: %s."%(channel,e)))
                        pass
        else:
            self.logger.debug(eventmessage("channel","Couldn't join channel %s: ratelimit exceeded."%(channel,)))
        # If we reach this, all available connections (if any) were unable to send the join or the request was ratelimited.
        # We create a new one and send the join to the joinqueue. This is ratelimited with 1 connection request per second.
        now = time.time()
        if now-self._lastNewConnectionRequest[clusterinfo[0]]>10:
            self.logger.debug(eventmessage("connection","Requesting new connection"))
            self.connections[clusterinfo[0]].append(self.parent.TMIConnectionFactory(self,clusterinfo))
            self._lastNewConnectionRequest[clusterinfo[0]] = now
        self.logger.debug(eventmessage("channel","Adding JOIN %s to the resend queue. Queue length: %d"%(channel,len(self.parent.joinqueue))))
        if appendtoqueue:
            self.parent.joinqueue.append({"user":self,"message":"JOIN %s"%(channel,)})
        else:
            self.parent.joinqueue.insert(0,{"user":self,"message":"JOIN %s"%(channel,)})
        return False
    
    def part(self,channel,announce=True):
        channelinfo = self.channels[channel]
        # remove from channelsByName
        self.channelsByName[channelinfo.cluster][channelinfo.channelname].remove(channelinfo)
        # if there are no channels for this channelname left, we leave the channel 
        if len(self.channelsByName[channelinfo.cluster][channelinfo.channelname])==0:
            try:
                channelinfo.part()
            except NotConnectedError:
                pass
        # remove from channels
        self.channels.pop(channelinfo.channelkey,None)
        if announce:
            # let the world know we left the channel
            self.broadcast(":{nick}!{nick}@{nick}.tmi.twitch.tv PART {chan}".format(nick=self.nick,chan=channel))
    
    def privmsg(self,message, appendtoqueue):
        if not message[STATE_TRAILING]:
            raise TypeError("PRIVMSG: Trailing data expected")
        
        channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
        allok = True
        for channel in channels:
            if channel[0] != "#":
                raise InvalidChannelError("PRIVMSG: Invalid channel %s."%(channel,))
            channelname = channel.split(self.parent.parent.config["cluster-seperator"],1)[0]
            clusterinfo = self.parent.getClusterInfo(channel,self.oauth)
            for conn in self.connections[clusterinfo[0]]:
                try:
                    conn.privmsg(channelname,message[STATE_TRAILING])
                    break
                except (RateLimitError, NotConnectedError):
                    pass
            else:
                # If we reach this, all available connections (if any) were unable to send the message.
                # We create a new one (cooldown: 3 seconds) and send the message to the messagequeue.
                self.logger.debug(eventmessage("connection","Requesting new connection to %s because of %s"%(clusterinfo[0],message[0])))
                now = time.time()
                if now-self._lastNewConnectionRequest[clusterinfo[0]]>3:
                    self.connections[clusterinfo[0]].append(self.parent.TMIConnectionFactory(self,clusterinfo))
                    self._lastNewConnectionRequest[clusterinfo[0]] = now
                # (re)add to messagequeue. message[0] is the original message
                if appendtoqueue:
                    self.messagequeue.append({"user":self,"message":message[0]})
                else:
                    self.messagequeue.insert(0,{"user":self,"message":message[0]})
                allok = False
        return allok
    
    def handle_client_privmsg(self,client,message, appendtoqueue):
        self.stats["ClientMessages"] += 1
        try:
            return self.privmsg(message, appendtoqueue)
        except InvalidChannelError:
            client.request.sendall((":tmi.twitch.tv 421 tmi.twitch.tv :Invalid PRIVMSG command. Use PRIVMSG #channel :message or PRIVMSG #channel%scluster :message where cluster is either 'normal', 'event' or 'group'\r\n"%(self.parent.parent.config["cluster-seperator"],)).encode("utf-8"))
    
    def handle_client_cap(self,client,message, appendtoqueue):
        client.request.sendall(b":tmi.twitch.tv 410 tmi.twitch.tv :Invalid CAP command. TMoohI always runs twitch.tv/commands and twitch.tv/tags\r\n")
    
    def handle_client_ping(self,client,message, appendtoqueue):
        if message[STATE_PARAM]:
            client.request.sendall((":tmi.twitch.tv PONG tmi.twitch.tv :%s\r\n"%(message[STATE_PARAM][0],)).encode("utf-8"))
        else:
            client.request.sendall((":tmi.twitch.tv PONG tmi.twitch.tv :%s\r\n"%(int(time.time()),)).encode("utf-8"))
        return True
    
    def handle_client_join(self,client,message, appendtoqueue):
        if message[STATE_PARAM]:
            allok = True
            try:
                channels = [y for b in message[STATE_PARAM] for y in b.split(",") if y]
                for channel in channels:
                    ok = self.join(channel, appendtoqueue)
                    allok = ok and allok
            except TypeError:
                self.logger.exception()
                client.request.sendall((":tmi.twitch.tv 420 tmi.twitch.tv :Invalid JOIN command. Use JOIN #channel or JOIN #channel%scluster where cluster is either 'normal', 'event' or 'group'\r\n"%(self.parent.parent.config["cluster-seperator"],)).encode("utf-8"))
            return allok
        else:
            client.request.sendall((":tmi.twitch.tv 420 tmi.twitch.tv :Invalid JOIN command. Use JOIN #channel or JOIN #channel%scluster where cluster is either 'normal', 'event' or 'group'\r\n"%(self.parent.parent.config["cluster-seperator"],)).encode("utf-8"))
        return True
    
    def handle_client_part(self,client,message, appendtoqueue):
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
            client.request.sendall((":tmi.twitch.tv 421 tmi.twitch.tv :Invalid PART command. Use PART #channel or PART #channel%scluster where cluster is either 'normal', 'event' or 'group'\r\n"%(self.parent.parent.config["cluster-seperator"],)).encode("utf-8"))
        return True
        
    
    def handle_client_mode(self,client,message, appendtoqueue):
        client.request.sendall((":tmi.twitch.tv 421 %s %s :Unknown command\r\n"%(self.nick,message[STATE_COMMAND])).encode("utf-8"))
        return True
        
    
    def handle_client_who(self,client,message, appendtoqueue):
        client.request.sendall((":tmi.twitch.tv 421 %s %s :Unknown command\r\n"%(self.nick,message[STATE_COMMAND])).encode("utf-8"))
        return True
    
    def handle_client_conndisc(self,client,message, appendtoqueue):
        cluster = "normal"
        if message[STATE_PARAM]:
            cluster = message[STATE_PARAM]
        for conn in self.connections[cluster]:
            if conn.getConnected():
                conn.disc()
                break
        client.request.sendall((":tmi.twitch.tv 421 %s :Cutting a bot\r\n"%(self.nick,)).encode("utf-8"))
        return True
        
    def handle_client_connkill(self,client,message, appendtoqueue):
        cluster = "normal"
        if message[STATE_PARAM]:
            cluster = message[STATE_PARAM]
        for conn in self.connections[cluster]:
            if conn.getConnected():
                conn.kill()
                break
        client.request.sendall((":tmi.twitch.tv 421 %s :Killing a bot\r\n"%(self.nick,)).encode("utf-8"))
        return True
    
    def handle_client_conndie(self,client,message, appendtoqueue):
        cluster = "normal"
        if message[STATE_PARAM]:
            cluster = message[STATE_PARAM]
        for conn in self.connections[cluster]:
            if conn.getConnected():
                conn.die()
                break
        client.request.sendall((":tmi.twitch.tv 421 %s :A bot passed away...\r\n"%(self.nick,)).encode("utf-8"))
        return True
        
    
    #this takes a client message and handles it. It manages connection counts, channel limits, ratelimits. If it cant send a message at the current point in time, 
    #because of ratelimits or the like, it pushes the message into the TMoohIManager's messagequeue/joinqueue
    # returns True if no message was added to the resentqueue, False if there was.
    def handleClientMessage(self,client,data, appendtoqueue):
        self.logger.debug(eventmessage("message","Handling message %s for %s"%(data,self.key)))
        # parse the message
        message = parseIRCMessage(data)
        cmd = message[STATE_COMMAND].lower()
        
        handler = None
        try:
            handler = getattr(self,"handle_client_%s"%(cmd,))
        except AttributeError:
            pass
        else:
            # they return True if the message could be handled.
            try:
                return handler(client,message, appendtoqueue)
            except Exception:
                self.logger.exception()
            
        return True
    
    # Swallows messages from the user himself and dispatches them
    def handleTMIMessage(self,connection,message):
        ownhostmask = ":{nick}!{nick}@{nick}.tmi.twitch.tv".format(nick=self.nick)
        if message[STATE_PREFIX] == ownhostmask and message[STATE_COMMAND] in ["PRIVMSG",]:
            # eat messages from "myself".
            return
        if message[STATE_COMMAND] in ["001","002","003","004","375","372","376","PONG","CAP"]:
            # eat numeric "welcome" messages as well as pongs and caps.
            return
        if message[STATE_COMMAND] == "GLOBALUSERSTATE":
            self.globaluserstate = message[0]
        params = message[STATE_PARAM]
        if message[STATE_COMMAND] == "PRIVMSG":
            self.stats["TMIMessages"] += 1
        # we find the bound channels and replace them.
        for param in params:
            if param in self.channelsByName[connection.clustername]:
                for targetchannelinfo in self.channelsByName[connection.clustername][param]:
                    # replace the param for each channel and dispatch
                    # if this is part of the welcoming process of the channel, we dont sent it, but keep it back for now.
                    newmessage = replaceChannel(message, param, targetchannelinfo.channelkey)
                    if newmessage[STATE_COMMAND] in targetchannelinfo.data:
                        print("got data message",newmessage)
                        targetchannelinfo.setData(newmessage)
                    self.broadcast(newmessage[0])
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
        client.request.sendall(":tmi.twitch.tv 001 {username} :Welcome, GLHF!\r\n:tmi.twitch.tv 002 {username} :Your host is tmi.twitch.tv\r\n:tmi.twitch.tv 003 {username} :This server is pretty old\r\n:tmi.twitch.tv 004 {username} :{buildinfo} loaded and running smoothly.\r\n:tmi.twitch.tv 375 {username} :-\r\n:tmi.twitch.tv 372 {username} :You are in a maze of dank memes, all alike.\r\n:tmi.twitch.tv 376 {username} :>\r\n".format(username=client.nick,buildinfo=self.parent.parent.BuildInfo).encode("utf-8"))
        client.request.sendall(":tmi.twitch.tv CAP * ACK :twitch.tv/tags\r\n:tmi.twitch.tv CAP * ACK :twitch.tv/commands\r\n".encode("utf-8"))
        if self.globaluserstate:
            client.request.sendall((self.globaluserstate+"\r\n").encode("utf-8"))
        for channelkey,channelobj in self.channels.items():  # @UnusedVariable
            channelobj.welcome(client)
        self.clients.append(client)


def replaceChannel(ex, source, target):
    copy = [None,
            ex[STATE_V3],
            ex[STATE_PREFIX],
            ex[STATE_COMMAND],
            [target if x==source else x for x in ex[STATE_PARAM]],
            ex[STATE_TRAILING]]
    message = ""
    if copy[STATE_V3]:
        message += copy[STATE_V3] + " "
    if copy[STATE_PREFIX]:
        message += copy[STATE_PREFIX] + " "
    message += copy[STATE_COMMAND]
    if copy[STATE_PARAM]:
        message += " " + " ".join(copy[STATE_PARAM])
    if copy[STATE_TRAILING]:
        message += " " + copy[STATE_TRAILING]
    
    copy[0] = message
    return copy
