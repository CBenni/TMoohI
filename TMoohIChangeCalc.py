class TMoohIChangeTracker:
    def __init__(self,val):
        # costs
        self.COST_INSERT = 10
        self.COST_REMOVE = 10
        self.COST_REPLACE = 10
        self.COST_BADREPLACE = 15

        # insert: 1
        # change: 2
        # delete: 3
        self.LS_NONE = "none"
        self.LS_INSERT = "insert"
        self.LS_CHANGE = "change"
        self.LS_REPLACE = "replace"
        self.LS_REMOVE = "delete"
        
        self.oldval = val

    def list_levenshtein(self,s,t):
        # degenerate cases
        m = len(s)
        n = len(t)
        
        d = [[(0,)]*(n+1) for x in range(m+1)]
        for i in range(m):
            d[i+1][0] = (i+1,i,0,(self.LS_REMOVE,))
        for j in range(n):
            d[0][j+1] = (j+1,0,j,(self.LS_INSERT,t[j]))
        
        for j in range(n):
            for i in range(m):
                change = self.calc_changes(s[i],t[j])
                if change == self.LS_NONE:
                    d[i+1][j+1] = (d[i][j][0],i,j,self.LS_NONE)
                else:
                    d[i+1][j+1] = min(
                        (d[i][j][0]+change[0],i,j,(self.LS_CHANGE,change[1])),        # change
                        (d[i][j+1][0]+self.COST_REMOVE,i,j+1,(self.LS_REMOVE,)),            # delete
                        (d[i+1][j][0]+self.COST_INSERT,i+1,j,(self.LS_INSERT,t[j])),        # insert
                    )
        
        # reconstruct changes
        i = m
        j = n
        
        res = []
        nonecnt = 0
        skipnone = True
        while(i > 0 or j > 0):
            x = d[i][j]
            i = x[1]
            j = x[2]
            if x[3]==self.LS_NONE:
                if skipnone:
                    continue
                nonecnt += 1
                if nonecnt>1:
                    res[0] = "%s*%d"%(self.LS_NONE,nonecnt,)
                    continue
            else:
                nonecnt = 0
                skipnone = False
            res.insert(0,x[3])
        return (d[m][n][0],res)

    # returns (cost,changes)
    def calc_changes(self,a,b):
        if a==b:
            return self.LS_NONE
        elif type(a) != type(b):
            return (self.COST_BADREPLACE,[self.LS_REPLACE,b])
        else:
            if type(a) is list:
                ls = self.list_levenshtein(a,b)
                return (int(ls[0]/2),ls[1])
            elif type(a) is dict:
                cost = 0
                res = {}
                for key in a:
                    if key in b:
                        change = self.calc_changes(a[key],b[key])
                        if change == self.LS_NONE:
                            continue
                        else:
                            cost += change[0]
                            res[key] = (self.LS_CHANGE,change[1])
                    else:
                        cost += self.COST_REMOVE
                        res[key] = (self.LS_REMOVE,)
                for key in b:
                    if key not in a:
                        cost += self.COST_INSERT
                        res[key] = (self.LS_INSERT,b[key])
                return (int(cost/2),res)
            else:
                return (self.COST_REPLACE,(self.LS_REPLACE,b))
    
    def update(self,b):
        chg = self.calc_changes(self.oldval,b)
        self.oldval = b
        return chg
