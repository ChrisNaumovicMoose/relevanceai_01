# Implementing orchestrator-prompt-v2.md (v2.2) in Relevance AI

How to turn the v2.2 prompt into a running Relevance agent, mapped onto
Relevance's actual primitives (agents, tools, evals, knowledge, triggers).
Grounded in the two prior critiques — in particular, this plan is where
Finding 2 ("policy where mechanism belongs") and Finding 8 ("no feedback
loop") from `systems-engineering-review.md` get turned into real config
instead of prose rules.

**Environment check performed:** Linear is already a connected OAuth
integration in this Relevance project (`list_integration_providers` shows
`linear`, 1 connected account). No usable pre-built Linear tools exist in the
public library — the two that show up (`Add Linear Tickets to Knowledge Base`,
`Retrieve Recent Tickets from Linear`) are read-only samples authenticated with
a raw pasted API key, not the connected OAuth account, and don't cover search,
create, comment, or linking. **Custom tools need to be built** — see below.

---

## Architecture decision: one agent, not a workforce

Relevance offers both single agents and multi-agent **workforces** (graphs of
agents connected by forced-handover or tool-call edges). The workforce
guidance is explicit: use agents for distinct reasoning roles, tools for
integrations, and a graph when steps need genuine separation (different
prompts, different evals, no back-and-forth between them).

v2.2's flow — search, draft, converse with the user about edits, commit — is
**one continuous conversation**, not distinct roles. A workforce would force
that conversation through rigid handover edges, which reintroduces the exact
problem Finding 1 raised against v1: a workflow's rigidity applied somewhere
that needs to stay conversational (the user interrupting to ask something
unrelated, edit a draft, or re-open review after committing part of a
package). Recommendation: **a single agent**, and get the "search always
happens before drafting" guarantee from tool design and eval checks (below),
not from a graph.

Revisit this only if a future need is genuinely separable — e.g., a nightly
"scan Linear for stale packages" job is a good workforce/scheduled-trigger
candidate later, because it has no human in the loop and no conversation to
protect.

## Tool surface — the actual enforcement layer

### Existing agent found in Garage_56: "Linear Assistant" — mine it, don't reuse it live

There's already a **"Linear Assistant"** agent in this project
(`044e8790-9bd9-4629-91d6-f7c29eea4b50`, published, no evals or dashboard).
Inspected it directly: `claude-sonnet-4-6`, temp 0, one attached tool called
"Linear (API key) API Call" set to `action_behaviour: never-ask`. That tool is
a generic "make an authorized POST to Linear's GraphQL endpoint" wrapper — the
model writes the raw query or mutation itself. The agent's ~8,200-character
system prompt (fetching the full config returns 900K+ characters because
`{{linear_docs}}` and `{{linear_schema}}` — the entire Linear API docs and
GraphQL schema — are substituted in at runtime) is genuinely well-tuned: it
has hard-won, tested patterns for exactly the operations this plan needs —
`teamId` is required for `issueCreate` and has to be fetched via the project's
`teams` connection first, issue keys (`CHA-558`) must be resolved to internal
UUIDs before any mutation, Linear's priority field is an integer 0–4 (2 =
High, not 1), cycle selection means comparing dates against `startsAt`/`endsAt`
since the API doesn't return "the current one," and a documented list of
GraphQL schema gotchas (`teams` not `team` on a project, don't filter
`ProjectMilestone` by `project`, etc.).

**Why it can't just be wired in — as a workforce subagent or merged straight
into the orchestrator — for the write path:** it has exactly one tool, and
that tool is generic. Relevance's `action_behaviour` gates a whole attached
tool, not a specific GraphQL operation inside a call to that tool — there's no
way for the platform to tell "this call is a read" from "this call is a
mutation" when both go through the same "make an authorized request" action.
So no matter how this agent gets composed in — subagent hand-off, or copying
its tool onto our orchestrator directly — the model remains equally free to
run `mutation { issueCreate(...) }` through it with zero approval gate, which
silently breaks the orchestrator's first hard rule ("nothing written without
approval, no exceptions") regardless of what the orchestrator's own prompt
says. Editing the existing tool to `always-ask` doesn't fix this either — it
just moves the friction onto reads instead, which were supposed to be free.
This is a structural property of a generic single-tool wrapper, not something
prompt wording could patch around.

(This is a related but distinct question from the remote-MCP one below:
Linear's actual remote MCP server exposes many genuinely distinct, separately-
named tools — `list_issues`, `save_issue`, `save_comment`, etc. — not one
generic passthrough, so it may still turn out to support per-tool
`action_behaviour` where this homegrown agent structurally cannot. The
dashboard check below is still worth doing for that reason.)

**Decision:** don't reuse "Linear Assistant" live. Build the dedicated,
individually-gated tools as planned, but write them using the GraphQL patterns
above as a tested starting point instead of rediscovering them — real time
saved, since those specific gotchas (`teamId` requirement, connection/`nodes`
pagination, priority integer mapping, key-to-UUID resolution before mutating)
would otherwise be exactly the kind of thing you only learn by hitting the API
and reading the error. Worth a quick separate check: this tool authenticates
with a Linear **API key** (shared credential, all actions attributed to one
key), while the project also has a proper OAuth-connected `linear` account —
OAuth ties each action to a real identity in Linear's own audit log, which is
probably the better choice for a production write path; flagging as a
decision, not assuming it.

### Open question first: remote MCP vs. custom tools

Linear ships its own official hosted remote MCP server
(`https://mcp.linear.app/mcp`, OAuth-based — [Linear's MCP docs](https://linear.app/docs/mcp)).
This Claude Code session has a Linear MCP connection itself (the `mcp__Linear__*`
tools visible throughout this conversation — list_issues, get_issue, save_issue,
save_comment, save_project, list_teams, and more), almost certainly backed by
that same official server. Relevance agents can connect to any remote MCP
server too, via a `remote_mcp_configs` field that enables a phantom tool called
`mcp_remote_tool_call` — so in principle, the agent we're building could get
Linear's whole official toolset for free instead of anyone hand-building the
tools listed below.

Two things stand in the way of just doing that:

1. **`remote_mcp_configs` is a blocked field** — it can't be set via
   `relevance_update_agent`/`relevance_create_agent` (the API this plan uses
   throughout). It's dashboard-only, so this is a step a human has to do in
   the Relevance UI; it can't be scripted end-to-end the way the rest of this
   plan is.
2. **Unconfirmed: does it preserve per-operation permissioning?** This whole
   plan's actual safety mechanism (Finding 2) is that reads and writes get
   different `action_behaviour` settings, and admin operations aren't attached
   at all. That works because each hand-built tool below is its own Relevance
   action with its own permission. A remote MCP connection may or may not
   expose that same granularity — if Linear's whole MCP surface shows up as
   one `mcp_remote_tool_call` action with a single `action_behaviour`, then
   connecting it wholesale means either every write goes through unchecked
   (never-ask covering creates too) or every read requires approval too
   (dead weight on the one thing that was supposed to be frictionless). Not
   verified either way yet.

**Before building anything, verify this empirically rather than guess:** add
the Linear remote MCP connection to a throwaway test agent in the Garage_56
dashboard (Agent settings → remote MCP / integrations → server URL
`https://mcp.linear.app/mcp`, then the OAuth prompt), and then call
`relevance_get_agent_tools` on that test agent — it'll show whether Linear's
operations land as one bundled action or many individually-addressable ones.
That one check decides the shape of everything below:

- **If individually addressable:** skip building custom tools entirely, wire
  the review/write split via `action_behaviour` per remote-MCP action instead.
- **If bundled into one action:** a clean middle path is to use the remote MCP
  connection for reads only (bundling is harmless there — everything's
  `never-ask` anyway) and hand-build only the four write tools below, where
  granular `always-ask` gating is the point. That halves the build effort
  versus building all eight from scratch, while keeping the safety property
  that actually matters.
- **If neither works cleanly:** fall back to the original plan — build all
  eight as custom tools. The Linear MCP tool schemas visible in this session
  (`save_issue`, `save_comment`, `save_project`, `list_issues`, etc.) are now a
  verified reference for exactly what fields and behavior to replicate,
  instead of reverse-engineering Linear's GraphQL schema from scratch.

The rest of this section describes the fallback (fully custom) version; treat
it as provisional until the dashboard check above resolves which path we're on.

Per Finding 2: least-privilege tool scoping is the mechanism-level version of
several v1/v2.2 prose rules. Build these as custom tools (Settings →
`relevance_create_tool` / `relevance_create_tool_from_transformation`, backed
by Linear's GraphQL API using the connected `linear` OAuth account, not a
pasted API key):

**Read tools — `action_behaviour: never-ask`:**
- Search issues (by text / project / label)
- Search projects
- Get issue / get project (for citing IDs in the review card)
- List users (for owner-matching against workspace signals)

**Write tools — `action_behaviour: always-ask`:**
- Create issue
- Create project
- Add comment
- Create issue relation (dependency link)

**Deliberately not built at all:** update workflow states, manage
teams/labels, any admin/config endpoint. This is Finding 2's core move — "never
touch workflow configuration" stops being a prompt rule the model might forget
under instruction-density pressure (per the IFScale finding) and becomes a
tool the agent literally does not hold. Delete the corresponding prose rule
from the prompt once the tool surface enforces it — don't keep both; the
Anthropic guidance on agent-computer interface treats the tool surface as the
primary lever, and a redundant prose rule just spends attention budget for no
additional safety.

`always-ask` is the correct blunt default for launch (matches v2.2's
"nothing written without approval, no exceptions"). `relevance_update_agent_action`
also exposes `conditional_approval_rules` per attached tool — worth returning
to once there's usage data, to encode v2.2's size-scaled ceremony (e.g.
auto-approve a single-issue create under some condition, always ask above it)
as platform config rather than prompt instruction. Not needed for the MVP;
don't add it speculatively (Gall's Law — evolve toward it once real drafts
show the pattern is safe).

## Agent settings beyond the prompt

- **`thinking_tool: { enabled: true }`** — gives the agent a real scratchpad
  for the "self-check before showing any draft" step in v2.2 (verify every
  Decide ticket has a decider, every dependency resolves, nothing duplicates
  a cited issue, nothing's invented). This replaces v1's internal JSON
  reasoning schema with the platform's actual mechanism for hidden
  reasoning — no risk of the JSON leaking into chat output, no drift between
  a hand-specified schema and what the model actually produces.
- **`autonomy_limit` + `autonomy_limit_behaviour: "ask-for-approval"`** — caps
  runaway tool-call loops within a single turn and forces a check-in rather
  than silently running long. Direct mitigation for the "no mid-commit
  failure handling" gap identified in the first-pass critique.
- **Memory: skip for the MVP.** Nothing in v2.2 requires persistence across
  conversations yet. Adding it now would be exactly the kind of complexity
  Gall's Law says to defer until a concrete need shows up (e.g., "remember
  this requester's usual project" after real usage shows it'd help).
- **Knowledge set for the "Workspace notes" appendix.** v2.2 already
  marks that section "edit this section as the workspace evolves" — put it
  in a Relevance Knowledge Set instead of the system prompt. This is the
  platform-native version of the shearing-layers separation from the
  systems-engineering review: the AI Lab can update programme names, default
  projects, and sponsor mappings without anyone touching prompt text. The
  reusable engine (motions, archetypes, review card, hard rules) stays in the
  system prompt; the volatile facts move to Knowledge.

## Writing the prompt itself

Two-pass, per the platform's own requirement (action IDs don't exist until
tools are attached):

1. Create the agent (`relevance_create_agent`) with v2.2's prose as a draft,
   tool-reference lines left as plain text.
2. Attach the built tools (`relevance_attach_tools_to_agent`), fetch their
   `action_id`s (`relevance_get_agent_tools`), then edit the prompt
   (`relevance_edit_agent_system_prompt`) to weave `{{_actions.<id>}}` pills
   inline at each decision point — e.g., where v2.2 says "search Linear before
   drafting" and "only after explicit approval... create the parent, then
   children." Inline pills give the model a real tool-selection cue; prose
   like "use the search tool" doesn't.

No other prompt changes are needed — v2.2's structure (hard rules first,
answer/small-ticket/package routing, archetype escape valve, self-check,
assumptions-first review card) carries over directly.

## Testing before publish (this is where the feedback loop lives)

Finding 8 was that v1 has no feedback loop at all. Relevance's eval system is
the concrete fix — both the pre-publish gate and the post-launch monitor:

**Test set (pre-publish).** Build scenarios that mirror the risks each critique
raised, and simulate every write tool by default (per the evals skill's
default-to-simulate rule) so testing never actually writes to Linear:

- *Answer-only* — "does Fusion already do this?" → check: zero write-tool
  calls (a `tool_usage` check with `operator: at_most, count: 0` on the create
  tools).
- *Small ticket* — one obvious ask → check: compressed confirm, not a full
  review card.
- *The held-stock worked example* — check: search tool called before any
  create-issue call (`tool_usage` with `position: "first"` on the search
  tool is a real, mechanical version of the "always search before drafting"
  invariant — cheaper than a workforce and actually testable).
- *A Decide-shaped request with no named decider* — check: agent asks for a
  decision-maker rather than inventing one or silently proceeding.
- *A duplicate-overlap scenario* (seed a similar existing issue via
  simulation) — check: the duplicate is surfaced before any draft, cited by
  ID.

**Publish gate.** Link this test set to the agent's Evaluate tab → Publish
section with a minimum pass rate. This is the platform's native "block
publish unless evals pass" — from here on, no prompt edit (including future
ones nobody on this thread makes) reaches production without clearing the
same bar. This is the most direct fix available for Finding 8: the system
literally cannot get worse without someone noticing before it ships.

**Performance dashboard (post-publish).** Sample live conversations
(`sample_rate` ~0.1–0.2 to start) against checks such as: no owner/project/date
invented without evidence, a cited duplicate or an explicit "nothing
overlapping" statement, assumptions/open-questions shown before the ticket
list. Review on a weekly cadence initially — this is also the operational
home for the "edit-rate as a vigilance signal" metric from the
systems-engineering review: a sustained near-zero edit rate at review is a
signal the human gate has gone ceremonial, not that the agent has gotten
better.

## Surface-dependent UX enhancements (revisit once the chat surface is chosen)

Two ideas from reviewing a comparable Moose chat-agent prompt (see
`lessons-from-moose-ai-challenge-prompt.md`) are worth having but only pay off
on a surface that supports them — not needed for the MVP, but worth deciding
alongside the chat-surface choice below rather than forgetting about them:

- **A hidden commit-success marker.** v2.2's "Committing to Linear" section
  now says to use one "if the surface can carry a hidden, structured marker."
  Concretely, that would look like an HTML comment appended only in the reply
  immediately after a confirmed successful write, e.g.
  `<!--committed:{"package":"Exclude held stock from availability","issues":["OSSS-142","OSSS-143","OSSS-144"]}-->`
  — invisible in any renderer that turns markdown into HTML, and a hard signal
  a wrapping app or a Teams/Slack integration could key off (post a
  notification, update a tracker, disable a "commit" button). It also gives
  the eval system something cheap and mechanical to check: a test scenario
  can assert the marker never appears unless the create-issue tool actually
  ran and returned success first.
- **Quick-reply buttons on the review card's decision** ("create these /
  change something / drop an item / cancel") instead of typed free text —
  lower friction on the single highest-value interaction, the approval gate.
  Needs button/quick-reply support on the target surface (Slack Block Kit,
  Teams adaptive cards, or a custom UI); the native Relevance chat page is the
  one candidate surface unlikely to support this out of the box.

## Chat interface

Every Relevance agent already has a native hosted chat page (shareable link,
no extra setup) — that's the zero-config way to put this in front of users and
is the recommended starting surface: it needs no OAuth, no trigger config, and
nothing to get wrong before the first pilot conversation. Slack or Teams can be
layered on afterward via `relevance_create_trigger` (`trigger_type: "slack"` or
`"teams"`), which does require an OAuth-connected account for that provider
and a bit more setup. (This repo already has a Teams-migration playbook under
`docs/teams-migration/`, so Teams may be the eventual target — worth
confirming before wiring a trigger, since Slack vs. Teams changes what needs
connecting first.)

## Build sequence

1. Confirm the Linear OAuth account's scopes cover read + issue/comment/relation
   create — and deliberately do **not** request team/workflow-admin scopes.
2. Build the eight custom Linear tools listed above as drafts.
3. Create the agent with the v2.2 prompt as a draft.
4. Attach tools with the action_behaviour split above; enable `thinking_tool`;
   set an `autonomy_limit`.
5. Weave `{{_actions.<id>}}` pills into the prompt (pass 2).
6. Create a Knowledge Set from the "Workspace notes" section; attach it.
7. Build the eval test set (5 scenarios above), simulating all write tools;
   run it and iterate on the prompt until green.
8. Link the test set as a publish gate with a minimum pass rate.
9. Publish.
10. Share the native chat link for a small pilot group first — this is a
    direct response to the very first critique's core risk (uniform ceremony
    and taxonomy leakage killing engagement); watch real conversations before
    opening it further.
11. Create the performance dashboard; review weekly.
12. Once the pilot shows non-zero, non-100% edit rates at review (i.e., the
    gate is doing real work) and duplicate catches are happening, expand
    rollout and consider a Teams/Slack trigger and `conditional_approval_rules`
    for size-scaled ceremony.
