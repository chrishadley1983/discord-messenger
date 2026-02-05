# Phase 8a Schedule Additions

Add these rows to `SCHEDULE.md`:

```markdown
## Scheduled Skills

| Job Name | Skill | Schedule | Channel | Needs Data |
|----------|-------|----------|---------|------------|
| ... existing entries ... |
| Email Summary | email-summary | 08:00 UK | #general | yes |
| Schedule Today | schedule-today | 08:00 UK | #general | yes |
| Schedule Week | schedule-week | 18:00 Sun UK | #general | yes |
| Notion Todos | notion-todos | 08:00 UK | #general | yes |
```

## Notes

1. **Morning Briefing Integration**
   
   Instead of separate 08:00 jobs, consider consolidating into `morning-briefing` skill:
   
   ```
   Morning Briefing includes:
   - Weather (existing)
   - Schedule Today (new)
   - Email Summary (new)  
   - Notion Todos (new)
   - Health Digest (existing)
   ```

2. **Conversational-Only Skills**
   
   These skills have NO schedule entry (triggered by conversation only):
   - `email-search`
   - `find-free-time`
   - `drive-search`
   - `notion-ideas`

3. **Skip-If-Empty Behavior**
   
   For scheduled runs, these skills should NOT post to Discord if:
   - `email-summary`: 0 unread emails
   - `notion-todos`: 0 pending tasks
   - `schedule-today`: 0 events (optional - some prefer "calendar clear" message)
