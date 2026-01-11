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
    
📶 Smart Hotspot & Fast Boot Setup

This project features an intelligent WiFi Failover System. On boot, the device searches for a known Home WiFi network. If it isn't found within 10 seconds, it automatically transforms into a standalone WiFi Hotspot named "Zompler".
1. Prerequisite: Create the Hotspot

Run this command on your Pi to create the Zompler network profile (replace YourPassword with your desired password):
Bash

sudo nmcli device wifi hotspot con-name Zompler ssid Zompler password YourPassword
sudo nmcli connection modify Zompler connection.autoconnect no

2. Installation

    Download the Failover Script: Place wifi_failover.sh in your project directory and make it executable:
    Bash

chmod +x wifi_failover.sh

Install the Systemd Service: Copy the wifi-check.service file to /etc/systemd/system/ and enable it:
Bash

sudo cp wifi-check.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wifi-check.service

Update App Dependencies: Ensure your main application service (e.g., monkey-web.service) includes these lines in the [Unit] section:
Ini, TOML

    After=network.target wifi-check.service
    Requires=wifi-check.service

3. How to Connect

    At Home: Connect via your local network IP (e.g., http://192.168.1.XX:5000).

    At a Gig: Connect your phone to the "Zompler" WiFi network and navigate to http://192.168.4.1:5000.

4. Boot Performance

The system is optimized for a 20-second "Cold Boot" to fully operational status on a Raspberry Pi Zero 2W. It achieves this by bypassing IPv6 negotiation and using a rapid-polling network check loop.
