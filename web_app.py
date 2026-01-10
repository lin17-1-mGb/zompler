import eventlet
eventlet.monkey_patch() 

from flask import Flask, render_template_string
from flask_socketio import SocketIO
import json, os, time

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Ensure these match the Main Script paths exactly
BASE_DIR = "/home/pi/midifileplayer"
STATE_FILE = os.path.join(BASE_DIR, "monkey_state.json")

IS_BUSY = False

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Monkey MIDI Remote</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <style>
        body { background: #111; color: white; font-family: sans-serif; text-align: center; margin: 0; padding: 0; overflow: hidden; }
        #status-bar { 
            background: #222; color: #0f0; padding: 12px; font-weight: bold; 
            border-bottom: 2px solid #444; display: flex; justify-content: space-between;
        }
        #menu-container { height: 55vh; overflow-y: auto; scroll-behavior: smooth; border-bottom: 1px solid #333; }
        .menu-item { padding: 16px; border-bottom: 1px solid #222; font-size: 1.1em; transition: 0.1s; }
        .controls { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 15px; }
        button { 
            padding: 20px; font-size: 1.2em; background: #333; color: white; 
            border: 1px solid #555; border-radius: 10px; outline: none;
        }
        button:active { background: #007bff; transform: scale(0.98); }
        .sel-btn { background: #0062cc; grid-column: span 2; font-weight: bold; }
        .back-btn { background: #a51d2d; grid-column: span 2; }
        .bar-container { width: 80%; background: #333; height: 15px; margin: 10px auto; border-radius: 10px; overflow: hidden; }
        .bar-fill { height: 100%; background: #007bff; transition: width 0.2s; }
    </style>
</head>
<body>
    <div id="status-bar">
        <span id="mode-text">CONNECTING...</span>
        <span id="batt-text" style="color: #aaa;">--:--</span>
    </div>
    <div id="menu-container"></div>
    <div class="controls">
        <button onclick="sendCmd('up')">UP</button>
        <button onclick="sendCmd('down')">DOWN</button>
        <button class="sel-btn" onclick="sendCmd('select')">SELECT / OK</button>
        <button class="back-btn" onclick="sendCmd('back')">BACK / MENU</button>
    </div>

    <script>
        var socket = io();
        function sendCmd(name) { socket.emit('control', {btn: name}); }

        socket.on('state_update', function(data) {
            if(!data) return;
            document.getElementById('batt-text').innerText = data.battery || "0:00";
            const modeEl = document.getElementById('mode-text');
            const menuContainer = document.getElementById('menu-container');
            
            // 1. Header/Mode Logic
            if (data.msg) {
                modeEl.innerText = data.msg;
                modeEl.style.color = "#ff4444";
            } else {
                modeEl.innerText = (data.mode || "MAIN").toUpperCase();
                modeEl.style.color = data.is_eco ? "#fbff00" : "#00ff00";
            }

            // 2. Specialized Screen Logic
            let html = '';
            
            if (data.mode === "VOLUME") {
                html = `
                    <div style="padding: 40px;">
                        <h2 style="color: #aaa;">MASTER VOLUME</h2>
                        <div style="font-size: 5em; font-weight: bold; color: #00ff00;">${data.volume}%</div>
                        <div class="bar-container">
                            <div class="bar-fill" style="width: ${data.volume}%; background: #00ff00;"></div>
                        </div>
                    </div>`;
            } 
            else if (data.mode === "METRONOME") {
                let statusColor = data.metronome_on ? "#00ff00" : "#ff4444";
                let sel = parseInt(data.index);
                html = `
                    <div style="padding: 20px;">
                        <h2 style="color: #aaa;">METRONOME</h2>
                        <div style="padding: 10px; border-radius: 10px; ${sel === 0 ? 'border: 2px solid yellow; background: #222;' : ''}">
                            <div style="font-size: 1.5em; color: ${statusColor}; font-weight: bold;">
                                ${data.metronome_on ? "● ACTIVE" : "○ OFF"}
                            </div>
                        </div>
                        <div style="margin-top: 15px; padding: 10px; border-radius: 10px; ${sel === 1 ? 'border: 2px solid #007bff; background: #222;' : ''}">
                            <div style="font-size: 0.8em; color: #888;">TEMPO</div>
                            <div style="font-size: 3em; font-weight: bold;">${data.bpm} <span style="font-size: 0.4em;">BPM</span></div>
                        </div>
                        <div style="margin-top: 15px; padding: 10px; border-radius: 10px; ${sel === 2 ? 'border: 2px solid #007bff; background: #222;' : ''}">
                            <div style="font-size: 0.8em; color: #888;">CLICK VOLUME</div>
                            <div style="font-size: 2em; font-weight: bold; color: #007bff;">${data.metro_vol}</div>
                            <div class="bar-container" style="width: 60%;">
                                <div class="bar-fill" style="width: ${(data.metro_vol/127)*100}%"></div>
                            </div>
                        </div>
                    </div>`;
            }
            else {
                // Default Menu List Logic
                (data.files || []).forEach((item, i) => {
                    let isSel = (parseInt(i) === parseInt(data.index));
                    let style = isSel ? 'background: #007bff; color: white; font-weight: bold; border-left: 8px solid yellow;' : 'color: #888;';
                    html += `<div id="item-${i}" class="menu-item" style="${style}">${item}</div>`;
                });
            }

            menuContainer.innerHTML = html;

            if (data.mode !== "VOLUME" && data.mode !== "METRONOME") {
                const active = document.getElementById(`item-${data.index}`);
                if (active) active.scrollIntoView({ block: 'center', behavior: 'smooth' });
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

def force_emit():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                socketio.emit('state_update', data)
    except:
        pass

@socketio.on('control')
def handle_control(data):
    global IS_BUSY
    btn = data.get('btn')
    cmd_file = os.path.join(BASE_DIR, f"cmd_{btn}")
    try:
        IS_BUSY = True 
        with open(cmd_file, "w") as f:
            f.write("1")
        socketio.sleep(0.15) 
        force_emit()
    finally:
        IS_BUSY = False

def broadcast_loop():
    last_mtime = 0
    while True:
        if not IS_BUSY:
            try:
                if os.path.exists(STATE_FILE):
                    mtime = os.path.getmtime(STATE_FILE)
                    if mtime != last_mtime:
                        force_emit()
                        last_mtime = mtime
            except:
                pass
        socketio.sleep(0.2)

if __name__ == '__main__':
    if not os.path.exists(BASE_DIR):
        os.makedirs(BASE_DIR)
    socketio.start_background_task(broadcast_loop)
    socketio.run(app, host='0.0.0.0', port=5000)