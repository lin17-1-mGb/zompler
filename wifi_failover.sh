#!/bin/bash

# Only wait 8 seconds - if it's not found by then, it won't be
MAX_RETRIES=8
CONNECTED=false

for ((i=1; i<=$MAX_RETRIES; i++)); do
    # Check for connection state rather than just IP address
    if nmcli -t -f TYPE,STATE dev | grep -q "wifi:connected"; then
        echo "WiFi connected in $i seconds!"
        CONNECTED=true
        break
    fi
    sleep 1
done

if [ "$CONNECTED" = false ]; then
    echo "Switching to Hotspot..."
    sudo nmcli con up Zompler
    # Force the IP immediately without waiting for DHCP
    sudo ifconfig wlan0 192.168.4.1 netmask 255.255.255.0 up
fi
