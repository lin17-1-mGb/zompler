#!/usr/bin/env python3
import sys, os, time, threading, smbus, datetime, json
import mido 

# --- 1. BOOT DELAY ---
time.sleep(0.5)

# --- 2. HARDCODED PATHS ---
BASE_DIR = "/home/pi/midifileplayer"
soundfont_folder = "/home/pi/sf2"
midi_file_folder = "/home/pi/midifiles"
STATE_FILE = os.path.join(BASE_DIR, "monkey_state.json")
mixer_file = os.path.join(BASE_DIR, "mixer_settings.json")

# Ensure folders exist
for d in [soundfont_folder, midi_file_folder, BASE_DIR]:
    if not os.path.exists(d): os.makedirs(d)

# --- 3. CONFIGURATION & STATE ---
LED_NAME = "ACT"  
SHUTTING_DOWN = False  
LOW_POWER_MODE = False
MESSAGE = ""
msg_start_time = 0

# Navigation & Menu State
operation_mode = "main screen"
selectedindex = 0
files = []
pathes = []
MAIN_MENU = ["SOUND FONT", "MIDI FILE", "MIDI KEYBOARD", "MIXER", "METRONOME", "VOLUME", "POWER", "RECORD", "SHUTDOWN"]

# Audio & Volume State
# Changed 0.5 to 70 (0-100 scale) to match display and scroll logic
volume_level = 70 
channel_volumes = {i: 100 for i in range(16)}

# Metronome State
metronome_on = False
metro_adjusting = False
bpm = 120
metro_vol = 80 # Default MIDI volume (0-127)

# Mixer State
mixer_selected_ch = 0
mixer_adjusting = False

# Rename State
rename_string = ""
rename_char_idx = 0
rename_chars = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-OK"

# FluidSynth & MIDI
midi_manager = None 
sf2_mapping_cache = {}
sfid = None # Track loaded SoundFont ID
selected_file_path = ""
loaded_sf2_path = ""

# --- MIXER SAVE/LOAD LOGIC ---
def save_mixer():
    try:
        with open(mixer_file, 'w') as f:
            json.dump(channel_volumes, f)
    except: pass

def load_mixer():
    global channel_volumes
    if os.path.exists(mixer_file):
        try:
            with open(mixer_file, 'r') as f:
                data = json.load(f)
                channel_volumes = {int(k): v for k, v in data.items()}
        except: pass

# ---------------------- RECORDING ENGINE ----------------------
class MidiRecorder:
    def __init__(self):
        self.recording = False
        self.mid = None
        self.track = None
        self.start_time = 0
        self.last_event_time = 0

    def start(self):
        self.mid = mido.MidiFile()
        self.track = mido.MidiTrack()
        self.mid.tracks.append(self.track)
        self.recording = True
        self.start_time = time.time()
        self.last_event_time = self.start_time

    def stop(self, filename=None):
        if not self.recording: return
        self.recording = False
        if filename:
            # Properly close MIDI track
            self.track.append(mido.MetaMessage('end_of_track', time=0))
            self.mid.save(filename)

    def add_event(self, msg):
        if self.recording:
            now = time.time()
            # Calculate delta time in ticks (assuming 480 TPB and 120 BPM)
            delta = int(mido.second2tick(now - self.last_event_time, self.mid.ticks_per_beat, 500000))
            msg.time = delta
            self.track.append(msg)
            self.last_event_time = now

recorder = MidiRecorder()

# ---------------------- METRONOME ENGINE ----------------------
metronome_on = False
bpm = 120
metro_vol = 80 
metro_adjusting = False

def metronome_worker():
    while True:
        if metronome_on and fs:
            try:
                fs.noteon(9, 76, 110) 
                time.sleep(0.05)
                fs.noteoff(9, 76)
                time.sleep(max(0.01, (60.0 / bpm) - 0.05))
            except: time.sleep(0.1)
        else:
            time.sleep(0.2)

threading.Thread(target=metronome_worker, daemon=True).start()

# ---------------------- WAVESHARE UPS (C) ----------------------
class UPS_C:
    def __init__(self, addr=0x43):
        self.bus = None; self.addr = addr; self.readings = []
        try: self.bus = smbus.SMBus(1)
        except: pass
    def get_voltage(self):
        if not self.bus: return 0.0
        try:
            read = self.bus.read_word_data(self.addr, 0x02)
            swapped = ((read << 8) & 0xFF00) | ((read >> 8) & 0x00FF)
            v = (swapped >> 3) * 0.004
            self.readings.append(v)
            if len(self.readings) > 20: self.readings.pop(0)
            return sorted(self.readings)[len(self.readings)//2]
        except: return 0.0
    def get_time_left(self):
        v = self.get_voltage()
        if v < 3.0: return "0:00"
        p = max(0, min(1, (v - 3.4) / (4.15 - 3.4)))
        total_minutes = p * (450 if LOW_POWER_MODE else 240)
        return f"{int(total_minutes // 60)}:{int(total_minutes % 60):02d}"

ups = UPS_C()

# ---------------------- UI MENU CONFIG ----------------------
MAIN_MENU = ["MIDI KEYBOARD", "SOUND FONT", "MIDI FILE", "MIXER", "RECORD", "METRONOME", "VOLUME", "POWER", "SHUTDOWN"]
files = MAIN_MENU.copy()
pathes = MAIN_MENU.copy()
selectedindex = 0
operation_mode = "main screen"
selected_file_path = ""
rename_string = ""
rename_chars = [" ", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z", "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "_", "-", "OK"]
rename_char_idx = 0
mixer_selected_ch = 0
mixer_adjusting = False
channel_presets = {}

# ---------------------- HARDWARE INITIALIZATION ----------------------
fs = None; sfid = None; loaded_sf2_path = None; disp = None
img = draw = font = font_tiny = None
_last_display_time = 0.0
soundfont_paths, soundfont_names = [], []; midi_paths, midi_names = [], []

def init_buttons():
    global button_up, button_down, button_select, button_back
    from gpiozero import Button
    button_up, button_down = Button(16), Button(24)
    button_select, button_back = Button(5), Button(6)

def init_display():
    global disp, img, draw, font, font_tiny
    try:
        import st7789 as st_lib
        from PIL import Image, ImageDraw, ImageFont
        disp = st_lib.ST7789(width=240, height=240, rotation=90, port=0, cs=st_lib.BG_SPI_CS_FRONT, dc=9, backlight=13, spi_speed_hz=40_000_000)
        disp.begin()
        img = Image.new("RGB", (240, 240), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        try: 
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        except: 
            font = ImageFont.load_default(); font_tiny = ImageFont.load_default()
    except: pass

def init_fluidsynth_lazy():
    global fs
    if fs is None:
        try:
            import fluidsynth as fs_lib
            fs = fs_lib.Synth()
            
            # --- VOLUME CORRECTION ---
            # Converts 0-100 scale back to 0.0-1.0 for FluidSynth
            fs.setting('synth.gain', volume_level / 100.0)
            
            # Performance Settings
            fs.setting('player.timing-source', 'sample')
            fs.setting('synth.cpu-cores', 4) # Take advantage of Pi's cores
            fs.setting('audio.alsa.device', 'default')
            
            # Start the driver
            # Note: driver name can be "alsa", "pulse", or "jack" depending on your OS setup
            fs.start(driver="alsa")
            
            # Initialize Metronome Volume (Internal Channel 9 / MIDI Ch 10)
            # This ensures the metronome starts at your saved metro_vol level
            fs.cc(9, 7, metro_vol)
            
        except Exception as e: 
            print(f"Synth Init Fail: {e}")
# ---------------------- POWER MANAGEMENT ----------------------
def toggle_power_mode():
    global LOW_POWER_MODE, MESSAGE, msg_start_time
    LOW_POWER_MODE = not LOW_POWER_MODE
    if LOW_POWER_MODE:
        os.system("sudo tvservice -o > /dev/null 2>&1")
        os.system("echo powersave | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor > /dev/null")
        os.system(f"echo none | sudo tee /sys/class/leds/{LED_NAME}/trigger > /dev/null")
        if fs: fs.setting('synth.polyphony', 48)
        MESSAGE = "Lean: ON (ECO)"
    else:
        os.system("sudo tvservice -p > /dev/null 2>&1")
        os.system("echo ondemand | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor > /dev/null")
        os.system(f"echo mmc0 | sudo tee /sys/class/leds/{LED_NAME}/trigger > /dev/null")
        if fs: fs.setting('synth.polyphony', 96)
        MESSAGE = "Lean: OFF (MAX)"
    msg_start_time = time.time()

# ---------------------- MIDI ENGINE LOGIC ----------------------
def get_internal_channel(monkey_ch): 
    return 9 if monkey_ch == 0 else monkey_ch - 1

def build_sf2_preset_map(sf2_path):
    global sf2_mapping_cache
    if not sf2_path or not os.path.exists(sf2_path):
        return {}, False
    try:
        from sf2utils.sf2parse import Sf2File
        with open(sf2_path, 'rb') as f:
            sf2 = Sf2File(f)
            mapping = {}
            for p in sf2.presets:
                b = getattr(p, 'bank', getattr(getattr(p, 'header', object()), 'bank', 0))
                pr = getattr(p, 'preset', getattr(getattr(p, 'header', object()), 'preset', 0))
                mapping[(b, pr)] = p.name
            sf2_mapping_cache = mapping
            return mapping, True
    except:
        return {}, False

def select_first_presets_for_monkey():
    global channel_presets, sfid, fs, loaded_sf2_path, sf2_mapping_cache
    if sfid is None or fs is None or not loaded_sf2_path: return
    
    # Force a fresh scan if cache is empty
    mapping, ok = build_sf2_preset_map(loaded_sf2_path)
        
    channel_presets.clear() 
    if ok and mapping:
        # Find all available banks
        available_banks = sorted(list(set(bank for bank, prog in mapping.keys())))
        # Use first available bank if 0 isn't there
        main_bank = 0 if 0 in available_banks else (available_banks[0] if available_banks else 0)
        
        # --- DRUMS (Monkey 0 -> MIDI Ch 10) ---
        drum_bank = 128 if 128 in available_banks else (127 if 127 in available_banks else main_bank)
        fs.program_select(9, sfid, drum_bank, 0)
        channel_presets[9] = mapping.get((drum_bank, 0), "Drums")

        # --- INSTRUMENTS (Monkey 1-9 -> MIDI Ch 1-9) ---
        # Get all presets in our main bank
        bank_presets = sorted([p for b, p in mapping.keys() if b == main_bank])
        
        for m_ch in range(1, 10):
            f_ch = m_ch - 1 # Internal index
            # Pick the next available preset in the bank
            prog = bank_presets[m_ch-1] if len(bank_presets) >= m_ch else 0
            fs.program_select(f_ch, sfid, main_bank, prog)
            channel_presets[f_ch] = mapping.get((main_bank, prog), f"Patch {prog}")
    else:
        # Emergency Fallback if sf2utils failed
        for i in range(16): channel_presets[i] = "Generic Patch"
    
    update_web_state()

class SafeMidiIn:
    def __init__(self):
        import rtmidi as rt_lib
        self.midiin = rt_lib.MidiIn(); self.port_name = None; self.callback = None
    def set_callback(self, cb):
        self.callback = cb
        if self.midiin.is_port_open(): self.midiin.set_callback(self._cb)
    def _cb(self, msg, ts):
        if self.callback: self.callback(msg, ts)
    def open_port_by_name_async(self, name):
        def t():
            ports = self.midiin.get_ports()
            if name in ports:
                if self.midiin.is_port_open(): self.midiin.close_port()
                self.midiin.open_port(ports.index(name))
                self.midiin.set_callback(self._cb); self.port_name = name
                global MESSAGE, msg_start_time; MESSAGE = "MIDI Connected"; msg_start_time = time.time()
        threading.Thread(target=t, daemon=True).start()
    def list_ports(self): return self.midiin.get_ports()

def midi_callback(message_data, timestamp):
    global sf2_mapping_cache, sfid, channel_presets, fs, loaded_sf2_path
    message, _ = message_data
    status = message[0] & 0xF0
    ch = message[0] & 0x0F
    n1 = message[1] if len(message) > 1 else 0
    n2 = message[2] if len(message) > 2 else 0

    if recorder.recording:
        try:
            mido_msg = mido.Message.from_bytes(bytes(message))
            recorder.add_event(mido_msg)
        except: pass

    if not fs: return

    if status == 0x90 and n2 > 0: fs.noteon(ch, n1, n2)
    elif status == 0x90 or status == 0x80: fs.noteoff(ch, n1)
    elif status == 0xB0: 
        fs.cc(ch, n1, n2)
        if n1 == 7: channel_volumes[ch] = n2 # Sync volume if keyboard sends CC7
    elif status == 0xE0: fs.pitch_bend(ch, (n2 << 7) + n1 - 8192)
    elif status == 0xC0:
        bank = 128 if ch == 9 else 0
        if sfid is not None:
            fs.program_select(ch, sfid, bank, n1)
            name = sf2_mapping_cache.get((bank, n1), f"Patch {n1}")
            channel_presets[ch] = name
            update_web_state()

def scan_soundfonts():
    global soundfont_paths, soundfont_names
    p, l = [], []
    if os.path.isdir(soundfont_folder):
        for f in sorted(os.listdir(soundfont_folder)):
            if f.endswith('.sf2'): p.append(os.path.join(soundfont_folder, f)); l.append(f.replace('.sf2', ''))
    soundfont_paths, soundfont_names = p, l

def scan_midifiles():
    global midi_paths, midi_names
    p, l = [], []
    if os.path.isdir(midi_file_folder):
        for f in sorted(os.listdir(midi_file_folder)):
            if f.endswith('.mid'): p.append(os.path.join(midi_file_folder, f)); l.append(f.replace('.mid', ''))
    midi_paths, midi_names = p, l

# ---------------------- BUTTON HANDLERS ----------------------
def handle_back():
    global operation_mode, files, pathes, selectedindex, rename_string, mixer_adjusting, metro_adjusting
    if operation_mode == "MIXER":
        if mixer_adjusting: mixer_adjusting = False; return
        else: save_mixer() 
    if operation_mode == "METRONOME" and metro_adjusting: metro_adjusting = False; return
    
    if operation_mode == "RENAME":
        if len(rename_string) > 0: 
            rename_string = rename_string[:-1]
        else: 
            operation_mode = "FILE ACTION"
            files = ["PLAY", "STOP", "RENAME", "DELETE", "BACK"]
            selectedindex = 2 # Highlight RENAME so you know where you came from
    elif operation_mode == "FILE ACTION":
        operation_mode = "MIDI FILE"
        scan_midifiles()
        files, pathes = midi_names.copy(), midi_paths.copy()
        selectedindex = 0
    else:
        operation_mode = "main screen"
        files = MAIN_MENU.copy()
        selectedindex = 0
    update_web_state()
    
def handle_scroll(direction):
    global selectedindex, operation_mode, volume_level, bpm, rename_char_idx
    global mixer_selected_ch, mixer_adjusting, metro_vol, metro_adjusting

    # --- 1. NAVIGATION MODES (Main Menu & File Lists) ---
    if operation_mode in ["main screen", "SOUND FONT", "MIDI FILE", "MIDI KEYBOARD", "FILE ACTION"]:
        if direction == "UP":
            selectedindex = (selectedindex - 1) % len(files)
        else:
            selectedindex = (selectedindex + 1) % len(files)

    # --- 2. VOLUME MODE (Master Gain) ---
    elif operation_mode == "VOLUME":
        if direction == "UP":
            volume_level = min(100, volume_level + 5)
        else:
            volume_level = max(0, volume_level - 5)
        if fs:
            fs.setting('synth.gain', volume_level / 100.0)

    # --- 3. METRONOME MODE (Toggle, BPM, and Click Vol) ---
    elif operation_mode == "METRONOME":
        if not metro_adjusting:
            # Scroll through the 3 rows: [0: Status, 1: BPM, 2: Vol]
            if direction == "UP":
                selectedindex = (selectedindex - 1) % 3
            else:
                selectedindex = (selectedindex + 1) % 3
        else:
            # Adjust the actual values of the selected row
            if selectedindex == 1: # BPM Row
                bpm = min(250, bpm + 2) if direction == "UP" else max(40, bpm - 2)
            elif selectedindex == 2: # Metronome Volume Row
                metro_vol = min(127, metro_vol + 5) if direction == "UP" else max(0, metro_vol - 5)
                if fs:
                    fs.cc(9, 7, metro_vol)

    # --- 4. MIXER MODE (Channel Volumes) ---
    elif operation_mode == "MIXER":
        if not mixer_adjusting:
            # Choose which of the 10 channels to look at
            mixer_selected_ch = (mixer_selected_ch + (1 if direction == "DOWN" else -1)) % 10
        else:
            # Adjust the volume of the chosen channel
            f_ch = get_internal_channel(mixer_selected_ch)
            vol = channel_volumes.get(f_ch, 100)
            vol = min(127, vol + 5) if direction == "UP" else max(0, vol - 5)
            channel_volumes[f_ch] = vol
            if fs:
                fs.cc(f_ch, 7, vol)

    # --- 5. RENAME MODE (Letter Picker) ---
    elif operation_mode == "RENAME":
        if direction == "UP":
            rename_char_idx = (rename_char_idx - 1) % len(rename_chars)
        else:
            rename_char_idx = (rename_char_idx + 1) % len(rename_chars)

    # Always sync to the web app/phone after a scroll
    update_web_state()
    
def handle_select():
    global operation_mode, files, pathes, selectedindex, MESSAGE, msg_start_time
    global fs, sfid, SHUTTING_DOWN, rename_string, rename_char_idx
    global mixer_adjusting, selected_file_path, loaded_sf2_path, metronome_on, metro_adjusting
    global volume_level, bpm, metro_vol

    # --- 1. SPECIAL MODES (Mixer & Metronome) ---
    if operation_mode == "MIXER": 
        mixer_adjusting = not mixer_adjusting
        update_web_state()
        return
        
    if operation_mode == "METRONOME":
        if selectedindex == 0: 
            metronome_on = not metronome_on
            MESSAGE = "Metro: " + ("ON" if metronome_on else "OFF")
        else: 
            # Toggles between "moving the cursor" and "changing the value"
            metro_adjusting = not metro_adjusting
            MESSAGE = "ADJUSTING..." if metro_adjusting else "CONFIRMED"
        
        msg_start_time = time.time()
        update_web_state()
        return

    # --- 2. VOLUME MODE ---
    elif operation_mode == "VOLUME":
        operation_mode = "main screen"
        files = MAIN_MENU.copy()
        selectedindex = 0 # Return to top or use a specific index
        MESSAGE = f"Master: {int(volume_level)}%"
        msg_start_time = time.time()
        update_web_state()
        return
        
    # --- 3. VALIDATION ---
    if not files and operation_mode != "RENAME": return
    if operation_mode != "RENAME": sel = files[selectedindex]
    
    # --- 4. MAIN MENU LOGIC ---
    if operation_mode == "main screen":
        # Handle simple mode switches first
        if sel in ["MIXER", "METRONOME", "VOLUME"]:
            operation_mode = sel
            selectedindex = 0
            return
        
        if sel == "POWER": toggle_power_mode(); return

        if sel == "RECORD":
            if not recorder.recording:
                recorder.start(); MESSAGE = "Recording..."
            else:
                ts = datetime.datetime.now().strftime("%H%M%S")
                path = os.path.join(midi_file_folder, f"rec_{ts}.mid")
                recorder.stop(path); MESSAGE = "Saved Rec"; scan_midifiles()
            msg_start_time = time.time(); update_web_state(); return
        
        if sel == "SHUTDOWN":
            SHUTTING_DOWN = True
            draw.rectangle((0, 0, 240, 240), fill=(0, 0, 0))
            draw.text((45, 100), "SYSTEM HALT", font=font, fill=(255, 0, 0))
            disp.display(img)
            if fs: fs.delete()
            time.sleep(1.0); os.system("sudo /sbin/poweroff"); return

        # Load Sub-Menus
        operation_mode = sel
        if sel == "SOUND FONT": 
            scan_soundfonts()
            files, pathes = soundfont_names.copy(), soundfont_paths.copy()
        elif sel == "MIDI FILE": 
            scan_midifiles()
            files, pathes = midi_names.copy(), midi_paths.copy()
        elif sel == "MIDI KEYBOARD": 
            files = pathes = midi_manager.list_ports()
        selectedindex = 0

    # --- 5. MIDI FILE & FILE ACTIONS ---
    elif operation_mode == "MIDI FILE":
        selected_file_path = pathes[selectedindex]
        operation_mode = "FILE ACTION"
        files = ["PLAY", "STOP", "RENAME", "DELETE", "BACK"]
        selectedindex = 0

    elif operation_mode == "FILE ACTION":
        if sel == "PLAY":
            if not sfid: 
                MESSAGE = "LOAD SF2 FIRST"
            else:
                import subprocess
                try:
                    # 1. Kill old processes
                    subprocess.run(["pkill", "-9", "aplaymidi"], capture_output=True)
                    
                    # 2. Reset synth
                    if fs:
                        for i in range(16): 
                            fs.all_sounds_off(i)
                    
                    # 3. Robust Port Discovery
                    target_port = None
                    try:
                        port_data = subprocess.check_output(['aplaymidi', '-l']).decode()
                        for line in port_data.split('\n'):
                            if "FLUID Synth" in line:
                                # This splits the line and takes the first part (e.g., '128:0')
                                target_port = line.strip().split(' ')[0]
                                break
                    except:
                        target_port = "128:0" # Fallback if -l fails

                    if not target_port:
                        target_port = "128:0"

                    # 4. Start playback
                    # Added 'str()' and check if file exists
                    if os.path.exists(selected_file_path):
                        subprocess.Popen(["aplaymidi", "--port", target_port, str(selected_file_path)])
                        MESSAGE = f"Playing"
                    else:
                        MESSAGE = "File Not Found"
                    
                except Exception as e:
                    print(f"CRITICAL PLAY ERROR: {e}") # This shows in your terminal/logs
                    MESSAGE = "Play Error"

        elif sel == "STOP":
            import subprocess
            subprocess.run(["pkill", "-9", "aplaymidi"], capture_output=True)
            if fs:
                for i in range(16): 
                    fs.all_sounds_off(i)
                select_first_presets_for_monkey()
            MESSAGE = "Stopped"

        elif sel == "RENAME":
            operation_mode = "RENAME"
            rename_string = os.path.basename(selected_file_path).replace(".mid", "")
            rename_char_idx = 0

        elif sel == "DELETE":
            try:
                if os.path.exists(selected_file_path): 
                    os.remove(selected_file_path)
                MESSAGE = "Deleted"
                scan_midifiles()
                files, pathes = midi_names.copy(), midi_paths.copy()
                operation_mode = "MIDI FILE"
                selectedindex = 0
            except:
                MESSAGE = "Delete Error"

        elif sel == "BACK":
            operation_mode = "MIDI FILE"
            selectedindex = 0

    # --- 6. RENAME & SOUNDFONT LOADING ---
    elif operation_mode == "RENAME":
        char = rename_chars[rename_char_idx]
        if char == "OK":
            new_path = os.path.join(midi_file_folder, rename_string.strip() + ".mid")
            try: os.rename(selected_file_path, new_path); MESSAGE = "Renamed"
            except: MESSAGE = "Error"
            operation_mode = "MIDI FILE"
            scan_midifiles(); files, pathes = midi_names.copy(), midi_paths.copy()
            selectedindex = 0
        else:
            rename_string += char

    elif operation_mode == "SOUND FONT":
        loaded_sf2_path = pathes[selectedindex]
        MESSAGE = "Loading..."
        update_display() # Show "Loading" immediately
        init_fluidsynth_lazy()
        sfid = fs.sfload(loaded_sf2_path, True)
        select_first_presets_for_monkey()
        MESSAGE = "SF2 LOADED"
        operation_mode = "main screen"; files = MAIN_MENU.copy(); selectedindex = 0

    elif operation_mode == "MIDI KEYBOARD":
        midi_manager.open_port_by_name_async(pathes[selectedindex])
        operation_mode = "main screen"; files = MAIN_MENU.copy(); selectedindex = 0

    msg_start_time = time.time()
    update_web_state()
# ---------------------- WEB CONNECTIVITY ----------------------
def update_web_state():
    global operation_mode, selectedindex, rename_string, rename_char_idx, files
    global volume_level, bpm, metronome_on, MESSAGE, msg_start_time
    global metro_vol, metro_adjusting, mixer_selected_ch, mixer_adjusting # Added for safety

    try:
        display_list = []
        current_idx = selectedindex
        
        # 1. Determine the 'List View' content
        if operation_mode == "RENAME":
            display_list = [f"Building: {rename_string}", f"Char: {rename_chars[rename_char_idx]}"]
            current_idx = 1
        elif operation_mode == "MIXER":
            current_idx = mixer_selected_ch
            for m_ch in range(10):
                f_ch = get_internal_channel(m_ch)
                name = channel_presets.get(f_ch, f"CH {f_ch}")
                vol = channel_volumes.get(f_ch, 100)
                display_list.append(f"{m_ch}: {name[:10]} ({vol}%)")
        elif operation_mode in ["VOLUME", "METRONOME"]:
            # We clear the list so the web app shows its specialized UI overlays
            display_list = []
        else:
            display_list = files if files else ["No Files"]

        # 2. Package everything for the Web App
        state_data = {
            "mode": str(operation_mode),
            "index": int(current_idx), # Use the smart index we calculated
            "files": display_list,     # Use the smart list we built
            "msg": MESSAGE if (time.time() - msg_start_time < 2.0) else "",
            "battery": ups.get_time_left(),
            "is_eco": bool(LOW_POWER_MODE),
            "rename_tmp": str(rename_string),
            "volume": int(volume_level),
            "bpm": int(bpm),
            "metronome_on": bool(metronome_on),
            "metro_vol": int(metro_vol),
            "mixer_idx": int(mixer_selected_ch),
            "is_adjusting": bool(metro_adjusting or mixer_adjusting)
        }

        # 3. Atomic Write (Anti-Corruption)
        target = os.path.join(BASE_DIR, "monkey_state.json")
        temp_file = target + ".tmp"
        with open(temp_file, "w") as f: 
            json.dump(state_data, f)
        os.replace(temp_file, target) # Instant swap
        
    except Exception as e:
        # print(f"Web Update Error: {e}") 
        pass

# ---------------------- DISPLAY ENGINE ----------------------
def update_display():
    global _last_display_time
    if SHUTTING_DOWN or draw is None: return 
    
    now = time.time()
    # Throttle display updates to save CPU
    if now - _last_display_time < (0.15 if LOW_POWER_MODE else 0.06): return
    _last_display_time = now
    
    # Yellow accent for ECO mode, White for MAX
    accent = (255, 255, 0) if LOW_POWER_MODE else (255, 255, 255)
    
    # 1. Clear Background and Draw Header
    draw.rectangle((0, 0, 240, 240), fill=(0, 0, 0))
    draw.rectangle((0, 0, 240, 26), fill=(30, 30, 30))
    draw.text((10, 4), f"BAT: {ups.get_time_left()}", font=font_tiny, fill=accent)
    
    # 2. Draw Mode Title
    draw.rectangle((0, 26, 240, 56), fill=(50, 50, 50))
    draw.text((10, 31), operation_mode.upper(), font=font, fill=accent)

    # --- MODE: VOLUME ---
    if operation_mode == "VOLUME":
        draw.text((30, 90), "MASTER GAIN", font=font, fill=accent)
        draw.rectangle((20, 120, 220, 150), outline=accent, width=2)
        # Standardized for 0-100 scale: 196 pixels wide max
        bar_width = int(1.96 * volume_level)
        draw.rectangle((22, 122, 22 + bar_width, 148), fill=(0, 255, 0))
        draw.text((100, 160), f"{int(volume_level)}%", font=font, fill=accent)

    # --- MODE: METRONOME ---
    elif operation_mode == "METRONOME":
        metro_lines = [
            f"STATUS: {'ACTIVE' if metronome_on else 'OFF'}",
            f"BPM: {bpm}",
            f"CLICK VOL: {metro_vol}"
        ]
        for i, text in enumerate(metro_lines):
            y = 75 + (i * 35)
            is_selected = (i == selectedindex)
            
            # Draw a green box if we are actually turning the knob to change the value
            if is_selected:
                box_color = (0, 255, 0) if metro_adjusting else accent
                draw.rectangle([10, y-4, 230, y+28], fill=box_color)
                draw.text((20, y), text, font=font, fill=(0, 0, 0))
            else:
                draw.text((20, y), text, font=font, fill=accent)

    # --- MODE: MIXER ---
    elif operation_mode == "MIXER":
        for i in range(10):
            y = 60 + (i * 18)
            f_ch = get_internal_channel(i)
            color = accent if i == mixer_selected_ch else (200, 200, 200)
            
            # Highlight current channel; Green outline if adjusting
            if i == mixer_selected_ch:
                if mixer_adjusting:
                    draw.rectangle((5, y, 235, y+16), outline=(0, 255, 0), width=1)
                else:
                    draw.rectangle((5, y, 235, y+16), outline=accent, width=1)
            
            name = channel_presets.get(f_ch, f"CH {f_ch}")
            draw.text((10, y), f"{i}:{name[:10]}", font=font_tiny, fill=color)
            vol = channel_volumes.get(f_ch, 100)
            # Volume bar for channel
            draw.rectangle((150, y+4, 150 + int(vol/1.6), y+12), fill=color)

    # --- MODE: RENAME ---
    elif operation_mode == "RENAME":
        draw.text((10, 80), "Rename to:", font=font_tiny, fill=accent)
        draw.text((10, 105), rename_string + "_", font=font, fill=(0, 255, 0))
        
        # Character Picker Box
        draw.rectangle((100, 150, 140, 190), outline=accent, width=2)
        draw.text((112, 158), rename_chars[rename_char_idx], font=font, fill=accent)

    # --- MODE: DEFAULT LIST (Main Menu, Files, etc.) ---
    else:
        view = 5
        start = max(0, min(selectedindex - 2, len(files) - view))
        for i, line in enumerate(files[start:start+view], start=start):
            y = 62 + (i - start) * 28
            if i == selectedindex:
                draw.rectangle([10, y, 230, y+26], fill=accent)
                draw.text((15, y+2), line[:22], font=font, fill=(0, 0, 0))
            else:
                draw.text((15, y+2), line[:22], font=font, fill=accent)

    # 3. Draw Toast Notifications (Overlay)
    if MESSAGE and now - msg_start_time < 2.0:
        draw.rectangle((20, 90, 220, 140), fill=(200, 0, 0), outline=(255, 255, 255), width=2)
        draw.text((35, 105), MESSAGE, font=font_tiny, fill=(255, 255, 255))

    # 4. Push to ST7789
    disp.display(img)

# ---------------------- MAIN BOOT ----------------------
def background_init():
    global midi_manager
    try:
        midi_manager = SafeMidiIn(); midi_manager.set_callback(midi_callback)
        init_buttons(); init_display(); scan_soundfonts(); scan_midifiles()
        
        # CHANGE THESE: Use lambda to pass the direction to handle_scroll
        button_up.when_pressed = lambda: handle_scroll("UP")
        button_down.when_pressed = lambda: handle_scroll("DOWN")
        
        button_select.when_pressed = handle_select
        button_back.when_pressed = handle_back
        update_web_state()
    except: pass

def main():
    threading.Thread(target=background_init, daemon=True).start()
    web_counter = 0
    while True:
        if not SHUTTING_DOWN:
            update_display()
            
            # Web Command Check
            cmd_found = False
            for btn in ["up", "down", "select", "back"]:
                path = os.path.join(BASE_DIR, f"cmd_{btn}")
                if os.path.exists(path):
                    try:
                        if btn == "up": 
                            handle_scroll("UP") # Changed from handle_up()
                        elif btn == "down": 
                            handle_scroll("DOWN") # Changed from handle_down()
                        elif btn == "select": 
                            handle_select()
                        elif btn == "back": 
                            handle_back()
                        cmd_found = True
                    finally:
                        try: os.remove(path)
                        except: pass
            
            web_counter += 1
            # If a command was processed or 0.5s has passed (10 * 0.05)
            if cmd_found or web_counter >= 10:
                update_web_state()
                web_counter = 0
                
        time.sleep(0.1)

if __name__ == '__main__':
    load_mixer()

    main()
