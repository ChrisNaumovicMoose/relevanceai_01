# Feasibility: "Forward / Add-Attendee" for Create Calendar Event

Agent: **Post-Call Sales Assistant** (Nate) — `agent_id 1912e5c0-db1f-4a98-bdf2-2f7dbb6438cb`
Tool in scope: **Post-Call Sales: Create Calendar Event** — `studio_id 7404ad12-a57b-4349-acc5-4fc0de9f3d13`

## The problem this solves

Today, `Post-Call Sales: Create Calendar Event` wraps Microsoft Graph
`POST /v1.0/me/events` and always creates a no-attendee event on a single
mailbox (whichever `oauth` account is passed). The system prompt's routing
logic (step 7a) already tries to send an internal action-owner's reminder to
*their own* calendar, but only succeeds if that owner is in the
`rep_outlook_oauth` knowledge table with `calendar-read-write` scope. Two
observed real cases fell through:

- **Jesse Peck** (Pinterest) — not in `rep_outlook_oauth` at all, so the rep
  summary email fell back to a default sender and the customer-draft tool
  (which strictly requires a valid OAuth account) couldn't run.
- **Natasha Karamanis** (Tomy/Takara Tomy) — action owner not in
  `rep_outlook_oauth`, so her `REMINDER` event silently landed on **Sunny
  Lee's** calendar instead, with only a subject-line tag
  (`REMINDER [Owner: Natasha Karamanis, not in rep_outlook_oauth KT]: ...`)
  to flag the gap. Confirmed against the live KT — it currently holds exactly
  three reps (Sunny Lee, Chris Naumovic, Tamara Stewart); Natasha and Jesse
  are both absent.

The proposal: give the tool an optional `attendees` parameter so that, in the
"owner not in KT" and "owner in KT but missing scope" fallback branches, the
event still lands on the rep's calendar (unchanged) **but the actual owner is
CC'd as an attendee**, so Outlook/Graph sends them a real invite without
requiring write access to their mailbox.

## Verdict: technically feasible, low effort, no new permissions required

I pulled the live tool definition and the `rep_outlook_oauth` KT to check
this against how the tool is actually built (not just how it's described):

- The tool is three transformation steps: `build_payload` (Python — builds
  the Graph JSON body), `create_event` (`microsoft_api_call` →
  `POST /v1.0/me/events` with `oauth_account_id: {{oauth}}`), `finalize`
  (Python — shapes the response). `build_payload` currently constructs
  `subject`, `body`, `start`, `end`, `showAs`, `isReminderOn`,
  `reminderMinutesBeforeStart`, `isAllDay` — there is no `attendees` key in
  the payload today, and no attendee-shaped param in `params_schema` to feed
  one.
- The `oauth` param's `integration_requirements` show `provider: microsoft`
  with an empty `permissions` array at the tool-metadata level — the actual
  scope enforcement lives in the rep's OAuth grant, tracked informally via
  the KT's free-text `scopes_granted` column (`email-read-write`,
  `calendar-read-write`).
- **Key point for feasibility**: Microsoft Graph's `attendees` array is a
  standard field on the `event` resource, and adding attendees to an event
  you create on **your own** calendar only requires the same
  `Calendars.ReadWrite` delegated permission the tool already uses to create
  the event at all. Graph handles sending the invite email itself. No
  additional scope, no admin consent, no directory write access to the
  attendee's own mailbox is needed — this sidesteps the tenant-level Graph
  permission blocker that the separate "directory-first" idea runs into.

So this really is the lighter-touch option: it reuses a grant Sunny Lee (or
whichever rep is authorised) already has.

## What would actually need to change

Three small, contained edits — one tool, one prompt, no new infrastructure:

1. **Tool schema** (`Create Calendar Event`, `params_schema`): add an
   optional `attendees` param, e.g. a JSON array of `{name, email}` or a
   simple comma-separated email list — whichever is easier to keep the LLM
   from malforming.
2. **`build_payload` step**: if `attendees` is non-empty, map it into Graph's
   expected shape and merge into `payload`:
   ```python
   payload['attendees'] = [
       {'emailAddress': {'address': a['email'], 'name': a.get('name', '')},
        'type': 'required'}
       for a in attendees_v
   ]
   ```
   A handful of lines, following the same defensive-parsing pattern already
   used for the other optional params in that step.
3. **Agent system prompt, step 7a** (owner-routing rules): in the two
   fallback sub-cases —
   - *KT match but missing `calendar-read-write`* → keep `oauth =
     resolved_oauth`, add `attendees = [{owner email, owner name}]`.
   - *No KT match* → keep `oauth = resolved_oauth`, add `attendees =
     [{owner email, owner name}]` using the same derived-email logic the
     prompt already performs for the per-owner KT search (`first.last@moosetoys.com`).
   - *Owner is customer-side* → **no change** — do not add an external
     attendee here; keep it as the existing `TO DO: Chase {customer person}`
     event on the rep's own calendar only, to avoid an unintended customer
     invite.
   - *Owner is the rep themself* → unchanged, no attendee needed.

Updated routing table:

| Owner | Today | Proposed |
|---|---|---|
| The rep | Rep's calendar, no attendee | Unchanged |
| Other Moose person, in KT with `calendar-read-write` | Owner's calendar | Unchanged |
| Other Moose person, in KT but missing scope | Rep's calendar, tagged subject only | Rep's calendar **+ owner added as attendee** |
| Other Moose person, not in KT | Rep's calendar, tagged subject only | Rep's calendar **+ owner added as attendee** |
| Customer-side | Rep's calendar (`TO DO: Chase ...`) | Unchanged — no external attendee |

Net effect for the Natasha Karamanis case: the reminder still lives on
Sunny's calendar as the system of record, but Natasha now receives an actual
Outlook invite instead of the rep having to notice the subject tag and
manually forward it.

## Trade-offs the tool owner should decide, not something I'd want to decide for Moose

- **This sends a real, live calendar invite automatically.** The tool's
  `action_behaviour` is currently `never-ask` (fully autonomous, no
  human-in-the-loop confirmation). Adding auto-invite behaviour compounds
  that — an owner could receive an invite for an action they haven't agreed
  to, generated purely from the agent's read of a transcript. Worth
  considering as an **opt-in flag** (e.g. `auto_invite_owner: bool`,
  default `false`) rather than always-on, at least initially.
  Alternatively, keep `never-ask` for the rep-owned path and require
  explicit approval specifically for the owner-attendee branch.
- **Guardrail against external invites is a must, not a nice-to-have.** The
  routing table above already excludes customer-side owners from
  `attendees`, but this needs to be enforced narrowly (only ever populate
  `attendees` from the internal-Moose-owner branch) so a prompt
  mis-classification can't accidentally invite a customer to an internal
  reminder.
- **Email accuracy risk.** The derived `first.last@moosetoys.com` pattern is
  a guess, same one already used for the KT search — if the guess is wrong,
  the invite silently goes to a non-existent or wrong mailbox. Low risk
  (Graph will bounce/NDR on an invalid address, it won't misdirect to a real
  wrong person unless the guessed address happens to exist), but worth a
  directory-lookup validation step if this gets built.
- **Complements, doesn't replace, the directory-first idea.** That idea (KT
  lookup → direct Graph write to the owner's own mailbox) still gives a
  cleaner result when tenant-level Graph permissions are eventually approved.
  This proposal is the interim/lighter-weight fix that works within the
  rep's existing grant.

## Effort estimate

Small. One tool edit (schema + ~10 lines of Python in `build_payload`), one
system-prompt edit (step 7a routing rules, `attendees` derivation reusing
existing owner-email logic), no new OAuth/Graph permission requests, no KT
schema change. The main open item is a product decision (opt-in flag vs.
always-on) rather than a technical blocker.

## Caveat

This is an investigation and spec only — I haven't modified the live
`Create Calendar Event` tool or the agent's system prompt. Building this is
a configuration change for whoever owns the Relevance AI project setup for
the Post-Call Sales Assistant.
