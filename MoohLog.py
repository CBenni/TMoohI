import codecs
import datetime
import re
import sys
import json
import traceback

class MoohLogger(object):
    DEBUG = 0
    INFO = 10
    WARNING = 20
    ERROR = 30
    EXCEPTION = 40
    FATAL = 50
    LEVELS = { DEBUG:"DEBUG", INFO:"INFO", WARNING:"WARNING", ERROR:"ERROR", EXCEPTION:"EXCEPTION", FATAL:"FATAL" }
    def __init__(self):
        self.writers = []
    def log(self,level,data):
        data.level = level
        for writer in self.writers:
            writer.write(data)
    def debug(self,x):
        self.log(MoohLogger.DEBUG,x)
    def info(self,x):
        self.log(MoohLogger.INFO,x)
    def warning(self,x):
        self.log(MoohLogger.WARNING,x)
    def error(self,x):
        self.log(MoohLogger.ERROR,x)
    def fatal(self,x):
        self.log(MoohLogger.FATAL,x)
    def exception(self):
        exc_type, exc_value, exc_traceback = sys.exc_info()
        self.error(eventmessage("exception","".join(traceback.format_exception(exc_type, exc_value,exc_traceback))))
        
class logwriter(object):
    def __init__(self):
        self.filters = [{}]
    def write(self,message):
        if message.meets_filter(self.filters):
            self.inner_write(message)
    def inner_write(self,message):
        raise NotImplementedError
        
        
class filewriter(logwriter):
    def __init__(self,fileformat):
        super(filewriter,self).__init__()
        self.fileformat = fileformat
    def inner_write(self,message):
        try:
            with codecs.open(datetime.datetime.now().strftime(self.fileformat), "a", "utf-8") as myfile:
                myfile.write(str(message)+"\r\n")
        except Exception:
            pass
class consolewriter(logwriter):
    def __init__(self):
        super(consolewriter,self).__init__()
    def inner_write(self,message):
        try:
            print(str(message))
        except Exception:
            pass


MOOHLOGFILTERS = {
    "ge": lambda a,b: float(a)>=float(b),
    "gt": lambda a,b: float(a)>float(b),
    "le": lambda a,b: float(a)<=float(b),
    "lt": lambda a,b: float(a)<float(b),
    "eq": lambda a,b: float(a)==float(b),
    "ne": lambda a,b: float(a)!=float(b),
    "isnull": lambda a,b: (a==None) == b,
    "exact": lambda a,b: a==b,
    "iexact": lambda a,b: a.lower()==b.lower(),
    "containedby": lambda a,b: a in b,
    "icontainedby": lambda a,b: a.lower() in b.lower(),
    "contains": lambda a,b: b in a,
    "icontains": lambda a,b: b.lower() in a.lower(),
    "startswith": lambda a,b: a.startswith(b),
    "endswith": lambda a,b: a.endswith(b),
}


def filter_value(key,val,data):
    # keys starting with ! invert the filter result
    invert = key[0] == "!"
    if invert:
        key = key[1:]
    
    try:
        key_name, query = key.rsplit("__",1)
    except Exception:
        key_name = key
        query = "exact"
        
    keys = key_name.split(".")
    
    try:
        for k in keys:
            data = data[k]
    except Exception:
        return invert
    
    try:
        return MOOHLOGFILTERS[query](data,val) ^ invert
    except Exception:
        pass
    try:
        return (val == data) ^ invert
    except Exception:
        return invert


def filter_dict(data,f):
    # list items are ORed
    for conj in f:
        # dict items are ANDed
        allok = True
        for key, val in conj.items():
            if not filter_value(key, val, data):
                allok = False
        if allok:
            return True
    return False

class logmessage(object):
    def __init__(self,level=0):
        self.level = level
        self.type = "generic"
    
    def meets_filter(self,filters):
        return filter_dict(self.serialize(), filters)
    
    def inner_str(self):
        raise NotImplementedError
    
    def __str__(self):
        levelname = ""
        maxl = -10
        for l,n in MoohLogger.LEVELS.items():
            if l<=self.level:
                if l>maxl:
                    levelname = "[%s] "%(n,)
                    maxl = l
        return levelname+self.inner_str()
    
    def serialize(self):
        return self.__dict__

class chatmessage(logmessage):
    def __init__(self,server,ip,channel,channelid,nick,message):
        self.server = server
        self.ip = ip
        self.channel = channel
        self.id = channelid
        self.nick = nick
        self.message = message
        self.type = "chat"
    
    def inner_str(self):
        return "[{server}] #{channel} <{nick}>: {message}".format(
            server = self.server,
            channel = self.channel,
            nick = self.nickname,
            message = self.message 
        )
        
def reploauth(m):
    return "oauth:(%d)"%(len(m.group(1)),)
class eventmessage(logmessage):
    def __init__(self,event,message):
        self.event = event
        self.message = re.sub("oauth:([a-z0-9]+)",reploauth,message)
        self.type = "event"
    
    def inner_str(self):
        return "[%s] %s"%(self.event,self.message)


class statusmessage(logmessage):
    def __init__(self,stats):
        self.data = stats
        self.type = "status"
    
    def inner_str(self):
        return json.dumps(self.data)




if __name__ == "__main__":
    l = MoohLogger()
    c = consolewriter()
    c.filters = [{"event":"test","level__ge":10}]
    #c.filters.append({"bro_lt":"1337"})
    l.writers.append(c)
    
    l.debug(eventmessage("test","testing events"))
    l.error(eventmessage("test","testing events"))
    l.fatal(eventmessage("test","testing events"))
    
    l.info(statusmessage({"dank":"memes","bro":420}))
