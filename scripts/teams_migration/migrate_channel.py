#!/usr/bin/env python3
"""Migrate a Microsoft Teams channel's files, recordings, and chat history
into a new channel, then post a "we've moved" pointer in the old one.

See docs/teams-migration/README.md for setup, required Graph permissions, and
the hard limits of what Graph can and can't automate (notably: pinning a
channel message has no API and must be done by hand in the Teams client).

Usage:
    python migrate_channel.py all --source-team ... --source-channel ... \\
        --dest-team ... --dest-channel ... --moved-message "..." \\
        --use-claude-cleanup

    python migrate_channel.py files --source-team ... --source-channel ... \\
        --dest-team ... --dest-channel ...

    python migrate_channel.py transcript --source-team ... --source-channel ... \\
        --dest-team ... --dest-channel ... --dry-run out.md

    python migrate_channel.py announce --source-team ... --source-channel ... \\
        --dest-team ... --dest-channel ... --moved-message "..."

    python migrate_channel.py full-import --source-team ... --source-channel ... \\
        --dest-team ... --dest-channel ...
"""
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import textwrap
import time
from dataclasses import dataclass
from typing import Iterator, Optional

import requests

GRAPH = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"

# Teams message bodies get unwieldy well before Graph's hard cap; split
# transcripts into parts under this size to stay readable and safe.
MAX_POST_CHARS = 20_000

DELEGATED_SCOPES = [
    "ChannelMessage.Read.All",
    "ChannelMessage.Send",
    "Channel.ReadBasic.All",
    "Files.ReadWrite.All",
    "Sites.ReadWrite.All",
]


def env(name: str, required: bool = True, default: Optional[str] = None) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def get_delegated_token() -> str:
    """Interactive device-code sign-in as the user running the script.

    Used for everything except full native message migration (Mode B), which
    requires application permissions instead (see get_app_only_token).
    """
    import msal

    tenant_id = env("GRAPH_TENANT_ID")
    client_id = env("GRAPH_CLIENT_ID")
    app = msal.PublicClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant_id}"
    )
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(DELEGATED_SCOPES, account=accounts[0])
    if not result:
        flow = app.initiate_device_flow(scopes=DELEGATED_SCOPES)
        if "user_code" not in flow:
            sys.exit(f"Failed to start device flow: {flow}")
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        sys.exit(f"Auth failed: {result.get('error_description', result)}")
    return result["access_token"]


def get_app_only_token() -> str:
    """Client-credentials sign-in for Mode B (Teamwork.Migrate.All)."""
    import msal

    tenant_id = env("GRAPH_TENANT_ID")
    client_id = env("GRAPH_CLIENT_ID_APPONLY")
    client_secret = env("GRAPH_CLIENT_SECRET")
    app = msal.ConfidentialClientApplication(
        client_id,
        client_credential=client_secret,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        sys.exit(f"App-only auth failed: {result.get('error_description', result)}")
    return result["access_token"]


class GraphClient:
    def __init__(self, token: str, base: str = GRAPH):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.base = base

    def get(self, path: str, **kwargs) -> dict:
        url = path if path.startswith("http") else f"{self.base}{path}"
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_paged(self, path: str) -> Iterator[dict]:
        url = f"{self.base}{path}"
        while url:
            resp = self.session.get(url)
            resp.raise_for_status()
            data = resp.json()
            yield from data.get("value", [])
            url = data.get("@odata.nextLink")

    def post(self, path: str, json_body: dict) -> dict:
        resp = self.session.post(f"{self.base}{path}", json=json_body)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def post_raw(self, path: str, json_body: dict) -> requests.Response:
        resp = self.session.post(f"{self.base}{path}", json=json_body)
        resp.raise_for_status()
        return resp


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class ChatLine:
    created: str  # ISO 8601 from Graph, already sortable as a string
    sender: str
    text: str

    def formatted(self) -> str:
        stamp = self.created.replace("T", " ")[:16]  # YYYY-MM-DDTHH:MM:SS -> YYYY-MM-DD HH:MM
        return f"[{stamp}] {self.sender}: {self.text}"


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(content: str, content_type: str) -> str:
    if content_type != "html":
        return content.strip()
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>", "\n", content)
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()


def message_to_line(msg: dict) -> Optional[ChatLine]:
    body = msg.get("body", {})
    text = strip_html(body.get("content", ""), body.get("contentType", "text"))
    if not text:
        return None  # system events, reactions-only, deleted messages, etc.
    sender = (msg.get("from") or {}).get("user", {}).get("displayName") or "Unknown sender"
    return ChatLine(created=msg["createdDateTime"], sender=sender, text=text)


# --------------------------------------------------------------------------
# Graph operations
# --------------------------------------------------------------------------

def get_channel(gc: GraphClient, team_id: str, channel_id: str) -> dict:
    return gc.get(f"/teams/{team_id}/channels/{channel_id}")


def fetch_all_messages(gc: GraphClient, team_id: str, channel_id: str) -> list[dict]:
    """All top-level messages plus their replies, flattened."""
    messages = []
    for msg in gc.get_paged(f"/teams/{team_id}/channels/{channel_id}/messages"):
        messages.append(msg)
        if msg.get("replies@odata.count", 0) or True:
            for reply in gc.get_paged(
                f"/teams/{team_id}/channels/{channel_id}/messages/{msg['id']}/replies"
            ):
                messages.append(reply)
    return messages


def build_transcript(gc: GraphClient, team_id: str, channel_id: str) -> str:
    raw_messages = fetch_all_messages(gc, team_id, channel_id)
    lines = [line for m in raw_messages if (line := message_to_line(m))]
    lines.sort(key=lambda l: l.created)
    return "\n".join(l.formatted() for l in lines)


def claude_cleanup(transcript: str) -> str:
    from anthropic import Anthropic

    prompt_path = os.path.join(os.path.dirname(__file__), "cleanup_prompt_template.md")
    with open(prompt_path) as f:
        template = f.read()
    instructions = template.split("## Automated / structured input")[1].split("```")[1]
    client = Anthropic(api_key=env("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=8192,
        messages=[{"role": "user", "content": f"{instructions}\n\n---\n{transcript}"}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def chunk_transcript(transcript: str, max_chars: int = MAX_POST_CHARS) -> list[str]:
    if len(transcript) <= max_chars:
        return [transcript]
    lines = transcript.split("\n")
    chunks, current = [], []
    size = 0
    for line in lines:
        if size + len(line) + 1 > max_chars and current:
            chunks.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def post_message(gc: GraphClient, team_id: str, channel_id: str, html_body: str) -> dict:
    return gc.post(
        f"/teams/{team_id}/channels/{channel_id}/messages",
        {"body": {"contentType": "html", "content": html_body}},
    )


def post_transcript(gc: GraphClient, team_id: str, channel_id: str, transcript: str, source_name: str):
    parts = chunk_transcript(transcript)
    posted = []
    for i, part in enumerate(parts, 1):
        header = f"<b>Migrated history from #{source_name}</b>" + (
            f" (part {i}/{len(parts)})" if len(parts) > 1 else ""
        )
        body_html = f"{header}<pre>{html.escape(part)}</pre>"
        result = post_message(gc, team_id, channel_id, body_html)
        posted.append(result)
        print(f"Posted part {i}/{len(parts)}: {result.get('webUrl', result.get('id'))}")
    return posted


def get_files_folder(gc: GraphClient, team_id: str, channel_id: str) -> dict:
    return gc.get(f"/teams/{team_id}/channels/{channel_id}/filesFolder")


def copy_channel_files(gc: GraphClient, source_team: str, source_channel: str,
                        dest_team: str, dest_channel: str, folder_name: str):
    src_folder = get_files_folder(gc, source_team, source_channel)
    dest_folder = get_files_folder(gc, dest_team, dest_channel)
    src_drive_id = src_folder["parentReference"]["driveId"]
    src_item_id = src_folder["id"]
    dest_drive_id = dest_folder["parentReference"]["driveId"]
    dest_item_id = dest_folder["id"]

    resp = gc.post_raw(
        f"/drives/{src_drive_id}/items/{src_item_id}/copy",
        {
            "parentReference": {"driveId": dest_drive_id, "id": dest_item_id},
            "name": folder_name,
        },
    )
    monitor_url = resp.headers.get("Location")
    if not monitor_url:
        print("Copy accepted, no monitor URL returned; check the destination Files tab.")
        return
    print(f"Copy in progress, polling {monitor_url} ...")
    while True:
        status = requests.get(monitor_url).json()
        pct = status.get("percentageComplete", 0)
        print(f"  {pct}% complete (status: {status.get('status')})")
        if status.get("status") in ("completed", "failed"):
            break
        time.sleep(5)


def announce_move(gc: GraphClient, source_team: str, source_channel: str,
                   dest_team: str, dest_channel: str, message: str) -> dict:
    dest = get_channel(gc, dest_team, dest_channel)
    link = dest["webUrl"]
    body_html = f"<p>{html.escape(message)}</p><p><a href='{link}'>{html.escape(dest['displayName'])}</a></p>"
    return post_message(gc, source_team, source_channel, body_html)


def full_import(app_gc: GraphClient, source_team: str, source_channel: str,
                 dest_team: str, dest_channel: str):
    """Native metadata-preserving migration (Mode B). Beta Graph endpoint —
    verify field names against https://learn.microsoft.com/en-us/graph/teams-import-messages
    before running against real data; this is a starting point, not a
    guaranteed-current wire format.
    """
    print("Starting migration mode on destination channel ...")
    app_gc.post(f"/teams/{dest_team}/channels/{dest_channel}/startMigration", {})

    raw_messages = fetch_all_messages(app_gc, source_team, source_channel)
    raw_messages.sort(key=lambda m: m["createdDateTime"])
    print(f"Replaying {len(raw_messages)} messages with original timestamps ...")
    for msg in raw_messages:
        sender = (msg.get("from") or {}).get("user") or {}
        if not sender.get("id"):
            print(f"  skipping message {msg['id']}: no same-tenant sender to attribute to")
            continue
        body = {
            "createdDateTime": msg["createdDateTime"],
            "from": {
                "user": {
                    "id": sender["id"],
                    "displayName": sender.get("displayName"),
                    "userIdentityType": "aadUser",
                }
            },
            "body": msg["body"],
        }
        app_gc.post(f"{GRAPH_BETA}/teams/{dest_team}/channels/{dest_channel}/messages", body)

    print("Completing migration ...")
    app_gc.post(f"/teams/{dest_team}/channels/{dest_channel}/completeMigration", {})
    print("Done. Files/recordings still need the separate 'files' step, and "
          "pinning is still a manual step in the Teams client.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def add_channel_args(p: argparse.ArgumentParser):
    p.add_argument("--source-team", required=True)
    p.add_argument("--source-channel", required=True)
    p.add_argument("--dest-team", required=True)
    p.add_argument("--dest-channel", required=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_files = sub.add_parser("files", help="Copy channel Files (incl. recordings) to the destination")
    add_channel_args(p_files)

    p_transcript = sub.add_parser("transcript", help="Build and post the chat-history transcript")
    add_channel_args(p_transcript)
    p_transcript.add_argument("--use-claude-cleanup", action="store_true")
    p_transcript.add_argument("--dry-run", metavar="OUTPUT_FILE",
                               help="Write the transcript to a file instead of posting it")

    p_announce = sub.add_parser("announce", help="Post the 'we've moved' message in the source channel")
    add_channel_args(p_announce)
    p_announce.add_argument("--moved-message", required=True)

    p_all = sub.add_parser("all", help="Run files + transcript + announce in sequence")
    add_channel_args(p_all)
    p_all.add_argument("--moved-message", required=True)
    p_all.add_argument("--use-claude-cleanup", action="store_true")

    p_full = sub.add_parser("full-import", help="Mode B: native metadata migration (app-only, beta)")
    add_channel_args(p_full)

    args = parser.parse_args()

    if args.command == "full-import":
        gc = GraphClient(get_app_only_token())
        full_import(gc, args.source_team, args.source_channel, args.dest_team, args.dest_channel)
        return

    gc = GraphClient(get_delegated_token())

    if args.command in ("files", "all"):
        source = get_channel(gc, args.source_team, args.source_channel)
        print(f"Copying files from '{source['displayName']}' ...")
        copy_channel_files(gc, args.source_team, args.source_channel,
                            args.dest_team, args.dest_channel,
                            folder_name=f"Migrated from {source['displayName']}")

    if args.command in ("transcript", "all"):
        source = get_channel(gc, args.source_team, args.source_channel)
        print("Fetching and formatting chat history ...")
        transcript = build_transcript(gc, args.source_team, args.source_channel)
        if not transcript:
            print("No messages found (or none with readable text content).")
        elif getattr(args, "use_claude_cleanup", False):
            print("Sending to Claude for a formatting pass ...")
            transcript = claude_cleanup(transcript)

        dry_run = getattr(args, "dry_run", None)
        if dry_run:
            with open(dry_run, "w") as f:
                f.write(transcript)
            print(f"Wrote transcript to {dry_run} (not posted).")
        elif transcript:
            posted = post_transcript(gc, args.dest_team, args.dest_channel, transcript, source["displayName"])
            print("\nReminder: pin the first post above manually in Teams — "
                  "there is no Graph API for pinning channel messages.")

    if args.command in ("announce", "all"):
        result = announce_move(gc, args.source_team, args.source_channel,
                                args.dest_team, args.dest_channel, args.moved_message)
        print(f"\nPosted 'we've moved' message: {result.get('webUrl', result.get('id'))}")
        print("Reminder: pin this post manually in Teams — "
              "there is no Graph API for pinning channel messages.")


if __name__ == "__main__":
    main()
