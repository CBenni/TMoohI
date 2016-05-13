import types

class TMoohIStatTrack:
	def __init__(self):
		self.stats = {}
	
	def _update(self):
		pass
	
	def serialize(self):
		data = {}
		self._update()
		for stat,val in self.stats.items():
			data[stat] = self._serialize(val)
		return data
	
	def _serialize(self,obj):
		typ = type(obj)
		if typ is list:
			return [ self._serialize(x) for x in obj ]
		elif typ is dict:
			data = {}
			for key,val in obj.items():
				data[key] = self._serialize(val)
			return data
		elif hasattr(obj, "serialize"):
			return obj.serialize()
		elif typ is types.MethodType:
			return obj()
		else:
			return obj
