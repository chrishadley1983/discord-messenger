#!/bin/bash
pkill -f 'close-overlay.py' 2>/dev/null
export WAYLAND_DISPLAY=wayland-0
export XDG_RUNTIME_DIR=/run/user/1000
export GDK_BACKEND=wayland
nohup python3 /home/chrishadley1983/media-overlay/close-overlay.py > /dev/null 2>&1 &
disown
