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

// update session variables every 15 seconds
const UPDATE_PERIOD     = 15000;

// ------------------
//  Global Variables
// ------------------

// -----------
//  Functions
// -----------

var flashMessage = (message, type) => console.log(`${type}: ${message}`);

var listElems = (elem) => <li>{elem}</li>;

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

    // called immediately after object is inserted in the DOM
    // begins update polling interval

    componentDidMount() {
        let intervalId = setInterval(update, UPDATE_PERIOD);
        this.setState({intervalId: intervalId});
    }

    // called immediately before object is removed from the DOM
    // clears update polling interval

    componentWillUnmount() {
        clearInterval(this.state.intervalId);
    }

    // updateSession: query localhost getSession method and update state accordingly

    updateSession() {
        fetch(`http://${pedaldomain}/getsession`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(response.json());
                    }
                return response.json();
                })
            .then(data => {
                    let sessionId, owner;
                    [sessionId, owner] = data;
                    this.setState({sessionId: sessionId, owner: owner});
                })
            .catch(error => flashMessage("Server error while updating session", "error"));
    }

    // updateMembers: query localhost getmembers method and update state accordingly

    updateMembers() {
        fetch(`http://${pedaldomain}/getmembers`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(response.json());
                    }
                return response.json();
                })
            .then(data => this.setState({members: data}))
            .catch(error => flashMessage("Server error while updating member list", "error"));
    }

    // updateLoops: query localhost getmembers method and update state accordingly

    updateLoops() {
        fetch(`http://${pedaldomain}/getloops`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(response.json());
                    }
                return response.json();
                })
            .then(data => this.setState({loops: data}))
            .catch(error => flashMessage("Server error while updating loop list", "error"));
    }

    // update: calls all update methods

    update() {
        updateSession();
        updateMembers();
        updateLoops();
    }

    render() {
        
        // if pedal offline, sessionId string will be empty
        const inSession = (this.state.sessionId !== "");

        return (
            <div id={inSession ? "onlinecontrolcontainer" : "offlinecontrolcontainer"}>
                <LoopMemberList inSession={inSession} loops={this.state.loops} members={this.state.members} />
            </div>
        );
    }

}

class LoopMemberList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            inSession:  props.inSession,
            loops:      props.loops,
            members:    props.members, 
            focused:    "loops"
        };
    }

    // switches focus between loops and members menus
    getFocus(elem) {
        this.setState({'focused' : elem});
    }

    render() {
    
        const loopMemberControl = (
            <div id="loopmembercontrol">
                <div id="loopfocusbutton" onClick={() => this.getFocus("loops")}>
                    LOOPS
                </div>
                <div id="memberfocusbutton" onClick={() => this.getFocus("members")}>
                    MEMBERS
                </div>
            </div>
        );

        return (
            <>
                {this.state.inSession ? loopMemberControl : loopMemberControl}
                <div id="loopcontainer" style={{display: this.state.focused === "loops" ? "flex" : "none" }}>
                    <ul>
                        this.state.loops.map(listElems)
                    </ul>
                </div>
                <div id="membercontainer" style={{display: this.state.focused === "members" ? "flex" : "none" }}>
                    <ul>
                        this.state.members.map(listElems);
                    </ul>
                </div>
            </>
        );
            
    } 
}

            
// root control panel
var controlpanel = ReactDOM.render(<ControlPanel />, document.getElementById("controlcontainer"));
