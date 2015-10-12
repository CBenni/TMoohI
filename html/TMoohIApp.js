var TMoohIApp = angular.module("TMoohIApp",[]);

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
		console.log(message)
		if(message.type == "status") {
			$scope.$apply(function(scope){scope.status = message.data});
		}
		else
		{
			$scope.$apply(function(scope){scope.loglines.push(message)});
		}
	}
}]);

TMoohIApp.filter("loglevel",function() {
	return function(input, defaultValue) {
		var exactlevel = parseInt(input);
		var levelname = "Unknown ("+exactlevel+")";
		for(var level in LEVELS) {
			console.log("Comparing exactlevel "+exactlevel+" to level "+level);
			if(level <= exactlevel) {
				levelname = LEVELS[level];
			}
		}
		return levelname;
	}
});