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

# This is the main manager for anything TMI/twitch API related. It will also bootstrap all the connections that have to be created when the server boots.
# Its parent is the main TMoohI class.
class TMoohIManager(TMoohIStatTrack):
    def __init__(self,parent):
        self.quitting = False
        self.started = time.time()
        self.cachedJSONresponses = dict()
        self.users = {}
        self.parent = parent
        self.logger = parent.logger

        self.stats = { "users":self.users, "queue":self.getResendQueueLength, "since":time.time(), "build": self.parent.BuildInfo.__dict__ }

        # contains all the messages that couldnt be sent at the given point in time as a tuple (user,client,message)
        self.joinqueue = []

        self._createdconnections = []
        self._joinedchannels = []
        self._connectionIDcounter = {}
        self._queuethread = threading.Thread(target=self.handleResendQueue)
        self._queuethread.start()

        self._updatestatusthread = threading.Thread(target=self.updateStatus)
        self._updatestatusthread.start()

    def quit(self):
        self.quitting = True
        for userkey,usr in self.users.items():
            usr.quit()



    def TMIConnectionFactory(self,user,clusterinfo):
        now = time.time()
        self._createdconnections = [i for i in self._createdconnections if i>now-10]
        if len(self._createdconnections)>40:
            raise RateLimitError('Creating connection to %s for user %s'%(clusterinfo[0],user.nick))
        else:
            self._createdconnections.append(now)
            #create a connection
            connkey = "%s/%s"%(clusterinfo[0],user.nick,)
            try:
                self._connectionIDcounter[connkey] += 1
            except Exception:
                self._connectionIDcounter[connkey] = 1
            return TMoohIConnection.TMoohIConnection(user,clusterinfo[0],random.choice(clusterinfo[1]),"%s #%d"%(connkey,self._connectionIDcounter[connkey]))

    def connect(self, client):
        for userkey,usr in self.users.items():
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
        except Exception:
            self.logger.exception()

    def getClusterInfo(self,channel,oauth=None):
        info = channel.split(self.parent.config["cluster-seperator"])
        checkchannel = ""
        if len(info)==1:
            if info[0][1]=="_":
                # group chat channel detected
                if oauth:
                    # we grab the memberships
                    membershipsResponse = self.getJSON("http://chatdepot.twitch.tv/room_memberships?oauth_token=%s"%(oauth[6:],),3600)
                    for room in membershipsResponse["memberships"]:
                        if room["room"]["irc_channel"] == info[0][1:]:
                            return ("group", room["room"]["servers"])
                    # if we havent actually been invited to that room, we just pick the first room.
                    if membershipsResponse["memberships"]:
                        return ("group", membershipsResponse["memberships"][0]["room"]["servers"])
                # fallback: get server IPs from http://tmi.twitch.tv/servers?cluster=group
                return ("group", self.getJSON("http://tmi.twitch.tv/servers?cluster=group", 3600)["servers"])
            else:
                # either normalchat or eventchat
                checkchannel = info[0]
        else:
            if "normalchat".startswith(info[1].lower()):
                checkchannel = self.parent.config["ref-channel-normal"]
            elif "eventchat".startswith(info[1].lower()):
                checkchannel = self.parent.config["ref-channel-event"]
            elif "groupchat".startswith(info[1].lower()):
                return ("group", self.getJSON("http://tmi.twitch.tv/servers?cluster=group", 3600)["servers"])
        if checkchannel:
            # this doesnt change often, so we cache it for a long time.
            chatproperties = self.getJSON("http://api.twitch.tv/api/channels/%s/chat_properties"%(checkchannel[1:],),3600)
            if "error" in chatproperties:
                self.logger.error(eventmessage("connect","Invalid chat properties reference channel %s"%(checkchannel,)))
                return None
            else:

                return (chatproperties["cluster"], chatproperties["chat_servers"])

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
        while not self.quitting:
            try:
                # in each iteration, handle the joinQueue
                while self.joinqueue:
                    if self.quitting:
                        return
                    # dequeue messages and handle them until we meet one that we cannot handle yet
                    message = self.joinqueue.pop(0)
                    user = message["user"]
                    try:
                        client = message["client"]
                    except KeyError:
                        client = None
                    data = message["message"]
                    self.logger.debug(eventmessage("queue","Dequeing message %s for %s"%(data,user.key)))
                    successfulsend = user.handleClientMessage(client,data, False)
                    self.logger.debug(eventmessage("queue","handleClientMessage returned with value %s"%(successfulsend,)))
                    if successfulsend:
                        self.logger.debug(eventmessage("queue","handleClientMessage was successful! Queue length: %d"%(len(self.joinqueue),)))
                    else:
                        self.logger.debug(eventmessage("queue","handleClientMessage added a new item to the queue. Queue length: %d"%(len(self.joinqueue),)))
                        break
                # then handle the messageQueues
                for userkey,usr in self.users.items():
                    usr.handleMessageQueue()
                time.sleep(0.1)
            except Exception:
                self.logger.exception()

    def getResendQueueLength(self):
        return len(self.joinqueue)

    def getUptime(self):
        return time.time()-self.started

    def updateStatus(self):
        cnt = 0
        while not self.quitting:
            if cnt%10==0:
                try:
                    #serialized = self._statsTracker.update(self.serialize())
                    serialized = self.serialize()
                    self.parent.websocketserver.factory.neweststatus = serialized
                    self.logger.log(1,MoohLog.statusmessage(serialized))
                except Exception:
                    self.logger.exception()
            cnt += 1
            time.sleep(1)
        #self._updatestatustimer.start()
