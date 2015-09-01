import re
import time

STATE_V3 = 1
STATE_PREFIX = 2
STATE_COMMAND = 3
STATE_PARAM = 4
STATE_TRAILING = 5

NFA_RULES = [
	[STATE_V3,STATE_PREFIX,STATE_COMMAND],		# state 0 (start of line)
	[STATE_PREFIX,STATE_COMMAND],				# state 1 (IRCv3 data)
	[STATE_COMMAND,],							# state 2 (prefix data)
	[STATE_PARAM,STATE_TRAILING],				# state 3 (command data)
	[STATE_PARAM,STATE_TRAILING],				# state 5 (parameter data)
	[STATE_TRAILING],							# state 6 (trailing data)
]
NFA_REGEX = [
	None,
	re.compile("^@"),							#STATE_V3
	re.compile("^:"),							#STATE_PREFIX
	re.compile("^(?:[a-zA-Z]+|\d\d\d)$"),		#STATE_COMMAND
	re.compile("^[^:]"),						#STATE_PARAM
	re.compile(""),								#STATE_TRAILING
]

def parseIRCMessage(message):
	parts = message.split(" ")
	return _parseIRCMessageByParts(parts)
	
def _parseIRCMessageByParts(parts):
	state = 0
	data = {}
	for part in parts:
		validcommand = False
		for possiblestate in NFA_RULES[state]:
			if NFA_REGEX[possiblestate].match(part):
				state = possiblestate
				data.setdefault(state,[]).append(part)
				validcommand = True
				break
		if not validcommand:
			raise InvalidCommandError("Invalid command. Part %s and state %d"%(part,state))
	try:
		data[STATE_TRAILING] = " ".join(data[STATE_TRAILING])
	except KeyError:
		pass
	return data

if __name__ == '__main__':
	with open(r"D:\Eigene Dateien\Programmierung\Python\raw2.txt","r", encoding="utf-8") as f:
		st = time.time()
		msgcnt = 0
		for line in f:
			s = line.replace("\n","").split(" ")
			res = _parseIRCMessageByParts(s[1:])
			msgcnt += 1
		print("DONE! Parsed %d messages, took me %.10f milliseconds!"%(msgcnt,(time.time()-st)*1000,))
	while 1:
		m = input('> ')
		print(parseIRCMessage(m))
