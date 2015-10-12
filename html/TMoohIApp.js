var TMoohIApp = angular.module("TMoohIApp",['ngMaterial']);

LEVELS = { 0:"DEBUG", 10:"INFO", 20:"WARNING", 30:"ERROR", 40:"EXCEPTION", 50:"FATAL" }


TMoohIApp.controller("StatusController", ["$scope", function($scope){
	var self = this;
	$scope.test = "hi";
	$scope.status = {};
	$scope.loglines = [];
	
	self.websocket = new WebSocket('ws://localhost:3141');
	self.websocket.onopen = function(e) {
		self.websocket.send('[{"level__ge":0},{"type":"stats"}]')
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

function isScrollBottom(element) {
	var elementHeight = element.outerHeight(); 
	var scrollPosition = element[0].scrollHeight - element.scrollTop();
	return (elementHeight == scrollPosition); 
}