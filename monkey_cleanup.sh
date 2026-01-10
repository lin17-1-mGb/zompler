#!/bin/bash

# Define the working directory
BASE_DIR="/home/pi/midifileplayer"

echo "--- Starting Monkey MIDI System Cleanup ---"

# 1. Remove any 'ghost' command files left over from previous sessions
echo "Cleaning old command files..."
rm -f $BASE_DIR/cmd_*

# 2. Delete temporary or corrupted state files
echo "Resetting JSON state..."
rm -f $BASE_DIR/monkey_state.json
rm -f $BASE_DIR/monkey_state.json.tmp

# 3. Ensure permissions are correct (allows Web and Main script to talk)
echo "Fixing permissions..."
sudo chown pi:pi $BASE_DIR
sudo chmod 755 $BASE_DIR

# 4. Check if fluidsynth or aplaymidi are hanging in the background
echo "Killing hanging processes..."
sudo pkill -9 aplaymidi
sudo pkill -9 fluidsynth

echo "--- Cleanup Complete. System is ready for boot. ---"
