# Critique — AI Lab Work Package Orchestrator prompt (v1)

**Verdict:** The design instincts are right — plain-English intake, a mandatory
human-review gate, workspace search before drafting, and package archetypes that
match how the AI Lab actually works. But the prompt as written will produce an
agent that feels like *process*, not *help*. Every conversation is funnelled into
a six-step pipeline, the review card exposes the internal taxonomy the prompt
forbids exposing, and the ceremony is identical whether the user needs one ticket
or twelve. Those are the things that determine whether business users come back.

The rewrite is in `orchestrator-prompt-v2.md` (~1,200 words vs ~4,500). This
document explains what changed and why.

---

## What v1 gets right (and v2 keeps)

- **The human-review gate.** Nothing is written to Linear without approval. This
  is the single most important rule and it survives untouched.
- **The five motions.** Discover / Change / Validate / Decide / Operationalize is
  a genuinely good vocabulary — clear, non-Agile, and it doubles as a
  completeness check ("you built a Change with no Validate — how will anyone
  trust the fix?").
- **The five archetypes.** They encode real institutional knowledge (the OSSS
  PRD→RTM traceability chain, the BAU handover shape). This is the most valuable
  content in the prompt.
- **Workspace intelligence before drafting.** Searching for duplicates, owners,
  and parents before proposing work is exactly right.
- **The worked example.** Concrete examples steer LLM behaviour better than
  rules; v2 keeps one.

---

## Critical issues

### 1. There is no "just answer the question" path

Every conversation in v1 terminates in a Work Package. But four of the nine
intents (*Understand*, *Decide*, *Operate*, *Govern*) frequently need an
**answer**, not tickets. A user asking "does Fusion already do this?" or "who
owns the Analyst Agent?" should get an answer from workspace search in one turn
— not a Discover → Validate → Decide package.

This is the biggest engagement killer. People abandon an assistant that turns
every question into process. The fastest way to earn trust is to *prevent*
unnecessary tickets, which is also v1's own stated mission ("prevent
unstructured business intent from becoming fragmented work") — killing a ticket
that didn't need to exist is a win the prompt never allows.

**v2:** the first routing decision is *answer / small ticket / work package*,
and "offer to create work only if the answer reveals a gap."

### 2. The review card contradicts the prompt's own rules

The governance section says:

> Never expose internal taxonomy to the business user unless asked.

The mandatory review card format says:

> Business Intent: [Intent]
> Motion Mix: [Motion 1] → [Motion 2] → [Motion 3]
> Motion: [Discover / Change / Validate / Decide / Operationalize]

That *is* the internal taxonomy, shown on every package, on every turn. An LLM
given contradictory instructions resolves them unpredictably — sometimes leaking
jargon, sometimes over-suppressing structure. And for the user, "Motion Mix:
Change → Validate" is exactly the kind of insider language that makes a tool
feel like it was built for its builders.

**v2:** motions are explicitly internal ("they never appear as labels in front
of the user"); the review card shows only outcomes, tickets, owners, and open
questions.

### 3. Three overlapping classification layers

v1 classifies every request three times: 9 intents → 5 motions → 5 archetypes
(plus 3 levels). But the intents already carry a "typical motion mix", and the
archetypes already imply both intent and motions. Three layers means three
places to misclassify, three vocabularies to keep consistent, and roughly half
the prompt's word count — for outputs (intent labels, confidence scores,
rationales) that no user ever sees and no downstream step strictly needs.

**v2:** the archetypes absorb the intents' trigger language as "sounds like"
cues, and motions remain as the per-ticket quality check. Two layers, each with
a job: *archetype picks the package shape; motion checks the package is
complete.* The 9-intent layer is deleted with no loss of routing power — its
trigger phrases live on inside the archetypes.

### 4. Ceremony doesn't scale down

A "Lightweight" package (possibly one ticket) travels the same six-step
pipeline and the same full review card as a Strategic programme. For the most
common interaction — one small, obvious ticket — the user gets a multi-section
card with intent, motion mix, mandatory flags, and a four-option menu. That's a
tax on exactly the interactions that build the habit of using the agent.

**v2:** ceremony is priced by size. Single ticket → two-to-three-line confirm.
Standard package → review card. Strategic → review card plus explicit decision
gates and a named sponsor. The approval gate applies at every size; only the
formatting shrinks.

### 5. Pseudo-precise confidence scores

"Confidence score from 0.00 to 1.00... if below 0.70, ask one clarifying
question." LLMs do not produce calibrated probabilities; the number will be
theatre, and the 0.70 threshold will fire arbitrarily. Meanwhile the hard cap —
"do not ask more than one clarifying question" — is brittle in the other
direction: if the user's answer surfaces a new ambiguity, the agent must now
guess.

**v2:** replaces scores with a behavioural rule that exploits the review gate:
*one question at a time, only when the answer would change what you build;
otherwise make a sensible assumption, state it, and let review catch it.* The
review card is already the safety net — upfront interrogation can be minimal.

### 6. Chat is not a pipeline

"You operate through this sequence" describes a linear pipeline, then the
"Response Modes" section retrofits four modes to cope with the fact that
conversations loop, jump, and restart. The two framings compete. Real sessions
look like: question → answer → "ok make that a ticket" → edit → commit →
"actually who owns the other thing?"

**v2:** one short "How a conversation goes" section with three entry points and
a natural edit loop. The modes section is deleted; the behaviour it described
falls out of the routing.

---

## Structural issues

### 7. Customer-specific content is baked into the engine

OSSS, TrendHunter, Marketing Copy Knowledge Book, Analyst Agent, Pre-Sales, and
the PRD/RTM convention appear throughout Steps 3–4. When the workspace evolves
(new programme, renamed project), someone must hunt through a 4,500-word prompt.

**v2:** a clearly-marked **Workspace notes** appendix ("edit this section as the
workspace evolves") holds all workspace-specific facts. The engine above it is
reusable across teams and clients.

### 8. The internal JSON schema will leak into chat

"Use this internal structure before producing the review card" asks the model to
generate a large JSON object it must then hide. In chat deployments this
reliably leaks into visible output, and it burns tokens re-stating what the
review card already contains. It also drifted from its own spec: Step 3 outputs
`recommended_work_package_archetype` and `dependencies`; the schema calls them
`archetype_match` and omits `dependencies` entirely.

**v2:** deleted. The review card *is* the structured artefact; the model doesn't
need a scratchpad format mandated in prose.

### 9. "Never create a Task without an owner" deadlocks intake

Often nobody knows the owner yet — that's normal at intake. As written, the rule
either blocks the commit or pressures the model to invent an assignee (the worse
failure). **v2:** never *invent* an owner; unassigned is allowed but must appear
as an open question on the review card, and the one hard case is kept — a Decide
ticket always needs a named decision-maker.

### 10. No mid-commit failure handling

Step 6 creates a parent, N children, dependencies, links, and a comment — any of
which can fail via the Linear API. v1 says nothing about partial state, so the
model will improvise (typically by reporting success). **v2:** "If anything
fails mid-commit, say exactly what was and wasn't created — never pretend a
partial commit succeeded."

### 11. Internal inconsistencies (smaller, but they erode instruction-following)

- The worked example assigns **two primary intents** ("Improve Something / Fix
  Something") — violating Step 1's "one primary Business Intent" on the prompt's
  own showcase.
- "Never commit **multi-ticket** work without human review" implies single
  tickets might skip review, while Step 6 requires approval for everything.
  v2 makes the gate universal and unambiguous.
- Step 3's required search list includes "PRD / RTM / test / implementation
  chains" — internal jargon inside the supposedly business-language engine;
  moved to Workspace notes.
- Unbounded pre-drafting search ("search... any available enterprise context")
  costs latency on every request. v2: "check the obvious places, don't boil the
  ocean; say what you checked."

### 12. No voice

v1 specifies structure exhaustively and personality not at all. Engagement with
a chat agent is substantially determined by tone, brevity, and whether it leads
with the useful thing. **v2** adds a four-line Voice section: warm, brief,
concrete; mirror the user's words; lead with the useful thing, not the process.

---

## Why shorter is also more effective (not just more elegant)

System-prompt attention is a budget. Instructions compete; a 4,500-word prompt
with three taxonomies, "what it is not" lists, and duplicated rules dilutes
compliance with the rules that actually matter (the approval gate, no invented
owners, duplicate surfacing). Most of v1's bulk teaches a capable model things
it already knows ("Validation is not building the solution"). v2 spends its
budget on the things a model *can't* infer: the archetype chains, the workspace
conventions, the review-card shape, and the hard rules.

Rule of thumb applied throughout: **specify behaviour the model can't guess;
delete definitions of things it already understands.**

---

## Suggested success measures once deployed

Worth instrumenting, since "users engage more" is the stated goal:

1. **Answer-only sessions** — questions resolved with zero tickets created
   (should be a healthy share; v1 would force this to ~0).
2. **Time / turns to first draft** — target: draft on the first or second turn.
3. **Edit rate at review** — high editing means drafts miss; zero editing may
   mean users rubber-stamp without reading.
4. **Commit rate and repeat usage** — packages approved, and users returning
   within two weeks.
5. **Duplicate catches** — times the agent surfaced existing work instead of
   creating new work. Report these; they're the trust builder.
