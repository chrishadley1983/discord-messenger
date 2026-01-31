# Git Repository Setup Guide

## Overview

Initialize git and push two local projects to GitHub. Repos already created:
- https://github.com/chrishadley1983/peterbot-mem
- https://github.com/chrishadley1983/discord-messenger

---

## Project 1: peterbot-mem

**Location:** WSL `~/peterbot-mem/` (or `/home/chris_hadley/peterbot-mem/`)

### Step 1: Create .gitignore

```bash
cd ~/peterbot-mem
cat > .gitignore << 'EOF'
# Secrets
.env
.env.*
*.pem
secrets/

# Node
node_modules/
dist/
*.log
npm-debug.log*

# Database files (keep schema, ignore data)
*.db
*.sqlite

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Build artifacts
build/
coverage/
EOF
```

### Step 2: Check for secrets

Before committing, verify no secrets in source files:

```bash
# Search for potential secrets (review output manually)
grep -r "sk-ant-" --include="*.ts" --include="*.js" --include="*.json" .
grep -r "ANTHROPIC" --include="*.ts" --include="*.js" .
grep -r "discord.*token" -i --include="*.ts" --include="*.js" --include="*.json" .
```

If found, move to `.env` and use `process.env.VAR_NAME` instead.

### Step 3: Initialize and push

```bash
cd ~/peterbot-mem
git init
git add .
git commit -m "Initial commit - peterbot-mem memory system

Forked from claude-mem with personality memory additions:
- Phase 1-5 implemented
- TieredRetrieval for context injection
- Supersede logic for observation deduplication
- /api/sessions/messages endpoint
- /api/context/inject endpoint
- peterbot.json personality extraction prompts"

git branch -M main
git remote add origin git@github.com:chrishadley1983/peterbot-mem.git
git push -u origin main
```

---

## Project 2: discord-messenger

**Location:** Windows, accessible via WSL at `/mnt/c/Users/Chris/path/to/Discord-Messenger/` (adjust path as needed)

### Step 1: Create .gitignore

```bash
cd /mnt/c/Users/Chris/path/to/Discord-Messenger  # ADJUST THIS PATH
cat > .gitignore << 'EOF'
# Secrets
.env
.env.*
*.pem
secrets/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
venv/
.venv/
env/
*.egg-info/
dist/
build/

# Logs
*.log
logs/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Draft/temp files (can remove after cleanup)
*-temp.json
*-updated.ts
EOF
```

### Step 2: Clean up draft files (optional but recommended)

```bash
# Remove old draft specs that are now implemented in peterbot-mem
rm -f peterbot-mode-temp.json
rm -f migrations-updated.ts
rm -f parser-updated.ts
rm -f observation-store-updated.ts
rm -f prompts-updated.ts

# Keep docs/phase-*.md for historical reference
```

### Step 3: Check for secrets

```bash
# Search for potential secrets
grep -r "sk-ant-" --include="*.py" --include="*.json" .
grep -r "ANTHROPIC" --include="*.py" .
grep -r "DISCORD.*TOKEN" -i --include="*.py" --include="*.json" .
grep -r "xai" -i --include="*.py" .
```

Ensure all secrets are in `.env` only, not hardcoded.

### Step 4: Initialize and push

```bash
cd /mnt/c/Users/Chris/path/to/Discord-Messenger  # ADJUST THIS PATH
git init
git add .
git commit -m "Initial commit - Discord bot with peterbot integration

Multi-domain Discord bot:
- domains/claude_code/ - tmux relay for Claude Code (Pre-A)
- domains/peterbot/ - personal assistant with memory (Phase 6 in progress)
- domains/nutrition/ - health tracking
- jobs/ - scheduled tasks (morning briefing, health reports)
- Connects to peterbot-mem worker for memory"

git branch -M main
git remote add origin git@github.com:chrishadley1983/discord-messenger.git
git push -u origin main
```

---

## Verification

After both pushes:

```bash
# Check peterbot-mem
cd ~/peterbot-mem
git status
git remote -v

# Check discord-messenger  
cd /mnt/c/Users/Chris/path/to/Discord-Messenger
git status
git remote -v
```

Both should show:
- `nothing to commit, working tree clean`
- `origin` pointing to the correct GitHub URL

---

## Notes

1. **SSH vs HTTPS**: Commands above use SSH (`git@github.com:`). If SSH isn't configured, use HTTPS instead:
   ```
   git remote add origin https://github.com/chrishadley1983/peterbot-mem.git
   ```

2. **Path for Discord-Messenger**: The exact Windows path needs to be confirmed. Common locations:
   - `/mnt/c/Users/Chris/Projects/Discord-Messenger/`
   - `/mnt/c/Users/Chris/Code/Discord-Messenger/`
   
3. **gh CLI alternative**: If `gh` is preferred over raw git:
   ```bash
   gh repo clone chrishadley1983/peterbot-mem  # Verify repo exists
   # Then in project folder:
   git init
   git add .
   git commit -m "Initial commit"
   gh repo sync  # If already linked
   ```
