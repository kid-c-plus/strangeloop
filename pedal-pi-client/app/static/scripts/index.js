import React from 'react';
import ReactDOM from 'react-dom';

// -----------
//  Constants
// -----------

// string responses sent by server
const SUCCESS_RETURN    = "True";
const FAILURE_RETURN    = "False";
const FULL_RETURN       = "Full";
const NONE_RETURN       = "None";

// ------------------
//  Global Variables
// ------------------

var sessionId   = "";
var owner       = "";
var members     = [];
var loops       = [];

// -----------
//  Functions
// -----------

var flashMessage = (message, type) => console.log(`${type}: ${message}`);

// --------------------
//  React Superclasses
// --------------------

class ControlPanel extends React.Component {
    
    constructor(props) {
        super(props);
        this.state = {
            sessionId:  "",
            owner:      false,
            members:    [],
            loops:      [],
        };
    }

    // updateSession: periodically query localhost getSession method
    //                and update webpage accordingly

    var updateSession = () => {
        fetch(`http://${pedaldomain}/getsession`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(response.json());
                }
                return response.json());
            .then(data => {
                    let si, o;
                    [si, o] = data;
                    this.setState({sessionId: si, owner: o});
                })
            .catch(error => flashMessage("Server error while updating session", "error"));
    }

    // updateMembers: periodically query localhost getmembers method
    //                and update webpage accordingly

    var updateMembers = () => {
        fetch(`http://${pedaldomain}/getmembers`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(response.json());
                }
                return response.json());
            .then(data => this.setState({members: data})
            .catch(error => flashMessage("Server error while updating member list", "error"));
    }

    // updateLoops: periodically query localhost getmembers method
    //              and update webpage accordingly

    var updateLoops = () => {
        fetch(`http://${pedaldomain}/getloops`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(response.json());
                }
                return response.json());
            .then(data => this.setState({loops: data}))
            .catch(error => flashMessage("Server error while updating loop list", "error"));
    }

    render() {
        
        // if pedal offline, sessionId string will be empty
        const inSession = (this.state.sessionId !== "");

        return (
            <div id={inSession ? "onlinecontrolcontainer" : "offlinecontrolcontainer"}>
                <LoopMemberList sessionId={this.state.sessionId} inSession={inSession} />
            </div>
        );
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

            
// root control panel, update this object's state
var controlpanel = ReactDOM.render(<ControlPanel />, document.getElementById("controlcontainer"));

// setInterval(checkSession, 5000);
