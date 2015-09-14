import time
import json
import random
import threading
import urllib.request as urllib2

import MoohLog
import TMoohIUser
import TMoohIConnection
from MoohLog import eventmessage
from TMoohIErrors import RateLimitError
from TMoohIStatTrack import TMoohIStatTrack
from TMoohIChangeCalc import TMoohIChangeTracker

# This is the main manager for anything TMI/twitch API related. It will also bootstrap all the connections that have to be created when the server boots.
# Its parent is the main TMoohI class.
class TMoohIManager(TMoohIStatTrack):
    def __init__(self,parent):
        self.started = time.time()
        self.cachedJSONresponses = dict()
        self.users = {}
        self.parent = parent
        self.logger = parent.logger
        
        self.stats = { "users":self.users, "queue":self.getResendQueueLength, "since":time.time() }
        
        # contains all the messages that couldnt be sent at the given point in time as a tuple (user,client,message)
        self.resendqueue = []
        
        self._createdconnections = []
        self._joinedchannels = []
        self._connectionIDcounter = {}
        self._queuethread = threading.Thread(target=self.handleResendQueue)
        self._queuethread.start()
        
        self._statsTracker = TMoohIChangeTracker(self.serialize())
        self._updatestatusthread = threading.Thread(target=self.updateStatus)
        self._updatestatusthread.start()
        
    def TMIConnectionFactory(self,user,clusterinfo):
        now = time.time()
        self._createdconnections = [i for i in self._createdconnections if i>now-30]
        if len(self._createdconnections)>25:
            raise RateLimitError('Creating connection to %s for user %s'%(clusterinfo[0],user.nick))
        else:
            self._createdconnections.append(now)
            #create a connection
            connkey = "%s@%s"%(user.nick,clusterinfo[0])
            try:
                self._connectionIDcounter[connkey] += 1
            except Exception:
                self._connectionIDcounter[connkey] = 1
            return TMoohIConnection.TMoohIConnection(user,clusterinfo[0],random.choice(clusterinfo[1]),"%s@%s #%d"%(user.nick,clusterinfo[0],self._connectionIDcounter[connkey]))
    
    def connect(self, client):
        for userkey in self.users:
            usr = self.users[userkey]
            if usr.nick == client.nick and usr.oauth == client.oauth:
                usr.welcome(client)
                return usr
        usr = TMoohIUser.TMoohIUser(self,client.nick,client.oauth)
        self.users[usr.key] = usr
        usr.welcome(client)
        print("Created user with key %s"%(usr.key,))
        return usr
    
    def disconnect(self, client):
        try:
            client.user.clients.remove(client)
        except:
            self.logger.exception()
        
    def getClusterInfo(self,channel,oauth=None):
        info = channel.split("@")
        checkchannel = ""
        if len(info)==1:
            if info[0][1]=="_":
                groupOauth = self.parent.config["ref-oauth-group"]
                if oauth:
                    groupOauth = oauth
                if groupOauth.startswith("oauth:"):
                    groupOauth = groupOauth[6:]
                # group chat channel detected
                if groupOauth:
                    # we grab the memberships
                    membershipsResponse = self.getJSON("http://chatdepot.twitch.tv/room_memberships?oauth_token=%s"%(groupOauth,),3600)
                    for room in membershipsResponse["memberships"]:
                        if room["room"]["irc_channel"] == info[0][1:]:
                            return ("group", room["room"]["servers"])
                    # if we havent actually been invited to that room, we just pick the first room.
                    if membershipsResponse["memberships"]:
                        return ("group", membershipsResponse["memberships"][0]["room"]["servers"])
                # fallback: hardcoded server IPs
                return ("group",["199.9.253.119:443","199.9.253.119:6667","199.9.253.119:80","199.9.253.120:443","199.9.253.120:6667","199.9.253.120:80"])
            else:
                # either normalchat or eventchat
                checkchannel = channel
        else:
            if "normalchat".startswith(info[1].lower()):
                checkchannel = self.parent.config["ref-channel-normal"]
            elif "eventchat".startswith(info[1].lower()):
                checkchannel = self.parent.config["ref-channel-event"]
            elif "groupchat".startswith(info[1].lower()):
                groupOauth = self.parent.config["ref-oauth-group"]
                if oauth:
                    groupOauth = oauth
                if groupOauth.startswith("oauth:"):
                    groupOauth = groupOauth[6:]
                if groupOauth:
                    # we grab the memberships (only 30 second cooldown, this is a volatile endpoint)
                    membershipsResponse = self.getJSON("http://chatdepot.twitch.tv/room_memberships?oauth_token=%s"%(groupOauth,),3600)
                    for room in membershipsResponse["memberships"]:
                        if room["room"]["irc_channel"] == channel[1:]:
                            return ("group", room["room"]["servers"])
                    # if we havent actually joined that room, we just pick the first room.
                    if membershipsResponse["memberships"]:
                        return ("group", membershipsResponse["memberships"][0]["room"]["servers"])
                return ("group",["199.9.253.119:443","199.9.253.119:6667","199.9.253.119:80","199.9.253.120:443","199.9.253.120:6667","199.9.253.120:80"])
        if checkchannel:
            # this doesnt change often, so we cache it for a long time.
            chatproperties = self.getJSON("http://api.twitch.tv/api/channels/%s/chat_properties"%(checkchannel[1:],),3600)
            if "error" in chatproperties:
                self.logger.error(eventmessage("connect","Invalid chat properties reference channel %s"%(checkchannel,)))
                return None
            else:
                cluster = "normal"
                if chatproperties["eventchat"]:
                    cluster = "event"
                return (cluster,chatproperties["chat_servers"])
                
    def getJSON(self,url,cooldown=3600):
        try:
            if time.time() < self.cachedJSONresponses[url][0]+cooldown:
                self.logger.debug(eventmessage("json","JSON response from cache: %s"%(url,)))
                return self.cachedJSONresponses[url][1]
        except KeyError:
            pass
        self.logger.debug(eventmessage("json","Downloading JSON from %s"%(url,)))
        res = urllib2.urlopen(url)
        jsdata = res.read().decode("utf-8")
        data = json.loads(jsdata)
        self.cachedJSONresponses[url] = (time.time(), data)
        return data
        
    def handleResendQueue(self):
        unsuccessfulsends = 0
        while True:
            try:
                if len(self.resendqueue)>0:
                    message = self.resendqueue.pop(0)
                    user = message["user"]
                    try:
                        client = message["client"]
                    except KeyError:
                        client = None
                    data = message["message"]
                    self.logger.debug(eventmessage("queue","Dequeing message %s for %s"%(data,user.key)))
                    successfulsend = user.handleClientMessage(client,data)
                    self.logger.debug(eventmessage("queue","handleClientMessage returned with value %s"%(successfulsend,)))
                    if successfulsend:
                        self.logger.debug(eventmessage("queue","handleClientMessage was successful! Queue length: %d, unsuccessful sends: %d"%(len(self.resendqueue),unsuccessfulsends)))
                        unsuccessfulsends = 0
                    else:
                        unsuccessfulsends += 1
                        self.logger.debug(eventmessage("queue","handleClientMessage added a new item to the queue. Queue length: %d, unsuccessful sends: %d"%(len(self.resendqueue),unsuccessfulsends)))
                        if len(self.resendqueue)<=unsuccessfulsends:
                            time.sleep(0.5)
                else:
                    time.sleep(0.5)
            except Exception:
                self.logger.exception()
    
    def getResendQueueLength(self):
        return len(self.resendqueue)
    
    def getUptime(self):
        return time.time()-self.started
    
    def updateStatus(self):
        while(1):
            try:
                serialized = self._statsTracker.update(self.serialize())
                #print(json.dumps(serialized))
                self.logger.log(-1,MoohLog.statsmessage(serialized))
            except Exception:
                self.logger.exception()
            time.sleep(10)
        #self._updatestatustimer.start()
