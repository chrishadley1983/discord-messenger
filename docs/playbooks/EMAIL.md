# Email Playbook

READ THIS before drafting replies, summarizing threads, or triaging inbox.

## Capabilities

Peter has Gmail API access via Hadley API:
- Search: /gmail/search, /gmail/unread, /gmail/starred
- Read: /gmail/get, /gmail/thread
- Draft: /gmail/draft (safer — creates draft for Chris to review)
- Send: /gmail/send (use ONLY when Chris explicitly says "send it")

## Drafting Emails

### Always
- Match the tone of the thread (formal ↔ casual)
- Keep it short — Chris writes concise emails
- Sign off as "Chris" (business) or "Thanks, Chris" (semi-formal)
- Use /gmail/draft by default — let Chris review before sending

### Never
- Use /gmail/send without explicit permission ("send it", "fire it off")
- Over-explain or pad with unnecessary pleasantries
- Assume email addresses — search first, ask if unsure

### Tone Calibration
- **Business (suppliers, marketplace comms):** Professional, direct, brief
- **Personal (friends, family):** Warm but still concise
- **Professional services (rentals, utilities):** Polite, to the point
- **Formal (HMRC, solicitors):** Careful, precise language

## Thread Summarization

When asked "what does this email say" or "summarize this thread":

1. **Who** — sender(s) and their role/context
2. **What** — the key point in one sentence
3. **Action needed** — what Chris needs to do (if anything)
4. **Deadline** — if there is one

Format:
📧 **From:** [Name] at [Company/Context]
**Gist:** [One sentence]
**Action:** [What Chris needs to do, or "None"]
**By:** [Deadline or "No deadline"]

## Inbox Triage

When asked "anything important" or "check my emails":

1. Fetch unread: /gmail/unread
2. Categorize by urgency:
   - 🔴 **Action needed today** — orders, time-sensitive
   - 🟡 **Worth reading** — business updates, personal
   - ⚪ **Skip** — newsletters, promotions, automated
3. Present as a scannable list, most important first
4. Offer to drill into any specific thread

## What GOOD Looks Like

📧 **3 unread worth your attention:**

🔴 **[Sender]** — [Urgent thing]. Needs response within [timeframe].

🟡 **[Sender]** — [Interesting thing]. [Brief context].

⚪ X others: newsletters, promotions, automated notifications

Want me to draft a reply to any of these?

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

| Query | Endpoint | Method |
|-------|----------|--------|
| Unread emails | `/gmail/unread?limit=10` | GET |
| Search emails | `/gmail/search?q=from:sarah` | GET |
| Get full email | `/gmail/get?id=<message_id>` | GET |
| Get labels | `/gmail/labels` | GET |
| Starred emails | `/gmail/starred` | GET |
| Full thread | `/gmail/thread?id=<thread_id>` | GET |
| Create draft | `/gmail/draft?to=...&subject=...&body=...` | POST |
| Send email | `/gmail/send?to=...&subject=...&body=...` | POST |
| Reply to email | `/gmail/reply?message_id=...&body=...` | POST |
| Archive email | `/gmail/archive?message_id=...` | POST |
| Trash email | `/gmail/trash?message_id=...` | POST |
| Mark read/unread | `/gmail/mark-read?message_id=...&read=true` | POST |
| Forward email | `/gmail/forward?message_id=...&to=...` | POST |
| Get attachments | `/gmail/attachments?message_id=...` | GET |
| Attachment text | `/gmail/attachment/text?message_id=...&attachment_id=...` | GET |
| Get vacation | `/gmail/vacation` | GET |
| Set vacation | `/gmail/vacation?enabled=true&subject=...&body=...` | POST |
| List filters | `/gmail/filters` | GET |
| Create filter | `/gmail/filters?from=...&action=trash` | POST |
| Get signature | `/gmail/signature` | GET |
| Set signature | `/gmail/signature?signature=...` | POST |

## Trigger Phrases

- "Any emails from X?" → `/gmail/search?q=from:X`
- "Read that email" / "Show me the full email" → `/gmail/get?id=<id>`
- "Show me the whole conversation" → `/gmail/thread?id=<thread_id>`
- "My starred emails" → `/gmail/starred`
- "Email Sarah about the meeting" → `/gmail/draft` (safer) or `/gmail/send`
- "Reply to that saying thanks" → `/gmail/reply?message_id=<id>&body=Thanks!`
- "Archive that email" → `/gmail/archive?message_id=<id>`
- "Delete that email" → `/gmail/trash?message_id=<id>`
- "Mark as read" → `/gmail/mark-read?message_id=<id>&read=true`
- "Forward that to Sarah" → `/gmail/forward?message_id=<id>&to=sarah@example.com`
- "Get the PDF from that email" → `/gmail/attachments?message_id=<id>`
- "Is my vacation responder on?" → `/gmail/vacation`
- "Turn on my out of office" → `/gmail/vacation` (POST with enabled=true)
- "What filters do I have?" → `/gmail/filters`
