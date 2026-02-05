// Check memory queue status
const Database = require('better-sqlite3');
const db = new Database('/home/chris_hadley/.claude-mem/claude-mem.db');

// Pending messages
const pending = db.prepare(`SELECT COUNT(*) as c FROM pending_messages WHERE status IN ('pending', 'processing')`).get();
console.log('Pending messages:', pending.c);

// Failed messages
const failed = db.prepare(`SELECT COUNT(*) as c FROM pending_messages WHERE status = 'failed'`).get();
console.log('Failed messages:', failed.c);

// Sessions with empty project
const emptyProject = db.prepare(`SELECT COUNT(*) as c FROM sdk_sessions WHERE project = '' OR project IS NULL`).get();
console.log('Sessions with empty project:', emptyProject.c);

// Clear failed messages older than 1 hour
const cleared = db.prepare(`DELETE FROM pending_messages WHERE status = 'failed' AND created_at_epoch < ?`).run(Date.now() - 3600000);
console.log('Cleared old failed:', cleared.changes);

// Reset stuck processing messages back to pending
const reset = db.prepare(`UPDATE pending_messages SET status = 'pending', started_processing_at_epoch = NULL WHERE status = 'processing' AND started_processing_at_epoch < ?`).run(Date.now() - 300000);
console.log('Reset stuck processing:', reset.changes);

db.close();
console.log('Done');
