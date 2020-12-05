// ------------
//  Constants
// ------------

// string responses sent by server
var SUCCESS_RETURN = "True"
var FAILURE_RETURN = "False"
var FULL_RETURN = "Full"
var NONE_RETURN = "None"

// all web elements that are enabled when user is out of session
var enabledOutOfSession = ["newsessionnick", "newsessionsubmit", "joinsessionid", "joinsessionsubmit"]

// all web elements that are enabled when user is in session
var enabledInSession = ["leavsessionsubmit"]

// all web elements that are enabled when user is owner of session
var enabledWhenOwner = ["endsessionsubmit"]

// -------------------
//  Helper Functions
// -------------------

// remove "disabled" attribute from element with given id

var enableElem = function(element) {
    $(`#${element}`).prop("disabled", false);
};

// add "disabled" attribute to element with given id

var disableElem = function(element) {
    $(`#${element}`).prop("disabled", true);
};

// ------------
//  Functions
// ------------

//  checkSession: periodically query localhost getSession method
//                and update webpage accordingly

var checkSession = function() {

    // response handler for Ajax request
    var ajaxRespHandler = function(data, statusCode) {
        if (statusCode == 200) {
            var dataParts = data.split(" ");
            var sessionIdElem = $("#sessionid");
            var ownerElem = $("#owner");

            if (dataParts.length == 3 && dataParts[0] === SUCCESS_RETURN) {
                sessionIdElem.text = dataParts[1];
                if (!inSession) {
                    enabledOutOfSession.forEach(disableElem);
                    enabledInSession.forEach(enableElem);
                    inSession = true;
                }
                sessionIDElem.text = dataParts[2];
                if (dataParts[1] === "owner" && !owner) {
                    enabledWhenOwner.forEach(enableElem);
                    owner = true;
                } else if (dataParts[1] === "member" && owner) {
                    enabledWhenOwner.forEach(disableElem);
                }
            } else {
                if (dataParts[0] == NONE_RETURN) {
                    sessionIdElem.text = "No Session";
                    if (inSession) {
                        enabledInSession.concat(enabledWhenOwner).forEach(disableElem);
                        inSession = false;
                    }
                } else {
                    sessionIdElem.text = "Server Error";
                }
                ownerElem.text("&nbsp");
            }
        } else {
            console.log(`error code ${statusCode}`);
            console.log(data);
        }
    };

    $.get("http://localhost/getsession", ajaxRespHandler);
}

setInterval(checkSession, 500);
