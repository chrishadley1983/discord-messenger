# Peterbot Schedule

Peter can edit this file to manage scheduled jobs.
Run `!reload-schedule` after editing to apply changes.

---

## Fixed Time Jobs (Cron)

| Job | Skill | Schedule | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Parser Improvement | parser-improve | 02:00 UK | #peter-heartbeat!quiet | yes |
| Morning Quality Report | morning-quality-report | 06:45 UK | #peter-heartbeat | yes |
| Morning Briefing | morning-briefing | 07:00 UK | #ai-briefings | yes |
| Morning News | news | 07:02 UK | #news | yes |
| Morning Health Digest | health-digest | 07:55 UK | #food-log | yes |
| School Run (Mon-Wed,Fri) | school-run | Mon-Wed,Fri 08:10 UK | #traffic-reports+WhatsApp | yes |
| School Run (Thu) | school-run | Thu 07:45 UK | #traffic-reports+WhatsApp | yes |
| YouTube Digest | youtube-digest | 09:05 UK | #youtube | yes |
| Hydration Check-in | hydration | 09:02,11:02,13:02,15:02,17:02,19:02,21:02 UK | #food-log | yes |
| School Pickup (Mon,Tue,Thu,Fri) | school-pickup | Mon,Tue,Thu,Fri 14:55 UK | #traffic-reports+WhatsApp | yes |
| School Pickup (Wed) | school-pickup | Wed 16:50 UK | #traffic-reports+WhatsApp | yes |
| Daily Nutrition Summary | nutrition-summary | 21:00 UK | #food-log | yes |
| Weekly Health Summary | weekly-health | Sunday 09:10 UK | #food-log | yes |
| Monthly Health Summary | monthly-health | 1st 09:15 UK | #food-log | yes |
| WhatsApp Keepalive | whatsapp-keepalive | 06:00,22:00 UK | #peterbot!quiet | yes |
| Self-Reflect | self-reflect | 12:00,18:00,23:00 UK | #alerts!quiet | yes |
| Email Summary | email-summary | 08:02 UK | #peterbot | yes |
| Schedule Today | schedule-today | 08:04 UK | #peterbot | yes |
| Schedule Week | schedule-week | Sunday 18:00 UK | #peterbot | yes |
| Notion Todos | notion-todos | 08:06 UK | #peterbot | yes |
| Balance Monitor | balance-monitor | hourly+3 UK | #api-costs | yes |
| Heartbeat | heartbeat | half-hourly+1 UK | #peter-heartbeat!quiet | yes |
| Email Purchase Import | hb-email-purchases | 02:17 UK | 1466020068021240041!quiet | yes |
| HB Full Sync + Print | hb-full-sync-print | 09:35 UK | #peterbot | yes |

## Interval Jobs

*All interval jobs converted to fixed cron schedules above (see Balance Monitor, Heartbeat)*

## Quiet Hours

No jobs run between 23:00 and 06:00 UK.

---

## Notes

- **Schedule format**: `HH:MM UK` or `Day HH:MM UK` or `Day-Day,Day HH:MM UK`
- **Multiple times**: Comma-separated like `09:00,11:00,13:00 UK`
- **Hourly**: `hourly UK` runs at :00, `hourly+3 UK` runs at :03 (stagger to avoid collisions)
- **Half-hourly**: `half-hourly UK` runs at :00/:30, `half-hourly+1 UK` runs at :01/:31
- **Monthly**: `1st HH:MM UK` for first of month
- **WhatsApp**: Add `+WhatsApp` to channel name for dual posting
- **Quiet hours exempt**: Add `!quiet` to channel name to run during quiet hours (e.g., `#alerts!quiet`)
- **NO_REPLY**: Skills can suppress output by returning just `NO_REPLY`
