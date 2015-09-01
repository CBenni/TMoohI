import re
import time
from TMoohIErrors import *

STATE_V3 = 1
STATE_PREFIX = 2
STATE_COMMAND = 3
STATE_PARAM = 4
STATE_TRAILING = 5
	
def parseIRCMessage(message):
	parts = message.split(" ")
	state = 0
	data = [message,"","","",[],""]
	for part in parts:
		if state == STATE_TRAILING:
			pass
		elif state == 0 and part.startswith("@"):
			state = STATE_V3
		elif state < 2 and part.startswith(":"):
			state = STATE_PREFIX
		elif state < 3:
			state = STATE_COMMAND
		elif state >= 3 and part.startswith(":"):
			state = STATE_TRAILING
		else:
			state = STATE_PARAM
			data[state].append(part)
			continue
		if data[state]:
			data[state] += " "
		data[state] += part
	return data
