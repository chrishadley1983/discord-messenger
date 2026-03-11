# WhatsApp — Rules & Reference

## When to Send vs When to Just Reply

**Only send a WhatsApp message when Chris explicitly asks you to send/message someone.**

Explicit send triggers (USE the API):
- "Send Abby a message saying..."
- "WhatsApp Chris to say..."
- "Message Abby on WhatsApp"
- "Text Abby that..."
- "Send a voice note to..."

Conversational phrases (just REPLY in chat — do NOT send anything):
- "Say hi to the kids for me"
- "Tell Emmie good morning"
- "Say good morning to Emmie and Max"
- "Wish Abby happy birthday"

If in doubt, **do not send**. Ask Chris: "Do you want me to actually send that on WhatsApp, or just say it here?"

## Sending Messages

**Endpoint:** `POST http://172.19.64.1:8100/whatsapp/send?to=<contact>&message=<text>`

- `to` accepts: phone number (e.g. `447855620978`), contact name (`chris`, `abby`), or group JID
- `GET http://172.19.64.1:8100/whatsapp/status` — check connection status
- For replies to incoming WhatsApp messages, you don't need this — replies are sent automatically

## Sending Voice Notes

**Endpoint:** `POST http://172.19.64.1:8100/whatsapp/send-voice?to=<contact>&message=<text>`

- Generates a voice note from the message text (Kokoro TTS, bm_daniel voice) and sends it
- Also sends the text as a regular message alongside the voice note
- Use when Chris explicitly asks to send a voice note/voice message

## Contacts

| Name | Number | Notes |
|------|--------|-------|
| chris | 447855620978 | Chris Hadley |
| abby | 447856182831 | Abby Hadley |

**Family without WhatsApp:**
- **Emmie** (Emilia Hadley, born 1 Nov 2016) — no phone, no WhatsApp
- **Max** (Maxwell Hadley, born 9 Sep 2018) — no phone, no WhatsApp

If Chris asks to message Emmie or Max directly, tell him they don't have phones. Offer to send to Chris or Abby's phone instead, but only if Chris confirms.

## Name Accuracy

When STT transcribes a name (e.g. "Emmy", "Emi"), **always cross-reference against Second Brain** before using it. Search `family details` or the person's name to get the correct spelling. Never trust the transcription blindly for proper nouns.

## Strict Rules

1. **Only message the exact person(s) Chris names.** Never add extra recipients. Never reroute to a different contact.
2. **If a contact isn't in the list above, say so.** Ask Chris for the number — never guess.
3. **If the send API returns an error, report the error honestly.** Never claim success without a 200 response.
4. **Never claim to have sent a message you didn't send.** If the curl failed or you didn't run it, say so.

## Voice Message Replies (Automatic)

Messages tagged `[Voice]` or `[WhatsApp voice]` are spoken by Chris. Your text reply is automatically:
1. Sent as a text message on WhatsApp
2. Converted to speech (Kokoro TTS, bm_daniel voice) and sent as a WhatsApp voice note

All of this happens automatically — you do NOT need to call any API. Just reply normally with speech-friendly text.

**Voice reply style rules:**
- **Keep it short** — 1-3 sentences max. Think how you'd reply in a real conversation.
- **No formatting** — no bold, italic, bullet points, lists, headers, or emojis. Plain speech only.
- **No URLs or code** — these are unreadable when spoken aloud.
- **Conversational tone** — natural, flowing sentences. Not a report.
- **If the answer needs detail**, give the short spoken answer first, then say "I'll send the details as a text message" (your text reply goes through too).

Example — if Chris asks "what's on my calendar today?":
- Bad: "**📅 Today's Calendar:**\n- 10:00 — Dentist\n- 15:00 — School pickup"
- Good: "You've got the dentist at ten, then school pickup at three. Nothing else."
