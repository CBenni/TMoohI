STATE_V3 = 1
STATE_PREFIX = 2
STATE_COMMAND = 3
STATE_PARAM = 4
STATE_TRAILING = 5

function parseIRCMessage(message)
{
	parts = message.split(" ");
	state = 0;
	data = [message,"","","",[],""];
	for(var i=0;i<parts.length;i++)
	{
		part = parts[i];
		if(state == STATE_TRAILING)
		{
		}
		else if(state == 0 && part[0] == "@")
		{
			state = STATE_V3;
		}
		else if(state < 2 && part[0] == ":")
		{
			state = STATE_PREFIX;
		}
		else if(state < 3)
		{
			state = STATE_COMMAND;
		}
		else if(state >= 3 && part[0] == ":")
		{
			state = STATE_TRAILING;
		}
		else
		{
			state = STATE_PARAM;
			data[state].push(part);
			continue;
		}
		if(data[state])
		{
			data[state] += " ";
		}
		data[state] += part
	}
	return data
}

function splitWithTail(str,delim,count){
	var parts = str.split(delim);
	var tail = parts.slice(count).join(delim);
	var result = parts.slice(0,count);
	result.push(tail);
	return result;
}
var _channelBadgeCache = {
	"": {
		"global_mod": {
			"alpha": "http://chat-badges.s3.amazonaws.com/globalmod-alpha.png",
			"image": "http://chat-badges.s3.amazonaws.com/globalmod.png",
			"svg": "http://chat-badges.s3.amazonaws.com/globalmod.svg"
		},
		"admin": {
			"alpha": "http://chat-badges.s3.amazonaws.com/admin-alpha.png",
			"image": "http://chat-badges.s3.amazonaws.com/admin.png",
			"svg": "http://chat-badges.s3.amazonaws.com/admin.svg"
		},
		"broadcaster": {
			"alpha": "http://chat-badges.s3.amazonaws.com/broadcaster-alpha.png",
			"image": "http://chat-badges.s3.amazonaws.com/broadcaster.png",
			"svg": "http://chat-badges.s3.amazonaws.com/broadcaster.svg"
		},
		"mod": {
			"alpha": "http://chat-badges.s3.amazonaws.com/mod-alpha.png",
			"image": "http://chat-badges.s3.amazonaws.com/mod.png",
			"svg": "http://chat-badges.s3.amazonaws.com/mod.svg"
		},
		"staff": {
			"alpha": "http://chat-badges.s3.amazonaws.com/staff-alpha.png",
			"image": "http://chat-badges.s3.amazonaws.com/staff.png",
			"svg": "http://chat-badges.s3.amazonaws.com/staff.svg"
		},
		"turbo": {
			"alpha": "http://chat-badges.s3.amazonaws.com/turbo-alpha.png",
			"image": "http://chat-badges.s3.amazonaws.com/turbo.png",
			"svg": "http://chat-badges.s3.amazonaws.com/turbo.svg"
		},
		"subscriber": null,
		"_links": {
			"self": "https://api.twitch.tv/kraken/chat/cbenni/badges"
		}
	}
};

function getChannelBadges($http,channel) {
	/*
	 * load badges json (from cache) and return a promise
	 */
	var cached = _channelBadgeCache[channel];
	if(cached) {
		return _channelBadgeCache[channel];
	}
	else {
		$http.jsonp("https://api.twitch.tv/kraken/chat/"+channel+"/badges?callback=JSON_CALLBACK",{"cache":true}).then(function(resp){
			_channelBadgeCache[channel] = resp.data;
		},function(resp){
			return "ERROR";
		});
		return _channelBadgeCache[""];
	}
}

function getBadges(parsedmessage) {
	/*
	 * get the badges from the data
	 */
	var tags = {};
	var v3data = parsedmessage[STATE_V3].substring(1).split(";");
	for(var i=0;i<v3data.length;i++) {
		keyval = splitWithTail(v3data[i],"=",1)
		tags[keyval[0]] = keyval[1]
	}
	
	var nick = parsedmessage[STATE_PREFIX].match(/:(\w+)/)[1]
	var channel = parsedmessage[STATE_PARAM][0].match(/#(\w+)/)[1]
	var badges = []
	// moderation badge
	if(nick == channel) {
		badges.push("broadcaster");
	}
	if(tags["user-type"] != "") {
		badges.push(tags["user-type"]);
	}
	if(tags["subscriber"]=="1") {
		badges.push("subscriber")
	}
	if(tags["turbo"]=="1") {
		badges.push("turbo")
	}
	return badges;
	/*var channelBadges = _channelBadgeCache[channel];
	if(channelBadges === undefined) {
		channelBadges = _channelBadgeCache[""];
	}
	var result = "";
	for(var i=0;i<badges.length;i++) {
		var badgetype = badges[i];
		var badgeinfo = channelBadges[badgetype];
		if(badgeinfo) {
			badgetitle = badgetype.replace("_"," ").replace(/\b\w/g,function(m){return m.toUpperCase();});
			result += '<img src="' + badgeinfo.image + '" title="' + badgetitle + '" class="logviewer-badge logviewer-badge-' + badgetype + '">';
		}
	}*/
}