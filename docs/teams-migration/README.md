# Teams Channel Migration Playbook

Automates moving an old Microsoft Teams channel's **files/recordings** and **chat
history** into a new channel, then leaves a pinned "we've moved" pointer behind.
Companion script: [`scripts/teams_migration/migrate_channel.py`](../../scripts/teams_migration/migrate_channel.py).

## What's actually automatable (read this first)

Microsoft Graph draws a hard line between three things you asked for. Know which
bucket you're in before you start:

| Goal | Automatable? | How |
|---|---|---|
| Copy files & meeting recordings to the new channel's Files tab | **Yes, fully** | `driveItem: copy` — one API call copies the whole channel Files folder (including a `Recordings` subfolder) into the new channel. |
| Post the "We've moved" announcement in the old channel | **Yes, fully** | Normal `POST .../messages` call, sent as you. |
| Pin any message (old or new channel) | **No API exists** | Microsoft Graph only supports pinning messages in 1:1/group **chats** (`/chats/{id}/pinnedMessages`), not team **channels**. Channel pinning is a Teams-client-only action (right-click → Pin). The script prints a one-line reminder with a direct link to the message when a post needs pinning. |
| Repost chat history with the *original* sender name + exact original timestamp shown as text | **Yes** | The script reads messages via Graph (real sender + real timestamp are structured data — no more error-prone "paste into Claude and hope it parses correctly") and writes a `[YYYY-MM-DD HH:MM] Name: Message` transcript, posted as one announcement. Optional Claude cleanup pass tidies formatting/threading. |
| Repost chat history so Teams shows each message as *actually sent* by the original person at the original moment (native metadata, not just text) | **Yes, but heavyweight** | Requires the Teams **message migration API** (`channel: startMigration` / `completeMigration`, `Teamwork.Migrate.All` **application** permission, tenant-admin-consented Azure AD app). Only works cleanly on a channel that hasn't had real activity yet, and only for senders in the same tenant. See [Mode B](#mode-b-native-metadata-migration-heavyweight) below. |

If your destination channels are already live/in use, use **Mode A**
(transcript). If you can guarantee the destination channel is untouched and you
can get a tenant admin to register an app, **Mode B** gives you native,
per-message fidelity.

## Prerequisites

1. Python 3.9+, `pip install -r scripts/teams_migration/requirements.txt`.
2. You (or an admin) need an Azure AD app registration for Graph API access:
   - **Mode A (transcript + files, delegated, run as yourself):** a public
     client app registration (or reuse an existing one) with delegated
     permissions `ChannelMessage.Read.All`, `ChannelMessage.Send`,
     `Channel.ReadBasic.All`, `Files.ReadWrite.All`, `Sites.ReadWrite.All`.
     No admin consent needed for most tenants if these are already
     admin-consented org-wide; otherwise ask an admin to consent once.
   - **Mode B (native migration, application permissions):** an app
     registration with **application** permission `Teamwork.Migrate.All`
     (admin consent required) plus `ChannelMessage.Read.All` (application)
     on the source. This is an IT/admin task, not a per-user one.
3. The Team ID and Channel ID for both source and destination channels. Easiest
   way to get them: in Teams, open the channel → `...` → **Get link to
   channel**, then decode the `groupId` (team) and `channelId` (URL-encoded
   `19:...@thread.tacv2`) from the link, or use `python migrate_channel.py
   whoami` / Graph Explorer.

Set environment variables (see `.env.example` pattern below — don't commit
real secrets):

```
GRAPH_TENANT_ID=...
GRAPH_CLIENT_ID=...            # delegated app for Mode A
GRAPH_CLIENT_ID_APPONLY=...    # app-only registration for Mode B (optional)
GRAPH_CLIENT_SECRET=...        # only for Mode B
ANTHROPIC_API_KEY=...          # optional, only for the Claude cleanup pass
```

## Mode A: transcript migration (recommended default)

```bash
python scripts/teams_migration/migrate_channel.py all \
  --source-team <sourceTeamId> --source-channel <sourceChannelId> \
  --dest-team <destTeamId>   --dest-channel <destChannelId> \
  --moved-message "We've moved! 👉 Click here to join the new channel." \
  --use-claude-cleanup
```

This runs, in order:

1. **`files`** — copies the source channel's entire Files folder (including any
   `Recordings` subfolder from channel meetings) into the destination
   channel's Files folder, under a subfolder named after the source channel.
2. **`transcript`** — pulls every top-level message and reply from the source
   channel via Graph, sorts them chronologically, and renders
   `[YYYY-MM-DD HH:MM] Real Sender Name: message text` lines directly from the
   Graph data (not guessed by an LLM). If `--use-claude-cleanup` is set and
   `ANTHROPIC_API_KEY` is present, it sends that draft to Claude using the
   prompt in [`cleanup_prompt_template.md`](../../scripts/teams_migration/cleanup_prompt_template.md)
   for a light formatting/dedup pass — Claude never re-derives names or times,
   it only tidies presentation. The result is posted as one announcement (or
   several, numbered, if it exceeds Teams' message size limit) in the
   destination channel.
3. **`announce`** — posts the "we've moved" message (with a real deep link to
   the destination channel, taken from Graph's `webUrl`) into the *source*
   channel.
4. Prints a checklist of the messages you still need to **pin manually** (one
   click each in the Teams client) — this cannot be done via API.

Each subcommand can also be run individually — useful for dry runs
(`--dry-run` writes the transcript to a local file instead of posting).

## Mode B: native metadata migration (heavyweight)

Only attempt this if the destination channel has **zero** real messages in it
yet (migration mode is designed for freshly created channels) and you have a
tenant admin who can register an app with `Teamwork.Migrate.All`.

```bash
python scripts/teams_migration/migrate_channel.py full-import \
  --source-team <sourceTeamId> --source-channel <sourceChannelId> \
  --dest-team <destTeamId>   --dest-channel <destChannelId>
```

This calls `startMigration` on the destination channel, replays every source
message with its original `createdDateTime` and `from` (sender must belong to
your tenant), then calls `completeMigration` to return the channel to normal
use. Because this hits a **beta** Graph endpoint whose exact request shape
Microsoft revises periodically, treat the script's `full_import()` function as
a starting point — verify field names against the current
[Teams message migration docs](https://learn.microsoft.com/en-us/graph/teams-import-messages)
before running it against real data, and test against a throwaway team first.
Files/recordings still need the separate `files` step above; pinning is still
manual.

## What you still have to do by hand

- **Pinning**, in both modes, in both old and new channels — no Graph API for
  channel message pinning exists as of this writing.
- Reviewing the generated transcript before posting if you care about tone —
  use `--dry-run` to write it to a file first.
- Getting admin consent / app registration for Mode B.
