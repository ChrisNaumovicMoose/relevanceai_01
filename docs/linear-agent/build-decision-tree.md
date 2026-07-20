# Build decision tree — implementing orchestrator-prompt-v2.1 in Relevance

Visual companion to `relevance-implementation-plan.md`. Each diamond is a
decision point in the proposed build; the two open ones (chat surface,
rollout expansion) are left as forks rather than pre-decided, since they
depend on which chat platform the AI Lab wants first and on real pilot data
that doesn't exist yet.

```mermaid
flowchart TD
    Start(["Implement orchestrator-prompt v2.1 in Relevance"]) --> ArchQ{"Does any part of this need to run without a human conversation in the loop?"}

    ArchQ -- "No — one continuous conversation (search, draft, edit, commit)" --> SingleAgent["Build as ONE agent, not a workforce"]
    ArchQ -- "Yes — e.g. a future nightly duplicate-scan job" --> Workforce["Workforce graph — deferred, not MVP"]

    SingleAgent --> ToolQ{"For each Linear operation the agent needs..."}

    ToolQ -- "Read-only: search / get / list" --> ReadTool["Build tool — action_behaviour: never-ask"]
    ToolQ -- "Creates or modifies data: issue / project / comment / relation" --> WriteTool["Build tool — action_behaviour: always-ask"]
    ToolQ -- "Workflow config / teams / labels / admin" --> NoTool["Do NOT build this tool — enforced by omission, not a prompt rule"]

    ReadTool --> Settings
    WriteTool --> Settings
    NoTool --> Settings

    Settings["Agent settings: thinking_tool on for self-check; autonomy_limit + ask-for-approval; Knowledge Set = workspace notes; memory deferred"] --> Pills["Two-pass wiring: attach tools, fetch action ids, weave action-id pills into the prompt"]

    Pills --> EvalQ{"Eval test set — search-before-draft, answer-only, decider-required, duplicate-surfaced — pass rate meets threshold?"}

    EvalQ -- "No" --> Iterate["Iterate prompt / tool descriptions"] --> EvalQ
    EvalQ -- "Yes" --> Gate["Link test set as publish gate"] --> Publish["Publish agent"]

    Publish --> ChatQ{"Which chat surface for the pilot?"}

    ChatQ -- "Native Relevance chat link — recommended, zero setup" --> Pilot["Pilot with a small group"]
    ChatQ -- "Slack or Teams" --> OAuthTrig["Connect OAuth account + create trigger"] --> Pilot

    Pilot --> Dash["Create performance dashboard — sample_rate ~0.1-0.2, review weekly"]

    Dash --> HealthQ{"Healthy signals? Edit rate neither ~0% nor ~100%; duplicates get caught; no invented owners or dates"}

    HealthQ -- "No" --> Tighten["Tighten prompt / tool descriptions, add a regression eval case"] --> Dash
    HealthQ -- "Yes" --> ExpandQ{"Ready to expand rollout?"}

    ExpandQ -- "Not yet" --> Hold["Hold at pilot, keep monitoring"] --> Dash
    ExpandQ -- "Yes" --> Expand["Expand rollout: add conditional_approval_rules for size-scaled ceremony; add Teams/Slack trigger if not already connected"]
```

## Reading the tree

- **Top fork (architecture)** resolves to a single agent, not a workforce —
  because nothing in v2.1 needs to run without a human in the conversation.
  The workforce branch is kept visible because it's the right call *later*,
  for a genuinely separable job like a scheduled duplicate-scan.
- **Second fork (tool surface)** is where the enforcement actually lives —
  three outcomes per Linear operation, and the third (workflow config / admin)
  is a tool that's simply never built, which is the mechanism-level version
  of "never touch workflow configuration" instead of a prompt rule that
  competes for attention with everything else in the prompt.
- **Eval gate** is a real loop, not a one-way arrow: failing scenarios send
  you back to iterate, and only a passing test set unlocks publish.
- **Chat surface** is left open deliberately — it's a real choice, not
  something to default silently.
- **Bottom loop (post-launch)** doesn't terminate at "expand rollout" — it's
  a monitoring loop that keeps running (dashboard → health check → tighten or
  hold or expand) for as long as the agent is live, which is the concrete
  answer to "the system needs a feedback loop, not a one-shot launch."
