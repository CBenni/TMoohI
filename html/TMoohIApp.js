var TMoohIApp = angular.module("TMoohIApp",['ngSanitize','ngMaterial']);

LEVELS = { 0:"DEBUG", 10:"INFO", 20:"WARNING", 30:"ERROR", 40:"EXCEPTION", 50:"FATAL" }


TMoohIApp.controller("StatusController", ["$scope", function($scope){
	var self = this;
	$scope.test = "hi";
	$scope.status = {};
	$scope.loglines = [];

	self.websocket = new WebSocket('ws://localhost:3141');
	self.websocket.onopen = function(e) {
		self.websocket.send('SETFILTER [{"level__ge":0},{"type":"stats"}]')
	}
	self.websocket.onmessage = function(e) {
		var message = JSON.parse(e.data);
		//console.log(message)
		if(message.type == "status") {
			$scope.$apply(function(scope){scope.status = message.data});
		}
		else
		{
			$scope.$apply(function(scope){scope.loglines.push(message);scope.loglines=scope.loglines.slice(-500)});
		}
	}
}]);

TMoohIApp.filter("loglevel",function() {
	return function(input, defaultValue) {
		var exactlevel = parseInt(input);
		var levelname = "Unknown ("+exactlevel+")";
		for(var level in LEVELS) {
			if(level <= exactlevel) {
				levelname = LEVELS[level];
			}
		}
		return levelname;
	}
});

TMoohIApp.filter("userstate",function($sce,$http) {
	var knownuserstates = {};
	var knownalmostuserstates = {};
	return function(input, defaultValue) {
		if(knownuserstates[input[0]]) {
			return $sce.trustAsHtml(knownuserstates[input[0]]);
		} else {
			getBadges(input,$http).then(function(data){
				knownuserstates[input[0]] = data;
			},function(data){});
			if(!knownalmostuserstates[input[0]]) {
				knownalmostuserstates[input[0]] = getBadges(input)
			}
			return $sce.trustAsHtml(knownalmostuserstates[input[0]]);
		}
	}
});

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
