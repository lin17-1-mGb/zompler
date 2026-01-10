# Zompler
A raspberry pi rompler script (especially for broken Pimoroni Pirate Audio hat screen)
🐒 Monkey MIDI Player

# Video demo
https://youtu.be/eCKjwiwQem0

A high-performance Raspberry Pi MIDI player with an OLED interface and a real-time mobile web remote.
✨ Features

    OLED Interface: Navigate SoundFonts and MIDI files directly on the device.

    Mobile Remote: Full control via a web browser (BPM, Volume, File Selection).

    Metronome: Built-in MIDI metronome with adjustable BPM and volume.

    Atomic State Sync: The web app and hardware stay perfectly in sync using JSON-based state management.

🛠 Quick Start

    Clone and Install:
    Bash

git clone https://github.com/yourusername/monkey-midi-player.git
cd monkey-midi-player
pip install -r requirements.txt

Prepare Folders: Ensure you have folders at ~/midifiles and ~/sf2 with your media.

Launch: It is recommended to run these in two separate terminal windows (or via systemd):
Bash

    # Window 1: The Remote Server
    python3 web_app.py

    # Window 2: The MIDI Engine
    python3 main.py

🔌 Hardware Setup

    Display: I2C OLED (128x64 or 240x240)

    Controls: Physical buttons for UP, DOWN, SELECT, and BACK.

    Audio: Supports ALSA-compatible DACs or the built-in 3.5mm jack.
