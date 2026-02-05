# Peter Dashboard - Critical Fixes Patch

## Apply these changes to app.py

### Fix 1: Update KEY_FILES (around line 46)

```python
# Replace the KEY_FILES dict with:
KEY_FILES = {
    "CLAUDE.md": "domains/peterbot/wsl_config/CLAUDE.md",
    "PETERBOT_SOUL.md": "domains/peterbot/wsl_config/PETERBOT_SOUL.md",
    "SCHEDULE.md": "domains/peterbot/wsl_config/SCHEDULE.md",
    "HEARTBEAT.md": "domains/peterbot/wsl_config/HEARTBEAT.md",
    "USER.md": "domains/peterbot/wsl_config/USER.md",
    "Bot Config": "domains/peterbot/config.py",
    "Router": "domains/peterbot/router.py",
    "Parser": "domains/peterbot/parser.py",
}
```

### Fix 2: Update WSL_FILES (around line 56)

```python
# Replace the WSL_FILES dict with:
WSL_FILES = {
    "context.md": "/home/chris_hadley/peterbot/context.md",
    "raw_capture.log": "/home/chris_hadley/peterbot/raw_capture.log",
    "HEARTBEAT.md": "/home/chris_hadley/peterbot/HEARTBEAT.md",
    "SCHEDULE.md": "/home/chris_hadley/peterbot/SCHEDULE.md",
}
```

### Fix 3: Update peterbot_session restart (around line 360)

```python
# Replace the peterbot_session restart block with:
elif service == "peterbot_session":
    # Kill and recreate tmux session
    run_wsl_command("tmux kill-session -t claude-peterbot 2>/dev/null || true")
    run_wsl_command(f"tmux new-session -d -s claude-peterbot -c {CONFIG['wsl_peterbot_path']}")
    # Source profile for proper environment, use current CLI flag
    run_wsl_command("tmux send-keys -t claude-peterbot 'source ~/.profile && claude --dangerously-skip-permissions' Enter")
    return {"status": "restarting", "message": "Peterbot session recreated"}
```

### Fix 4: Add heartbeat status endpoint (add after line 420)

```python
@app.get("/api/heartbeat/status")
async def get_heartbeat_status():
    """Get heartbeat system status including SCHEDULE.md and HEARTBEAT.md."""
    schedule = read_wsl_file("/home/chris_hadley/peterbot/SCHEDULE.md", tail_lines=0)
    heartbeat = read_wsl_file("/home/chris_hadley/peterbot/HEARTBEAT.md", tail_lines=0)
    
    # Parse to-do items from HEARTBEAT.md
    todos = []
    if heartbeat.get("exists") and heartbeat.get("content"):
        for line in heartbeat["content"].split("\n"):
            if "- [ ]" in line:
                todos.append({"text": line.replace("- [ ]", "").strip(), "done": False})
            elif "- [x]" in line.lower():
                todos.append({"text": line.replace("- [x]", "").replace("- [X]", "").strip(), "done": True})
    
    return {
        "schedule": schedule,
        "heartbeat": heartbeat,
        "todos": todos,
        "pending_count": len([t for t in todos if not t["done"]]),
        "completed_count": len([t for t in todos if t["done"]])
    }


@app.get("/api/skills")
async def list_skills():
    """List available Peterbot skills."""
    skills_path = "/home/chris_hadley/peterbot/.claude/skills"
    cmd = f"find {skills_path} -maxdepth 2 -name 'SKILL.md' 2>/dev/null"
    stdout, stderr, code = run_wsl_command(cmd)
    
    skills = []
    if stdout.strip():
        for path in stdout.strip().split('\n'):
            if path:
                # Extract skill name from path
                parts = path.split('/')
                name = parts[-2] if len(parts) > 1 else 'unknown'
                skills.append({
                    "name": name,
                    "path": path
                })
    
    return {"skills": skills, "count": len(skills)}


@app.get("/api/skill/{name}")
async def get_skill(name: str):
    """Get skill content by name."""
    path = f"/home/chris_hadley/peterbot/.claude/skills/{name}/SKILL.md"
    return read_wsl_file(path, tail_lines=0)
```

### Fix 5: Add sidebar navigation items (in DASHBOARD_HTML around line 880)

Add these nav items to the sidebar:

```html
<div class="sidebar-section">
    <h3>Proactive</h3>
    <div class="nav-item" data-view="heartbeat">
        💓 Heartbeat
    </div>
    <div class="nav-item" data-view="schedule">
        📅 Schedule
    </div>
    <div class="nav-item" data-view="skills">
        🛠️ Skills
    </div>
</div>
```

### Fix 6: Add JavaScript render functions (before the switchView function around line 1284)

```javascript
async function renderHeartbeat() {
    const content = document.getElementById('content');
    content.innerHTML = '<h2>Loading heartbeat...</h2>';
    
    const data = await api('/heartbeat/status');
    
    let todosHtml = '<p style="color: var(--text-secondary);">No to-do items found</p>';
    if (data.todos && data.todos.length > 0) {
        todosHtml = data.todos.map(item => `
            <div style="padding: 0.75rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 0.5rem;">
                <span style="font-size: 1.2rem;">${item.done ? '✅' : '⬜'}</span>
                <span style="color: ${item.done ? 'var(--text-secondary)' : 'var(--text-primary)'}; ${item.done ? 'text-decoration: line-through;' : ''}">
                    ${escapeHtml(item.text)}
                </span>
            </div>
        `).join('');
    }
    
    content.innerHTML = `
        <h2 style="margin-bottom: 1rem;">💓 Heartbeat System</h2>
        
        <div class="grid grid-2" style="margin-bottom: 1.5rem;">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Status</span>
                </div>
                <div style="display: flex; gap: 2rem;">
                    <div>
                        <div style="font-size: 2rem; font-weight: bold; color: var(--warning);">${data.pending_count || 0}</div>
                        <div style="font-size: 0.8rem; color: var(--text-secondary);">Pending</div>
                    </div>
                    <div>
                        <div style="font-size: 2rem; font-weight: bold; color: var(--success);">${data.completed_count || 0}</div>
                        <div style="font-size: 0.8rem; color: var(--text-secondary);">Completed</div>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Quick Actions</span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                    <button class="btn btn-secondary" onclick="viewFile('wsl', 'HEARTBEAT.md')">Edit HEARTBEAT.md</button>
                    <button class="btn btn-secondary" onclick="renderHeartbeat()">Refresh</button>
                </div>
            </div>
        </div>
        
        <div class="card">
            <div class="card-header">
                <span class="card-title">To-Do List</span>
            </div>
            ${todosHtml}
        </div>
    `;
}

async function renderSchedule() {
    const content = document.getElementById('content');
    content.innerHTML = '<h2>Loading schedule...</h2>';
    
    const data = await api('/file/wsl/SCHEDULE.md');
    
    content.innerHTML = `
        <h2 style="margin-bottom: 1rem;">📅 Schedule</h2>
        <p style="margin-bottom: 1rem; color: var(--text-secondary);">
            Peterbot's scheduled jobs configuration.
        </p>
        <div class="code-viewer">
            <div class="code-header">
                <span>SCHEDULE.md</span>
                <span style="font-size: 0.75rem; color: var(--text-secondary);">
                    ${data.exists ? `${data.size} bytes` : 'File not found'}
                </span>
            </div>
            <div class="code-content">
                <pre>${data.exists ? escapeHtml(data.content) : 'Schedule file not found'}</pre>
            </div>
        </div>
        <button class="btn btn-secondary" style="margin-top: 1rem;" onclick="renderSchedule()">Refresh</button>
    `;
}

async function renderSkills() {
    const content = document.getElementById('content');
    content.innerHTML = '<h2>Loading skills...</h2>';
    
    const data = await api('/skills');
    
    let skillsHtml = '<p style="color: var(--text-secondary);">No skills found</p>';
    if (data.skills && data.skills.length > 0) {
        skillsHtml = `
            <div class="grid grid-3">
                ${data.skills.map(skill => `
                    <div class="card" style="cursor: pointer;" onclick="viewSkill('${skill.name}')">
                        <div class="card-header">
                            <span class="card-title">🛠️ ${skill.name}</span>
                        </div>
                        <p style="font-size: 0.75rem; color: var(--text-secondary); font-family: monospace;">
                            ${skill.path}
                        </p>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    content.innerHTML = `
        <h2 style="margin-bottom: 1rem;">🛠️ Skills</h2>
        <p style="margin-bottom: 1rem; color: var(--text-secondary);">
            ${data.count || 0} skill(s) available. Click to view details.
        </p>
        ${skillsHtml}
    `;
}

async function viewSkill(name) {
    const content = document.getElementById('content');
    content.innerHTML = '<h2>Loading skill...</h2>';
    
    const data = await api(`/skill/${name}`);
    
    content.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <h2>🛠️ ${name}</h2>
            <button class="btn btn-secondary" onclick="renderSkills()">Back to Skills</button>
        </div>
        <div class="code-viewer">
            <div class="code-header">
                <span>SKILL.md</span>
            </div>
            <div class="code-content" style="max-height: 600px;">
                <pre>${data.exists ? escapeHtml(data.content) : 'Skill not found'}</pre>
            </div>
        </div>
    `;
}
```

### Fix 7: Update switchView function (around line 1294)

```javascript
function switchView(view) {
    currentView = view;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.view === view) item.classList.add('active');
    });

    // Render view
    switch(view) {
        case 'dashboard': renderDashboard(); break;
        case 'context': renderContext(); break;
        case 'captures': renderCaptures(); break;
        case 'memory': renderMemory(); break;
        case 'files': renderFiles(); break;
        case 'endpoints': renderEndpoints(); break;
        case 'sessions': renderSessions(); break;
        // NEW views for Phase 7
        case 'heartbeat': renderHeartbeat(); break;
        case 'schedule': renderSchedule(); break;
        case 'skills': renderSkills(); break;
    }
}
```

---

## Quick Test

After applying fixes:

1. Start the dashboard: `python -m uvicorn app:app --host 0.0.0.0 --port 8200`
2. Visit http://localhost:8200
3. Check new "Proactive" section in sidebar
4. Click "Heartbeat" to see to-do list parsing
5. Click "Skills" to see skills directory (if populated)
6. Test service restart for peterbot_session
