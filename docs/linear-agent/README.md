# Business-User Linear Agent Playbook (Copilot Studio + Teams)

Lets AI Lab business participants raise and maintain their own Linear tickets by
chatting with a Copilot Studio agent in Microsoft Teams, instead of routing everything
through the PM manually. The whole point of the design is that every action the agent
takes runs under the *real business user's own* Linear login — so Linear's existing
per-Project access rights are enforced natively, with no custom permission logic to
build or trust.

This is not a coding project — there's no application code in this repo for it. It's
built entirely in Microsoft Copilot Studio, Power Platform (custom connector + Power
Automate), and Linear's own OAuth-app admin UI. This doc is the playbook for that build.

## What's actually enforceable here (read this first)

| Goal | Achievable? | How |
|---|---|---|
| Business user creates/edits a Linear ticket via natural language in Teams | **Yes** | Copilot Studio topics calling a custom connector to Linear's GraphQL API |
| Action is genuinely attributed to the real business user in Linear, not a bot/shared identity | **Yes** | Linear OAuth app registered with default `actor=user`, connector uses per-user OAuth (see below) |
| Agent only lets a user touch Projects they're already a member of in Linear | **Yes, natively — no custom code** | Power Automate "Run-only users" + "Provided by run-only user" connection binding means every call carries *that user's own* Linear token; Linear's GraphQL API itself filters/rejects based on real ProjectMembership |
| Ticket always has all required attributes before it's created | **Yes** | Deterministic Copilot Studio topic with explicit Question nodes + a confirm-before-write Adaptive Card; never let `CreateIssue` fire on partial input |
| A single shared Linear identity ("the bot") doing everything on everyone's behalf | **Explicitly ruled out** | This is the exact failure mode of the earlier Relevance AI prototype in this tenant (see below) — its Linear tool has a `oauth_account_id` fixed at build time, so every ticket it created was attributed to one shared account regardless of who was actually asking |

If you're tempted to take a shortcut and use one shared Linear API key for the bot to
simplify setup: don't. That silently reintroduces the exact problem this project exists
to remove, and it's the reason the earlier Relevance AI prototype (`Linear Ticket
Creator`, `Ticket Orch`, and the `Linear (API key) API Call` tool) was retired in favor
of this design rather than extended.

## Prerequisites

1. Workspace admin access to `linear.app/settings/api/applications` to register an
   OAuth app (one-time).
2. Power Platform maker access with permission to create a custom connector and Power
   Automate flows, plus access to Power Platform admin center (to configure "Run-only
   users" and inspect Connections during testing).
3. Copilot Studio maker access, with the target agent's channel set to Microsoft Teams.
4. An Entra ID security group containing every business user who should get access —
   this group is the actual enrollment mechanism (add/remove someone from the group
   rather than reconfiguring flows per person).
5. Confirmed, in advance, org-wide + per-team mandatory ticket attributes with the
   actual Linear team leads — different teams can have different labels/workflow
   states, so this isn't a single hardcoded list.
6. Two pilot users with **non-overlapping** Linear Project memberships, needed to
   actually exercise the access-isolation test in the verification section — don't
   skip finding these, a same-membership pilot pair can't prove anything about scoping.

## Step 1 — Register the Linear OAuth application

At `linear.app/settings/api/applications/new`:

- Scopes: `read write issues:create comments:create`. Do not request `admin`.
- Leave `actor` unset (defaults to `actor=user`) so every mutation shows up in Linear as
  made by the real person — do **not** use `actor=app`, which mints a distinct app
  identity and recreates the shared-identity problem.
- Redirect URI: leave this until Step 2 generates it (see the ordering note there).
- Register as an internal/private app (Moose Toys' own workspace only, not Linear's
  public app directory).
- No Linear webhooks are needed anywhere in this design — every interaction is
  user-initiated from Teams, nothing needs to push from Linear.

## Step 2 — Build the Power Platform custom connector

Create one custom connector, e.g. `Linear (User OAuth)`, targeting
`https://api.linear.app/graphql`.

- **Security tab**: Authentication type OAuth 2.0, Identity Provider **Generic Oauth 2**
  (Linear is a third-party IdP — this is not an Entra-ID "On-Behalf-Of" scenario).
  - Authorization URL: `https://linear.app/oauth/authorize`
  - Token URL / Refresh URL: `https://api.linear.app/oauth/token`
  - Scope: `read write issues:create comments:create`
- **Ordering quirk**: saving the connector's Security tab generates the redirect URI
  Power Platform expects Linear to call back to. Create the connector shell first, copy
  that generated redirect URI, go back to Step 1 and paste it into the Linear app
  registration, then come back and paste the Linear app's client id/secret into the
  connector. Confirm the exact generated value live — don't assume it in advance.
- **Actions to define** — each is one named, strongly-typed action wrapping a fixed
  GraphQL query/mutation. Do not expose a generic method/path/body passthrough action;
  that's the anti-pattern the old Relevance tool used, and it's also what would let a
  conversation prompt the bot into an arbitrary mutation instead of one of these:

  | Action | Purpose |
  |---|---|
  | `GetViewer` | who does this token belong to (id/name/email) — used for the one-time consent probe and the identity cross-check |
  | `ListMyTeams` | teams visible to this token's identity |
  | `ListMyProjects` | projects visible to this identity (optionally filtered by team) |
  | `ListWorkflowStates(teamId)` | that team's actual states, for defaulting/closing tickets correctly |
  | `ListLabels(teamId)` | that team's actual labels |
  | `ListTeamMembers(teamId)` | for the assignee picker |
  | `ListMyIssues` | portfolio queries, and matching a natural-language reference to a real ticket |
  | `GetIssueByIdentifier` | resolve e.g. "SHOP-123" |
  | `CreateIssue` (`issueCreate`) | main write path |
  | `UpdateIssue` (`issueUpdate`) | edits, reassignment, and status transitions via `stateId` |
  | `AddComment` (`commentCreate`) | comment-only actions |

  Validate the exact GraphQL input/type names (`IssueCreateInput`, `IssueUpdateInput`,
  etc.) against Linear's live schema while wiring each action — treat names above as
  very likely correct, not guaranteed.

## Step 3 — Power Automate flows with per-user connections (the crux)

This is the one setting that makes real per-user RBAC possible — get it right.

1. Build one flow per action family, triggered by **Power Virtual Agents/Copilot
   Studio trigger (V2)**, so Copilot Studio can call each as an Action. Build/test
   against your own (maker) Linear connection first.
2. On each flow's **Share → Run-only users**: add the Entra security group from the
   prerequisites.
3. For the Linear connector reference on that flow, set **Run-only user binding =
   "Provided by run-only user"** — not "Use this connection (maker's connection)". Do
   this **per flow, per connector reference**; it's easy to miss when you copy a flow to
   make the next one. This is the setting that makes every call run under the real
   business user's own Linear token instead of the maker's.
4. Add a lightweight **"Connect to Linear"** topic that fires proactively on a user's
   very first message, calling `GetViewer` purely to surface the one-time OAuth consent
   prompt in a low-stakes moment rather than mid-ticket-creation.
5. **Before building every flow**, spend a half-day spiking whether Copilot Studio's
   newer "add a custom connector directly as a Tool" path (with its own native per-user
   OAuth) works for one read-only action like `ListMyIssues`. If it does, it may let you
   skip the Power Automate flow layer entirely for simpler actions — worth knowing
   before committing to building a flow per action.

There is no shared/service Linear credential anywhere in this design as a fallback.
Auth failures must fail visibly — see error handling below — never silently retry with
a different identity.

## Step 4 — Copilot Studio topics

Use generative orchestration for intent routing, but keep two things deterministic
(explicit Question nodes, not left to generative auto-fill): mandatory-field
slot-filling and the confirm-before-write gate.

- **Create ticket**: resolve Team → live `ListMyProjects` / `ListWorkflowStates` /
  `ListLabels` for that team (never hardcoded) → slot-fill Title, Purpose, Acceptance
  Criteria (rendered as `- [ ] item` checkboxes), Priority, Assignee (fall back to a
  text note if the person isn't in Linear yet), Due Date, Label(s). This reuses the
  description-template and "assignee not yet in platform" handling already drafted in
  the retired Relevance prototype's `Linear Ticket Creator` system prompt. Then render
  an Adaptive Card confirm step — a Linear-Field→Value mapping table with
  Confirm/Edit/Cancel — before calling `CreateIssue`. After creation, re-fetch the issue
  to confirm the fields actually landed as proposed, then surface the ticket URL. This
  confirm-then-verify discipline mirrors what the retired `Ticket Orch` prototype had
  designed but never had real per-user auth to deploy safely.
- **Update / comment / close**: accept a Linear identifier or a natural description
  (match via `ListMyIssues`, confirm the match with the user before acting); same
  confirm-card gate; state transitions resolved from that team's live
  `ListWorkflowStates`, never a hardcoded state id/name.
- **Portfolio queries** ("what's in my portfolio," "what's overdue"): read-only, no
  confirm gate, `ListMyIssues` filtered/formatted as an Adaptive Card list grouped by
  project. Confirm with the team leads how "blocked" is represented today (label vs.
  relation) before building that specific filter.

Generative auto-extraction across a 7-field, per-team-conditional required schema isn't
proven reliable yet — build the deterministic Question-node path as the default, and
only adopt generative auto-fill later if testing shows it holds up.

## Identity & attribution rules

- Teams/Entra identity (`System.User.*`) is for logging, greeting, and a display
  cross-check only. **Never** branch an authorization decision on it.
- Linear authorization comes exclusively from the user's own delegated OAuth token via
  the per-user connection from Step 3.
- Safety-net cross-check: in the confirm card, compare `GetViewer.email` against
  `System.User.Email`; mismatch → warn and block, don't proceed.
- No-seat fallback: if a Teams user without a Linear login is routed to the bot, the
  OAuth consent itself fails — catch this and point them to request a seat; never fall
  back to an elevated credential on their behalf.
- Log per interaction: Teams user, Linear viewer id/email, action, target
  team/project/issue, success/failure + error code, flow run id. Power Automate's
  default run-history retention (~28–30 days) is short for an audit trail — consider a
  simple Dataverse/SharePoint append log if longer retention matters.

## Error handling

| Condition | Code | Bot behavior |
|---|---|---|
| 401 / invalid_grant (refresh token expired or revoked) | `REAUTH_REQUIRED` | Clear message + reconnect link back to the Connect-to-Linear topic. Never fall back to a shared identity. |
| 403 / Forbidden (valid token, no access to that team/project) | `NOT_A_MEMBER` | Plain "you don't have access to X — ask your Linear admin to add you" message. Never silently retry. |
| Anything else | — | Generic retry message, with the flow run correlation id logged for follow-up. |

## Rollout

1. Finalize mandatory-attribute policy with team leads (prerequisite 5).
2. Build and self-test against your own Linear identity first.
3. Pilot with 2–4 business users with deliberately non-overlapping Project memberships,
   1–2 weeks, PM still available as manual backstop.
4. Spot-check every pilot ticket against the required-attribute bar; target ≥90%
   first-attempt pass before broadening.
5. Fix loop on anything the pilot surfaces.
6. Broaden in waves by adding users to the Entra group — no per-flow reconfiguration.
7. Cut over per team once its users are self-sufficient; PM only intervenes on
   bot-reported auth/permission failures from the log.
8. Put the connector/flows in a proper Power Platform **solution** with shared/team
   ownership, not a single personal maker account, so nothing breaks if the builder
   moves on. Once cutover completes, decommission the Relevance AI prototype agents
   (`Linear Ticket Creator`, `Ticket Orch`) and the `Linear (API key) API Call` tool so
   there's only one ticket-creation path in the tenant.

## Verification checklist (manual — do this before pilot sign-off)

Using two real business users A and B who each belong to at least one Linear Project
the other doesn't:

- [ ] Each connects their own Linear account; Power Platform admin center shows two
      distinct connection records, not one shared connection.
- [ ] As A, "what can I create tickets in?" lists only A's real Project memberships —
      excludes B's exclusive project.
- [ ] As A, explicitly trying to create a ticket in B's exclusive project is rejected
      by Linear's API with the `NOT_A_MEMBER` message — not a silent success. Repeat
      symmetrically for B.
- [ ] A ticket created as A shows "Created by A" in Linear's own web UI — not the PM,
      not a bot/app identity.
- [ ] Rushing ticket creation without a due date/acceptance criteria is blocked by the
      topic, not sent through as nulls.
- [ ] Pressing Cancel on the confirm card writes nothing to Linear (verify in Linear
      directly, not just the bot's own "cancelled" message).
- [ ] Revoking a user's connection in the admin center produces a clear reconnect
      prompt on their next action — not a silent failure or a fallback success.
- [ ] A Teams user with no Linear account gets an explicit "you need a Linear seat"
      message.
- [ ] For a project both A and B belong to, both can see/edit tickets there (proving
      "correctly scoped," not just "maximally restrictive").

The membership-isolation checks above are the load-bearing ones — they're the actual
proof that Project-level RBAC is enforced, not just assumed from documentation.

## Assumptions to verify during build

- Exact Power Platform OAuth redirect URI value and connector/app-registration
  ordering — standard custom-connector pattern, but confirm the live value in-tenant.
- "Run-only user binding: Provided by run-only user" is the current Microsoft label per
  2026-era sources; Microsoft renames Power Automate sharing UI periodically, confirm
  at build time.
- Linear's access-token lifetime (~24h, rotating refresh tokens per an April 2026
  migration) came from a third-party source, not Linear's own docs directly — confirm
  before finalizing silent-refresh vs. re-prompt UX.
- Whether Linear's GraphQL API fully mirrors the app UI's ProjectMembership-based
  visibility for a user-scoped token is the single most load-bearing assumption this
  whole design rests on — this is exactly why the verification checklist above is a
  hard gate, not optional.
