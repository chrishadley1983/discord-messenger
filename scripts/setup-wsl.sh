#!/bin/bash
# Full WSL setup script for Discord-Messenger with Claude Code Remote
# Run this in WSL after installing: bash /mnt/c/Users/Chris\ Hadley/Discord-Messenger/scripts/setup-wsl.sh

set -e

echo "=== Discord-Messenger WSL Setup ==="
echo ""

# Step 1: Install system dependencies
echo "[1/5] Installing system dependencies..."
sudo apt update
sudo apt install -y tmux jq python3 python3-pip python3-venv curl

# Step 2: Copy project to home directory
echo ""
echo "[2/5] Copying project to ~/Discord-Messenger..."
cp -r "/mnt/c/Users/Chris Hadley/Discord-Messenger" ~/Discord-Messenger
cd ~/Discord-Messenger

# Step 3: Set up Python virtual environment and install dependencies
echo ""
echo "[3/5] Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Step 4: Add ccremote alias
echo ""
echo "[4/5] Adding ccremote alias to ~/.bashrc..."
cat >> ~/.bashrc << 'EOF'

# Quick switch to remote-controllable Claude Code
ccremote() {
    tmux new-session -s "claude-${PWD##*/}" -c "$PWD" \; send-keys "claude" Enter
}

# Activate Discord-Messenger venv
alias discord-bot="cd ~/Discord-Messenger && source venv/bin/activate && python bot.py"
EOF

# Step 5: Create run script
echo ""
echo "[5/5] Creating run script..."
cat > ~/Discord-Messenger/run.sh << 'EOF'
#!/bin/bash
cd ~/Discord-Messenger
source venv/bin/activate
python bot.py
EOF
chmod +x ~/Discord-Messenger/run.sh

echo ""
echo "=== Setup Complete ==="
echo ""
echo "To start the bot:"
echo "  cd ~/Discord-Messenger"
echo "  ./run.sh"
echo ""
echo "Or use the alias:"
echo "  discord-bot"
echo ""
echo "To start a remote Claude Code session:"
echo "  cd ~/your-project"
echo "  ccremote"
echo "  # Detach with Ctrl+B, D"
echo ""
echo "Run 'source ~/.bashrc' to load the new aliases."
