from collections import OrderedDict
from TMoohIStatTrack import TMoohIStatTrack
from TMoohIMessageParser import STATE_COMMAND, parseIRCMessage, STATE_V3
from lib.TMoohIMessageParser import getIRCv3Info
# represents a #channel@cluster or #channel object. It is used to track the ROOMSTATE, USERSTATE etc, in order to properly welcome users.
# the parent is a TMoohIUser
class TMoohIChannel(TMoohIStatTrack):
    def __init__(self,parent,channelkey,cluster,connection):
        self.channelkey = channelkey
        self.channelname = channelkey.split("@")[0]
        self.cluster = cluster
        self.parent = parent
        self.conn = connection
        # maps a command type (ROOMSTATE, HOSTTARGET, USERSTATE, numeric) to a full message
        self.data = OrderedDict.fromkeys(["JOIN","353","366","USERSTATE","ROOMSTATE","HOSTTARGET"])
        self.join()
        
        self.stats = {
            "name": self.channelname,
            "key": self.channelkey,
            "cluster": self.cluster,
            "data": self.dataDict
        }
    
    def setData(self,ex):
        if ex[STATE_COMMAND] == "ROOMSTATE":
            currentex = self.data["ROOMSTATE"]
            if currentex:
                currentv3tags = getIRCv3Info(currentex)
                v3tags = getIRCv3Info(ex)
                currentv3tags.update(v3tags)
                newv3info = "@"+(";".join(["%s=%s"%(key,val) for key,val in currentv3tags.items()]))
                currentex[0] = newv3info + " " + currentex[0].split(" ",1)[1]
                currentex[STATE_V3] = newv3info
                return
        self.data[ex[STATE_COMMAND]] = ex
        
    def dataDict(self):
        return dict(self.data)
        
    def welcome(self,client):
        for key,val in self.data.items():  # @UnusedVariable
            if val:
                client.request.sendall((val[0]+"\r\n").encode("utf-8"))
    
    def is_welcomed(self):
        return self.data["ROOMSTATE"]!=None
    
    def part(self):
        self.conn.part(self)
    
    def join(self):
        self.conn.join(self)
