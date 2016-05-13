class RateLimitError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class TooManyChannelsError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class InvalidCommandError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class InvalidChannelError(Exception):
	def __init__(self, value):
		self.value = value
	def __str__(self):
		return repr(self.value)

class NotConnectedError(Exception):
	def __init__(self):
		pass
	def __str__(self):
		return "NotConnectedError"

class BubbleEvent(Exception):
	def __init__(self):
		pass
	def __str__(self):
		return "BubbleEvent"
