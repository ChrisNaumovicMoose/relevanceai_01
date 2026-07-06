# Claude cleanup prompt template

Used by `migrate_channel.py --use-claude-cleanup`, and equally usable by hand if
you ever fall back to the manual copy/paste workflow (e.g. for a channel you
can't reach via Graph API).

The script already builds each line as `[YYYY-MM-DD HH:MM] Name: Message`
straight from Microsoft Graph data, so Claude is **not** asked to invent or
guess names/timestamps — only to tidy presentation. If you're pasting raw,
messy Teams export text by hand instead, tell Claude that up front so it knows
it has to parse the metadata itself (see the "manual fallback" variant below).

## Automated / structured input (script default)

```
You will receive an already-correctly-timestamped and already-correctly-attributed
Microsoft Teams channel transcript, one line per message in the form:
[YYYY-MM-DD HH:MM] Name: Message

Do NOT change any timestamp or sender name — they are already accurate and pulled
directly from the source system. Your job is only to:
1. Merge consecutive lines that are clearly one logical message Teams split across
   multiple lines (same sender, same minute, no other sender in between).
2. Strip leftover HTML artifacts, "edited" tags, and empty reaction/read-receipt lines.
3. Preserve chronological order exactly as given.
4. Keep code blocks, bullet lists, and links intact and readable in Markdown.
5. Do not summarize, shorten, or omit any message content.

Return only the cleaned Markdown transcript, no commentary.

---
<PASTE TRANSCRIPT HERE>
```

## Manual fallback (raw copy/paste from the Teams UI, no API access)

```
Clean up this messy raw text copy-pasted from a Microsoft Teams channel. Reformat
it into a clean, chronological Markdown transcript using this exact line format:
[YYYY-MM-DD HH:MM] Name: Message

Rules:
- Infer the date/time and sender for each message from whatever fragments are
  present in the raw text (Teams usually repeats the sender name and a relative
  or absolute timestamp above each message block).
- If a timestamp is relative ("Yesterday 3:04 PM") or ambiguous, resolve it
  against the most recent absolute date/time you can find earlier in the text
  and flag anything you had to guess with a trailing "(approx.)".
- Merge multi-line messages from the same sender into one line.
- Preserve chronological order.
- Do not summarize or omit content.

Return only the cleaned Markdown transcript, no commentary.

---
<PASTE MESSY TEAMS TEXT HERE>
```

## "We've moved" announcement template

Post this once in each retired channel (and pin it manually — Graph has no API
for pinning channel messages):

```
📣 **We've moved!**

This channel is no longer active. All future conversation is happening in
**[<New Channel Name>](<https://teams.microsoft.com/l/channel/... deep link>)**
— click through and join us there. The full chat history and files from this
channel have been copied over.
```
