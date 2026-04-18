# Peterbot Schedule

Peter can edit this file to manage scheduled jobs.
Run `!reload-schedule` after editing to apply changes.

---

## Fixed Time Jobs (Cron)

| Job | Skill | Schedule | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Parser Improvement | parser-improve | 02:00 UK | #peter-heartbeat!quiet | yes |
| Orphan Embed | orphan-embed | 03:00 UK | #alerts | yes |
| Morning Laughs | morning-laughs | 06:30 UK | #peterbot | yes |
| Morning Quality Report | morning-quality-report | 06:45 UK | #peter-heartbeat | yes |
| System Health | system-health | 06:50 UK | #alerts | yes |
| Life Admin Scan | life-admin-scan | 08:30 UK | #alerts+WhatsApp:chris | yes |
| Life Admin Email Scan | life-admin-email-scan | 03:30 UK | #peter-heartbeat!quiet | yes |
| Life Admin Dashboard | life-admin-dashboard | Sunday 09:15 UK | #peterbot | yes |
| Morning Briefing | morning-briefing | 07:01 UK | #ai-briefings | yes |
| Morning News | news | 07:02 UK | #news | yes |
| Kids Daily Briefing | kids-daily | 07:25 UK | #peterbot+WhatsApp:group | yes |
| Morning Cooking Reminder | cooking-reminder | 07:30 UK | #food-log | yes |
| Price Scanner | price-scanner | Mon 06:00 UK | #food-log | yes |
| Morning Health Digest | health-digest | 07:55 UK | #food-log | yes |
| Fitness Dashboard (Cut) | fitness-dashboard | 06:45 UK | #food-log | yes |
| School Run (Mon-Wed,Fri) | school-run | Mon-Wed,Fri 08:10 UK | #traffic-reports+WhatsApp:group | yes |
| School Run (Thu) | school-run | Thu 07:45 UK | #traffic-reports+WhatsApp:group | yes |
| GitHub Activity (Daily) | github-activity | 08:08 UK | #peterbot | yes |
| GitHub Activity (Weekly) | github-weekly | Sunday 18:05 UK | #peterbot | yes |
| Kids Weekly (Next Week) | kids-weekly | Sunday 18:10 UK | #peterbot+WhatsApp:group | yes |
| YouTube Digest | youtube-digest | 09:05 UK | #youtube | yes |
| Hydration Check-in | hydration | 07:02,08:02,09:02,10:02,11:02,12:02,13:02,14:02,15:02,16:02,17:02,18:02,19:02,20:02,21:02 UK | #food-log+WhatsApp:chris | yes |
| School Pickup (Mon,Tue,Thu,Fri) | school-pickup | Mon,Tue,Thu,Fri 14:55 UK | #traffic-reports+WhatsApp:group | yes |
| School Pickup (Wed) | school-pickup | Wed 16:50 UK | #traffic-reports+WhatsApp:group | yes |
| Meal Rating | meal-rating | 20:30 UK | #food-log | yes |
| Evening Cooking Reminder | cooking-reminder | 20:45 UK | #food-log | yes |
| Daily Nutrition Summary | nutrition-summary | 21:00 UK | #food-log | yes |
| Daily Instagram Prep | daily-instagram-prep | 21:05 UK | #peterbot | yes |
| Weekly Health Summary | weekly-health | Sunday 09:10 UK | #food-log | yes |
| Weekly Cut Review | weekly-cut-review | Sunday 09:00 UK | #food-log | yes |
| Fitness Advisor Check | fitness-advisor | 12:00,16:00,20:00 UK | #food-log | yes |
| Midweek Cut Nudge | fitness-dashboard | Wed 19:00 UK | #food-log | yes |
| Monthly Health Summary | monthly-health | 1st 09:15 UK | #food-log | yes |
| Claude History Reminder | - | 1st 10:00 UK | #peterbot | yes |
| WhatsApp Health Check | whatsapp-keepalive | 08:00,20:00 UK | #peter-heartbeat!quiet | yes |
| Self-Reflect | self-reflect | 12:00,18:00,23:00 UK | #alerts!quiet | yes |
| Email Summary | email-summary | 08:02 UK | #peterbot | yes |
| Schedule Today | schedule-today | 08:04 UK | #peterbot | yes |
| Schedule Week | schedule-week | Sunday 18:00 UK | #peterbot | yes |
| Notion Todos | notion-todos | 08:06 UK | #peterbot | yes |
| Balance Monitor | balance-monitor | hourly+3 UK | #api-costs | yes |
| Heartbeat | heartbeat | half-hourly+1 UK | #peter-heartbeat!quiet | yes |
| Healthera Prescriptions | healthera-prescriptions | 09:10 UK | #peterbot | yes |
| HB Full Sync + Print | hb-full-sync-print | 09:35 UK | #peterbot | yes |
| Weekly Spellings | school-weekly-spellings | Mon 07:30 UK | #peter-chat+WhatsApp:group | yes |
| Subscription Monitor | subscription-monitor | Sunday 09:02 UK | #alerts+WhatsApp:chris | yes |
| Recipe Discovery | recipe-discovery | Sunday 10:00 UK | #food-log | yes |
| Property Valuation | property-valuation | 1st 10:15 UK | #peterbot | yes |
| Saturday Sport Preview | saturday-sport-preview | Sat 08:00 UK | #peterbot+WhatsApp:chris | yes |
| Spurs Match Day | spurs-matchday | 08:00 UK | #peterbot+WhatsApp:chris | yes |
| Cricket Scores | cricket-scores | 08:30 UK | #peterbot+WhatsApp:chris | yes |
| Ballot Reminders | ballot-reminders | 09:00 UK | #peterbot+WhatsApp:chris | yes |
| PL Results | pl-results | 06:05 UK | #peterbot+WhatsApp:chris | yes |
| Amazon Purchases Sync | amazon-purchases | 09:30 UK | #peterbot | yes |
| Security Monitor | security-monitor | 06:00,10:00,14:00,18:00,22:00 UK | #alerts | yes |
| Tutor Email Parser | tutor-email-parser | Tue 19:00 UK | #peterbot | yes |
| Paper Builder | paper-builder | Tue 19:30 UK | #peterbot | yes |
| Practice Allocate | practice-allocate | Tue 21:00 UK | #peterbot | yes |
| Spelling Test Reminder | spelling-test-generator | Fri 19:00 UK | #peterbot+WhatsApp:chris | yes |
| Commitment Nudge | commitment-nudge | 19:00 UK | WhatsApp:chris | yes |
| Pocket Money Weekly | pocket-money-weekly | Sunday 09:32 UK | #peterbot | yes |
| Flight Price Monitor | flight-prices | 07:15 UK | #alerts | yes |
| Weekly Accountability | accountability-weekly | Sunday 19:00 UK | WhatsApp:chris | yes |
| Monthly Accountability | accountability-monthly | 1st 10:30 UK | #food-log+WhatsApp:chris | yes |

## Interval Jobs

| Job | Skill | Interval | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Spurs Live | spurs-live | 10m | #peterbot+WhatsApp:chris!quiet | yes |

## Quiet Hours

No jobs run between 23:00 and 06:00 UK.

---

## Notes

- **Schedule format**: `HH:MM UK` or `Day HH:MM UK` or `Day-Day,Day HH:MM UK`
- **Multiple times**: Comma-separated like `09:00,11:00,13:00 UK`
- **Hourly**: `hourly UK` runs at :00, `hourly+3 UK` runs at :03 (stagger to avoid collisions)
- **Half-hourly**: `half-hourly UK` runs at :00/:30, `half-hourly+1 UK` runs at :01/:31
- **Monthly**: `1st HH:MM UK` for first of month
- **WhatsApp**: Add `+WhatsApp` to channel name for dual posting (both Chris+Abby). Targets: `+WhatsApp:group` (Extended Team group), `+WhatsApp:group`, `+WhatsApp:abby`
- **Quiet hours exempt**: Add `!quiet` to channel name to run during quiet hours (e.g., `#alerts!quiet`)
- **NO_REPLY**: Skills can suppress output by returning just `NO_REPLY`