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
const COLLISION_RETURN  = "Collision";

// update session variables every 15 seconds
const UPDATE_PERIOD     = 2500;

// ------------------
//  Global Variables
// ------------------

var numberToWords = require('number-to-words');

// -----------
//  Functions
// -----------

var flashMessage = (type, message) => console.log(`${type}: ${message}`);

var fetchRespHandler = (response) => {
    if (!response.ok) {
        throw Error(response.json());
        }
    return response.json();
}

// --------------------
//  React Superclasses
// --------------------

class ControlPanel extends React.Component {
    
    constructor(props) {
        super(props);
        this.state = {
            sessionId:  null,
            owner:      null,
            members:    [],
            loops:      [],
            sessionButton1:    {},
            sessionButton2:    {}
        };
    }

    // called immediately after object is inserted in the DOM
    // begins update polling interval

    componentDidMount() {
        this.update();
        let self = this;
        let intervalId = setInterval(() => self.update(), UPDATE_PERIOD);
        this.setState({intervalId: intervalId});
    }

    // called immediately before object is removed from the DOM
    // clears update polling interval

    componentWillUnmount() {
        clearInterval(this.state.intervalId);
    }

    // updateSession: query localhost getSession method and update state accordingly

    updateSession() {
        fetch(`http://${pedalDomain}/getsession`)
            .then(fetchRespHandler)
            .then(data => {
                    let sessionId, owner;
                    [sessionId, owner] = data;
                    if (sessionId !== this.state.sessionId || owner !== this.state.owner) {
                        this.setState({sessionId: sessionId, owner: owner});
                        this.updateSessionButtons();
                    }
                })
            .catch(error => flashMessage("error", `server error while updating session: ${error}`));
    }

    // updates values of session control button child components

    updateSessionButtons() {
        let sessionButton1 = this.state.sessionId !== null ? 
            {
                id:             "leavesessionbutton",
                callback:       (emptyarr) => this.leaveSession(),
                text:           "leave session",
                textPrompts:    []
            } : {
                id:             "newsessionbutton",
                callback:       (arr) => this.newSession(arr),
                text:           "new session",
                textPrompts:    ["your nickname"]
            };

        let sessionButton2 = this.state.sessionId !== null ? 
            {
                id:             "endsessionbutton",
                callback:       (emptyarr) => this.endSession(),
                text:           "end session",
                textPrompts:    []
            } : {
                id:             "joinsessionbutton",
                callback:       (arr) => this.joinSession(arr),
                text:           "join session",
                textPrompts:    ["session id", "your nickname"]
            };


        this.setState({
            sessionButton1: sessionButton1,
            sessionButton2: sessionButton2
        });
    } 

    // updateMembers: query localhost getmembers method and update state accordingly

    updateMembers() {
        fetch(`http://${pedalDomain}/getmembers`)
            .then(fetchRespHandler)
            .then(data => {
                this.setState({members: data});
                })
            .catch(error => flashMessage("error", `server error while updating member list: ${error}`));
    }

    // updateLoops: query localhost getmembers method and update state accordingly

    updateLoops() {
        fetch(`http://${pedalDomain}/getloops`)
            .then(fetchRespHandler)
            .then(data => this.setState({loops: data}))
            .catch(error => flashMessage("error", `server error while updating loop list: ${error}`));
    }

    // update: calls all update methods

    update() {
        try {
            this.updateSession();
            this.updateSessionButtons();
            this.updateMembers();
            this.updateLoops();
        } catch (error) {
            flashMessage("error", `server error while updating components: ${error}`);
        }
    }

    newSession(args) {
        if (args.length == 1) {
            let nickname = args[0];
            if (nickname.length > 0) {
                fetch(`http://${pedalDomain}/newsession`, {
                        'method':   "POST",
                        'cache':    "no-cache",
                        'headers':  {
                            'Content-Type': "application/json"
                        },
                        'body':     JSON.stringify({'nickname': nickname})
                    })
                    .then(fetchRespHandler)
                    .then(data => {
                        flashMessage("info", "joined new session");
                        this.update();
                        })
                    .catch(error => {
                        flashMessage("error", {
                            FAILURE_RETURN: "pedal already in session",
                            FULL_RETURN:    "server full"
                        }[error] || `unknown error: ${error}`);

                        });
            } else {
                flashMessage("error", "nickname cannot be empty");
            }
        } else {
            flashMessage("error", "nickname required");
        }
    }

    endSession() {
        fetch(`http://${pedalDomain}/endsession`, {
            'method':   "POST",
            'cache':    "no-cache"
        })
            .then(fetchRespHandler)
            .then(data => {
                flashMessage("info", "ended session");
                this.update();
                })
            .catch(error => {
                flashMessage("error", {
                    FAILURE_RETURN: "unable to end session"
                }[error] || `unknown error: ${error}`);

                });
    

    joinSession(args) {
        if (args.length == 2) {
            let [sessionId, nickname] = args;
            if (nickname.length > 0 && sessionId.length == 4) {
                fetch(`http://${pedalDomain}/joinsession`, {
                        'method':   "POST",
                        'cache':    "no-cache",
                        'headers':  {
                            'Content-Type': "application/json"
                        },
                        'body':     JSON.stringify({'sessionid': sessionId, 'nickname': nickname})
                    })
                    .then(fetchRespHandler)
                    .then(data => {
                        flashMessage("info", "joined session");
                        this.update();
                        })
                    .catch(error => {
                        flashMessage("error", {
                            FAILURE_RETURN:     "session id not found",
                            FULL_RETURN:        "session full",
                            COLLISION_RETURN:   "nickname already in use, please pick another"
                        }[error] || `unknown error: ${error}`);
                        });
            
            } else {
                if (sessionId.length !== 4) {
                    flashMessage("error", "session id must be 4 characters long");
                } else {
                    flashMessage("error", "nickname cannot be empty");
                }
            }
        } else {
            flashMessage("error", "nickname and session id required")
        }
    }

    leaveSession() {
        fetch(`http://${pedalDomain}/leavesession`, {
                'method':   "POST",
                'cache':    "no-cache"
            })
            .then(fetchRespHandler)
            .then(data => {
                flashMessage("info", "left session");
                this.update();
                })
            .catch(error => {
                flashMessage("error", {
                    FAILURE_RETURN: "unable to leave session"
                }[error] || `unknown error: ${error}`);

                });
    }

    render() {
        // if pedal offline, sessionId string will be empty
        const inSession = (this.state.sessionId !== null);

        // flashMessage("info", `session id = ${this.state.sessionId}, in session = ${inSession}`);

        return (
            <div id={inSession ? "onlinecontrolcontainer" : "offlinecontrolcontainer"}>
                <LoopMemberList inSession={inSession} loops={this.state.loops} members={this.state.members} />
                <SessionControl inSession={inSession} sessionId={this.state.sessionId} owner={this.state.owner} button1={this.state.sessionButton1} button2={this.state.sessionButton2} />
            </div>
        );
    }

}

// --------------------------------------------------------------------------
//  LoopMemberList - control pane containing loop and member lists, and loop
//                   playback and deletion control
// --------------------------------------------------------------------------

class LoopMemberList extends React.Component {

    constructor(props) {
        super(props);
        this.state = {
            focused:        "loops",
            playingLoop:    -1
        };
    }

    // switches focus between loops and members menus
    getFocus(elem) {
        this.setState({'focused' : elem});
    }

    toggleLoop(loopIndex) {
        if (loopIndex == this.state.playingLoop) {
            fetch(`http://${pedalDomain}/stopplayback`, {
                    'method':   "POST",
                    'cache':    "no-cache"
                })
                .then(fetchRespHandler)
                .then(data => this.setState({'playingLoop': -1})
                .catch(error => flashMessage("error", `error while ending loop playback: ${error}`));
        } else {
            fetch(`http://${pedalDomain}/startplayback`, {
                    'method':   "POST",
                    'cache':    "no-cache",
                    'headers':  {
                        'Content-Type': "application/json"
                    },
                    'body':     JSON.stringify({'loopindex': loopIndex})
                })
                .then(fetchRespHandler)
                .then(data => this.setState({'playingLoop': loopIndex})
                .catch(error => flashMessage("error", `error while starting loop playback: ${error}`));
        }
    }

    removeLoop(loopIndex) {
        fetch(`http://${pedalDomain}/removeLoop`, {
                'method':   "POST",
                'cache':    "no-cache",
                'headers':  {
                    'Content-Type': "application/json"
                },
                'body':     JSON.stringify({'loopindex': loopIndex})
            })
            .then(fetchRespHandler)
            .catch(error => flashMessage("error", `error while removing loop: ${error}`));
    }

    render() {
        let loopMemberControl = (
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
                {this.props.inSession ? loopMemberControl : loopMemberControl}
                // all lists in this view will have unique entries, so their values can be used as keys
                <div id="loopcontainer" style={{display: this.state.focused === "loops" ? "flex" : "none" }}>
                    loops:
                    <ul>
                        {this.props.loops.map((loopIndex) => <li key={loopIndex} id={loopIndex == this.state.playingLoop ? "loop" : "playingloop"}>{numberToWords.toWords(loopIndex)}<div onClick={() => this.toggleLoop(loopIndex)}>{loopIndex == this.state.playingLoop ? "■" : "▶"}</div><div onClick={() => this.removeLoop(loopIndex)}>✖</div>)}
                    </ul>
                </div>
                <div id="membercontainer" style={{display: this.state.focused === "members" ? "flex" : "none" }}>
                    members:
                    <ul>
                        {this.props.members.map((elem) => <li key={elem}>{elem}</li>)}
                    </ul>
                </div>
            </>
        ); 
    } 
}

// ----------------------------------------------------------------------------------
//  SessionControl - control pane containing session information and control buttons
// ----------------------------------------------------------------------------------

class SessionControl extends React.Component {

    constructor(props) {
        super(props);
        
        this.button1Ref = null;
        this.button2Ref = null;

        // store references to child button elements, which does break encapsulation, but is necessary for maintaining focus/resetting deselected buttons
        this.setButton1Ref = element => {
            this.button1Ref = element;
        }

        this.setButton2Ref = element => {
            this.button2Ref = element;
        }

        this.resetButton1 = () => {
            if (this.button1Ref) {
                this.button1Ref.reset();
            }
        }

        this.resetButton2 = () => {
            if (this.button2Ref) {
                this.button2Ref.reset();
            }
        }
    }

    render() {
        let button1 = this.props.button1;
        let button2 = this.props.button2;

        return (
            <div id="sessioncontrol">
                <div id={this.props.inSession ? "onlinesessioncontrol" : "offlinesessioncontrol"}>
                    {this.props.inSession ? ( <> {this.props.sessionId} <br /> {this.props.owner ? "owner" : "member"} </> ) : "no session"}
                </div>
                <SessionControlButton key={button1['id'] || "loadingbutton1"} ref={this.setButton1Ref} parentClick={this.resetButton2} id={button1['id'] || "loadingbutton1"} className="button" callback={button1['callback']} text={button1['text'] || "loading..."} textPrompts={button1['textPrompts'] || []} disabled={false} />
                <SessionControlButton key={button2['id'] || "loadingbutton2"} ref={this.setButton2Ref} parentClick={this.resetButton1} id={button2['id'] || "loadingbutton2"} className="button" callback={button2['callback']} text={button2['text'] || "loading..."} textPrompts={button2['textPrompts'] || []} disabled={false} />
            </div>
        );
    }

}

// ---------------------------------------------------------------------
//  SessionControlButton - session control object supporting text entry
// ---------------------------------------------------------------------

class SessionControlButton extends React.Component {
    constructor(props) {
        super(props);

        // track where this element is in the text entry process
        // when selected is false, it presents as a pushbutton
        // when clicked, if this button requires text entry, it changes to a textbox
        // the prompt for the text box is supplied in the props.textPrompts array
        // until that array is exhausted, continue prompting for text entries and storing in textEntries
        // when exhausted, call props.callback with the textEntries array
        this.state = {
            selected:       false,
            textEntryIndex: 0,
            textEntries:    [],
            textFieldValue: "",
            innerHTML:      (<div className="sessionButtonDiv" onClick={() => this.advance()}>{this.props.text}</div>)
        };
    };

    // click/enter keypress handler for session control buttons
    advance() {
        if (!this.props.disabled) {
            // focus management parent function from props
            this.props.parentClick();
        
            let textEntryIndex = this.state.textEntryIndex;
            let textEntries = this.state.textEntries;

            if (this.state.selected) {
                if (textEntryIndex < this.props.textPrompts.length) {
                    textEntries.push(this.state.textFieldValue);
                    this.setState({
                        textFieldValue: ""
                    });
                    textEntryIndex++;
                }
            }

            // all text entry requirements satisfied, call parent callback
            if (textEntryIndex >= this.props.textPrompts.length) {
                console.log(textEntries);
                this.props.callback(textEntries);
                this.reset();
            } else {
                let innerHTML = (<> 
                    <input type="text" key={this.props.textPrompts[textEntryIndex]} id={`${this.props.id}textentry`} className="textentry" placeholder={this.props.textPrompts[textEntryIndex]} onChange={event => { this.setState({textFieldValue: event.target.value})}} onKeyDown={event => {if (event.code == "Enter") { this.advance(); }}} autoFocus />
                    <div className="sessionButtonArrow" onClick={() => this.advance()}>
                        →
                    </div>
                </>);
                this.setState({
                    selected:       true,
                    textEntryIndex: textEntryIndex,
                    textEntries:    textEntries,
                    textFieldValue: "",
                    innerHTML:      innerHTML
                });
            }
        }
    }

    reset() {
        this.setState({
            selected:       false,
            textEntryIndex: 0,
            textEntries:    [],
            textFieldValue: "",
            innerHTML:      (<div className="sessionButtonDiv" onClick={() => this.advance()}>{this.props.text}</div>)
        });
    }

    render() {
        
    
        return (
            <div id={this.props.id} className={this.props.disabled ? "sessionButton disabled" : "sessionButton" } >
                {this.state.innerHTML}
            </div>
        );
    }
}
               
// root control panel
var controlpanel = ReactDOM.render(<ControlPanel />, document.getElementById("controlcontainer"));
