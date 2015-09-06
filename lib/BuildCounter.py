import os
import hashlib
import json

def getVersionInfo(projectname,extensions=None):
    bi = BuildInfo(projectname)
    try:
        with open('%s_version.json'%(projectname,), 'a+') as f:
            f.seek(0)
            bi.data = json.load(f)
    except:
        pass
    h = hashlib.md5()
    for root, directories, filenames in os.walk('.'):
        for fn in filenames: 
            filename = os.path.join(root, fn)
            ext = filename.rsplit(".",1)[-1]
            if extensions==None or ext in extensions:
                with open( filename , "rb" ) as f:
                    while True:
                        buf = f.read(128)
                        if not buf:
                            break
                        h.update( buf )
    newhash = h.hexdigest()
    if newhash != bi.data["hash"]:
        bi.data["hash"] = newhash
        bi.data["build"] += 1
        with open('%s_version.json'%(projectname,), 'w') as f:
            json.dump(bi.data,f)
    return bi
    
class BuildInfo:
    def __init__(self,projectname,data=None):
        self.projectname = projectname
        if data:
            self.data = data
        else:
            self.data = {"hash":"","build":0,"version":"0.0.1"}
    
    def __repr__(self):
        return "BuildInfo(%s)"%(self.data,)
    
    def __hash__(self):
        return hash(self.data["hash"])
    
    def __str__(self):
        return "%s v%s (Build %d)"%(self.projectname,self.data["version"],self.data["build"])

if __name__ == '__main__':
    bi = getVersionInfo("BuildCounterTest",["py"])
    print(bi)
    print(repr(bi))
    print(hash(bi))
