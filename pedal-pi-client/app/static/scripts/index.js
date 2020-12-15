import React from 'react';
import ReactDOM from 'react-dom';

// ------------
//  Constants
// ------------

// string responses sent by server
var SUCCESS_RETURN = "True";
var FAILURE_RETURN = "False";
var FULL_RETURN = "Full";
var NONE_RETURN = "None";

// ------------
//  Functions
// ------------

// response handler for Ajax request
/*
var ajaxRespHandler = function(data, statusCode) {
    if (statusCode == 200) {
        let dataParts = data.split(" ");

        if (dataParts.length == 3 && dataParts[0] === SUCCESS_RETURN) {
            

     } else {
        console.log(`error code ${statusCode}`);
        console.log(data);
        return "error";
    }
};
*/ 
// checkSession: periodically query localhost getSession method
//                and update webpage accordingly

var checkSession = function() {
    // return $.get(`http://${pedalDomain}/getsession`, ajaxRespHandler);
}

// ---------------------
//  React Superclasses
// ---------------------

class ControlPanel extends React.Component {
    
    constructor(props) {
        super(props);
        this.state = {
            sessionId:  props.sessionId,
            owner:      props.owner,
        };
    }

    render() {
        
        // if pedal offline, sessionId string will be empty
        const inSession = (this.state.sessionId !== "");

        return (
            <div id={inSession ? "onlinecontrolcontainer" : "offlinecontrolcontainer"}>
                <LoopMemberList sessionId={this.state.sessionId} inSession={inSession} />
            </div>
        );
                //<SessionControl sessionId={this.state.sessionId} inSession={inSession} />
    }

}

class LoopMemberList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            sessionId:  props.sessionId,
            inSession:  props.inSession,
            focused:    "loops"
        };
    }

    // switches focus between loops and members menus
    getFocus(elem) {
        this.setState({'focused' : elem});
    }

    render() {
    
        const loopmembercontrol = (
            <div id="loopmembercontrol">
                <div id="loopfocusbutton" onClick={() => this.getFocus("loops")}>
                    LOOPS
                </div>
                <div id="memberfocusbutton" onClick={() => this.getFocus("members")}>
                    MEMBERS
                </div>
            </div>
        );

        const looplist = (
            <ul>
                
            </ul>
        );

        const memberlist = (
            <ul>
                <li>rick</li>
                <li>ash</li>
                <li>matt</li>
            </ul>
        );

        return (
            <>
                {this.state.inSession ? loopmembercontrol : loopmembercontrol}
                <div id="loopcontainer" style={{display: this.state.focused === "loops" ? "flex" : "none" }}>
                    {looplist}
                </div>
                <div id="membercontainer" style={{display: this.state.focused === "members" ? "flex" : "none" }}>
                    {memberlist}
                </div>
            </>
        );
            
    } 
}

            

ReactDOM.render(<ControlPanel sessionId={sessionId} owner={owner} />, document.getElementById("controlcontainer"));

// setInterval(checkSession, 5000);
