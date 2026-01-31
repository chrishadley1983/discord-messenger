#!/bin/bash
# Setup script for ccremote alias
# Run this in WSL: bash scripts/setup-ccremote.sh

cat >> ~/.bashrc << 'EOF'

# Quick switch to remote-controllable Claude Code
ccremote() {
    tmux new-session -s "claude-${PWD##*/}" -c "$PWD" \; send-keys "claude" Enter
}
EOF

echo "Added ccremote to ~/.bashrc"
echo ""
echo "Run 'source ~/.bashrc' or open a new terminal to use it."
echo ""
echo "Usage:"
echo "  cd ~/your-project"
echo "  ccremote"
echo "  # Detach with Ctrl+B, D"
