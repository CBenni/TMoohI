var TMoohIApp = angular.module("TMoohIApp",['ngMaterial']);

LEVELS = { 0:"DEBUG", 10:"INFO", 20:"WARNING", 30:"ERROR", 40:"EXCEPTION", 50:"FATAL" }

var ws_url = "";

TMoohIApp.controller("StatusController", ["$scope", "$http", "$mdDialog", function($scope, $http, $mdDialog){
	var self = this;
	_self = this;
	_scope = $scope;
	$scope.test = "hi";
	$scope.status = {};
	$scope.loglines = [];
	$scope.collapseFeed = false;
	$scope.selectedChannel = null;
	$scope.selectedConnection = null;
	$scope.filters = [{"level__ge":10},{"type":"status"},{"type":"patch"}];
	self.selectedStatusTab = 0;

    var websocketProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
	self.websocket = new WebSocket(ws_url || websocketProtocol + '//'+window.location.hostname+':3141');
	
	
	self.websocket.onopen = function(e) {
		$scope.$watch("filters", function() {
			self.websocket.send('SETFILTER '+angular.toJson($scope.filters));
		}, true);
	}
	self.websocket.onmessage = function(e) {
		var message = JSON.parse(e.data);
		//console.log(message)
		if(message.type == "status" || message.type == "patch") {
			$scope.$apply(function(){
				if(message.type == "patch") jsonpatch.apply($scope.status, message.data);
				if(message.type == "status") $scope.status = message.data;
				processStatusMessage();
			});
		}
		else
		{
			$scope.$apply(function(scope){
				scope.loglines.push(message);
				scope.loglines=scope.loglines.slice(-500);
			});
		}
	}

	function processStatusMessage() {
		for(var userid in $scope.status.users) {
			var user = $scope.status.users[userid];
			user.channelList = [];
			var connectionDict = {};
			for(var i=0;i<user.connections.length;++i) {
				var conn = user.connections[i];
				connectionDict[conn.id] = conn;
			}
			for(var channelname in user.channels) {
				var channel = user.channels[channelname];
				user.channelList.push(channel);
				channel.state = {
					badges: channel.data.USERSTATE && getBadges(parseIRCMessage(channel.data.USERSTATE)),
					settings: channel.data.ROOMSTATE && getSettings(parseIRCMessage(channel.data.ROOMSTATE)),
					hosting: channel.data.HOSTTARGET && getHosting(parseIRCMessage(channel.data.HOSTTARGET))
				};
				channel.badges = getChannelBadges($http, channel.name.substr(1));
				channel.id = userid+channel.name;
				channel.user = user;
				channel.connectionObj = connectionDict[channel.connection];
			}
		}
	}
	
	self.selectChannel = function(channel) {
		//todo: change from selectedChannel to selectedChannelName
		$scope.selectedChannel = channel;
	}
	
	self.selectConnection = function(userInfo, conn) {
		$scope.selectedConnection = conn;
		conn.user = userInfo;
	}
	
	self.selectClient = function(userInfo, client) {
		$scope.selectedClient = client;
		client.user = userInfo;
	}
	
	$scope.showFilterDialog = function(ev) {
		$mdDialog.show({
			controller: "FilterDialogController",
			templateUrl: 'filterdialog.html',
			targetEvent: ev,
			fullscreen: true,
			preserveScope: true,
			scope: $scope
		}).then(function(newFilters) {
			$scope.filters = newFilters;
		}).catch(function() {
			// do nothing
		});
	}
}]);

TMoohIApp.filter("loglevel",function() {
	var cached = {};
	return function(input, defaultValue) {
		if(cached[input] !== undefined) return cached[input];
		var exactlevel = parseInt(input);
		var levelname = "Unknown ("+exactlevel+")";
		for(var level in LEVELS) {
			if(level <= exactlevel) {
				levelname = LEVELS[level];
			}
		}
		cached[input] = levelname;
		return levelname;
	}
});

TMoohIApp.filter("badgetitle",function() {
	return function(input, defaultValue) {
		return input.replace("_"," ").replace(/\b\w/g,function(m){return m.toUpperCase();});
	}
});

TMoohIApp.controller("FilterDialogController", function($scope, $mdDialog) {
	console.log($scope);
	var oldFilters = $scope.filters;
	var returnValue = $scope.filters;
	function updateFiltersAsPropertyList() {
		var x = [];
		for(var i=0;i<returnValue.length;++i) {
			var f = [];
			var keys = Object.keys(returnValue[i]);
			for(var j=0;j<keys.length;++j) {
				var key = keys[j];
				var match = /(.*)(?:__([a-z]*))/.exec(key) || [key, key, ""];
				f.push({key: match[1], comparator: match[2], value: returnValue[i][keys[j]]});
			}
			x.push(f)
		}
		$scope.filtersAsPropertyList = x;
	}
	updateFiltersAsPropertyList();
	
	$scope.textFilters = angular.toJson(returnValue);
	$scope.updateFilters = function() {
		returnValue = [];
		var l = $scope.filtersAsPropertyList;
		for(var i=0;i<l.length;++i) {
			var f = {};
			for(var j=0;j<l[i].length;++j) {
				var key = l[i][j].key;
				var comp = l[i][j].comparator;
				if(comp && comp.length > 0) key += "__"+l[i][j].comparator;
				var val = l[i][j].value;
				var ival = parseInt(val);
				if(ival.toString() == val) val = ival;
				else {
					var fval = parseFloat(val);
					if(fval.toString() == val) val = fval;
				}
				f[key] = val;
			}
			returnValue.push(f);
		}
		$scope.textFilters = angular.toJson(returnValue);
	};
	
	$scope.ok = function() {
		$scope.filters = returnValue;
		$mdDialog.hide(returnValue);
	}
	
	$scope.apply = function() {
		$scope.filters = returnValue;
	}
	
	$scope.cancel = function() {
		$scope.filters = oldFilters;
		$mdDialog.cancel();
	}
	
	$scope.updateFiltersByText = function() {
		returnValue = JSON.parse($scope.textFilters);
		updateFiltersAsPropertyList();
	}
	
	$scope.addProperty = function(filter) {
		filter.push({key:"",value:"",comparator:""});
		$scope.updateFilters();
	}
	$scope.deleteProperty = function(filter, index) {
		filter.splice(index, 1);
		$scope.updateFilters();
	}
	$scope.addFilter = function(filter) {
		$scope.filtersAsPropertyList.push([{key:"",value:"",comparator:""}]);
		$scope.updateFilters();
	}
	$scope.deleteFilter = function(index) {
		$scope.filtersAsPropertyList.splice(index, 1);
		$scope.updateFilters();
	}
	
	// do nothing so far
});

/*TMoohIApp.filter("userstate",function($sce,$http) {
	var knownuserstates = {};
	return function(input, defaultValue) {
		if(knownuserstates[input[0]]) {
			return knownuserstates[input[0]];
		}
		else {
			knownuserstates[input[0]] = $sce.trustAsHtml(getBadges(input));
		}
	}
	/*var knownuserstates = {};
	var knownalmostuserstates = {};
	return function(input, defaultValue) {
		if(knownuserstates[input[0]]) {
			return knownuserstates[input[0]];
		} else {
			getBadges(input,$http).then(function(data){
				knownuserstates[input[0]] = $sce.trustAsHtml(data);
			},function(data){});
			if(!knownalmostuserstates[input[0]]) {
				knownalmostuserstates[input[0]] = $sce.trustAsHtml(getBadges(input));
			}
			return knownalmostuserstates[input[0]];
		}
	}*
});*/

TMoohIApp.directive('scrollToBottom', function () {
	return {
		link: function (scope, element) {
			$elem = $(element);
			var isScrolledToBottom = isScrollBottom($elem);
			var oldScrollTop = 0;
			$elem.scroll(function(event){
				var newScrollTop = $(element).scrollTop();
				var newIsScrolled = isScrollBottom($elem);
				if(newScrollTop < oldScrollTop || newIsScrolled) {
					isScrolledToBottom = newIsScrolled;
				}
				oldScrollTop = newScrollTop;
			});
			$elem.on('DOMNodeInserted', function (event) {
				if(isScrolledToBottom == true) {
					setTimeout(function(){$(element).scrollTop($(element)[0].scrollHeight);},1);
				}
			});
		}
	}
});


TMoohIApp.directive('timeSince', ["$interval", function ($interval) {
	return {
		scope: {
			timeSince: "="
		},
		link: function ($scope, element, attrs) {
			var startTime = parseFloat($scope.timeSince);
			var interval = $interval(updateTime, 1000);

			// used to update the UI
			function updateTime() {
				startTime = parseFloat($scope.timeSince);
				element.text(formatTimeSpan(new Date().getTime()/1000.0 - startTime));
			}
			updateTime();

			element.on('$destroy', function() {
				$interval.cancel(interval);
			});
		}
	}
}]);

function twoDigitNumber(number) {
	if (number<=9) return "0"+number;
	return ""+number;
}

function formatTimeSpan(dt) {
	var days = Math.floor(dt/86400);
	var hrs = Math.floor((dt - days * 86400) / 3600);
	var mins = Math.floor((dt - days * 86400 - hrs * 3600) / 60);
	var secs = Math.floor(dt - days * 86400 - hrs * 3600 - mins * 60);
	result = "";
	if(days > 1) {
		result += days + " days ";
	}
	else if(days == 1) {
		result += days + " day ";
	}
	result += twoDigitNumber(hrs)+":"+twoDigitNumber(mins)+":"+twoDigitNumber(secs);
	return result;
}

function isScrollBottom(element) {
	var elementHeight = element.outerHeight();
	var scrollPosition = element[0].scrollHeight - element.scrollTop();
	return (elementHeight == scrollPosition);
}
