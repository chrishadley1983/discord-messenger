# Utilities Playbook

Ad-hoc utility endpoints for casual queries that don't fit other playbooks.

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

### Reference & Knowledge

| Query | Endpoint | Method |
|-------|----------|--------|
| Wikipedia summary | `/wikipedia?query=Alan+Turing` | GET |
| Dictionary definition | `/dictionary?word=serendipity` | GET |
| Synonyms | `/synonyms?word=happy` | GET |
| Random quote | `/quote` | GET |
| Random fact | `/fact` | GET |

### Generators

| Query | Endpoint | Method |
|-------|----------|--------|
| QR code | `/qrcode?data=https://example.com` | GET |
| Shorten URL | `/shorten?url=https://...` | GET |
| UUID generator | `/uuid?count=5` | GET |
| Random number | `/random?min=1&max=100` | GET |
| Password generator | `/password?length=16&symbols=true` | GET |

### Date & Time

| Query | Endpoint | Method |
|-------|----------|--------|
| Countdown | `/countdown?target=2026-12-25` | GET |
| Age calculator | `/age?birthdate=1983-05-15` | GET |
| Holidays | `/holidays?country=GB&year=2026` | GET |

### Web Content Fetching

| Query | Endpoint | Method |
|-------|----------|--------|
| Fetch URL content | `/fetch-url?url=https://example.com` | GET |

**Notes:**
- Extracts text from PDFs (uses pypdf) and HTML pages (uses readability)
- Use this for PDFs or pages that WebFetch can't handle due to WSL network issues
- Returns: `url`, `type` (pdf/html/text), `text`, `truncated`, `total_chars`, `fetched_at`

### Network & Technical

| Query | Endpoint | Method |
|-------|----------|--------|
| IP info | `/ip?address=8.8.8.8` | GET |
| DNS lookup | `/dns?domain=google.com` | GET |
| WHOIS | `/whois?domain=example.com` | GET |
| Ping | `/ping?host=google.com` | GET |

### Encoding & Conversion

| Query | Endpoint | Method |
|-------|----------|--------|
| Color info | `/color?hex=FF5733` | GET |
| Encode/decode | `/encode?text=Hello&mode=base64` | GET |
| Calculate | `/calculate?expr=sqrt(144)+15*3` | GET |

### Media

| Query | Endpoint | Method |
|-------|----------|--------|
| YouTube search | `/youtube/search?q=cooking+pasta` | GET |

### WhatsApp (Twilio Sandbox)

| Action | Endpoint | Method |
|--------|----------|--------|
| Send text message | `/whatsapp/send?message=Hello&to=chris` | POST |
| Send with image | `/whatsapp/send?message=Check this&to=chris&media_url=https://...` | POST |
| Check config status | `/whatsapp/status` | GET |

**Notes:**
- `to` can be: `chris`, `me`, or a full phone number with country code (+447855620978)
- `media_url` must be a publicly accessible URL (Twilio fetches it)
- Twilio sandbox requires recipients to have joined first (send "join <phrase>" to +1 415 523 8886)

---

## Trigger Phrases

- "Tell me about Alan Turing" → `/wikipedia?query=Alan+Turing`
- "What does serendipity mean?" → `/dictionary?word=serendipity`
- "Synonyms for happy" → `/synonyms?word=happy`
- "Give me a quote" → `/quote`
- "Tell me a random fact" → `/fact`
- "Generate a QR code for this URL" → `/qrcode?data=...`
- "Shorten this URL" → `/shorten?url=...`
- "Generate some UUIDs" → `/uuid?count=5`
- "Pick a random number 1-100" → `/random?min=1&max=100`
- "Generate a secure password" → `/password?length=16&symbols=true`
- "How long until Christmas?" → `/countdown?target=2026-12-25`
- "How old is someone born May 15, 1983?" → `/age?birthdate=1983-05-15`
- "What are the UK bank holidays?" → `/holidays?country=GB&year=2026`
- "Where is IP 8.8.8.8?" → `/ip?address=8.8.8.8`
- "DNS lookup for google.com" → `/dns?domain=google.com`
- "Who owns example.com?" → `/whois?domain=example.com`
- "Ping google.com" → `/ping?host=google.com`
- "What color is #FF5733?" → `/color?hex=FF5733`
- "Encode hello in base64" → `/encode?text=hello&mode=base64`
- "What's 144 squared root plus 45?" → `/calculate?expr=sqrt(144)+45`
- "Find YouTube videos about cooking pasta" → `/youtube/search?q=cooking+pasta`
- "WhatsApp me that link" → `/whatsapp/send?message=...&to=chris`
- "Send me a WhatsApp with this image" → `/whatsapp/send?message=...&media_url=...`
- "Fetch this PDF for me" → `/fetch-url?url=...`
- "Get the content from this URL" → `/fetch-url?url=...`
