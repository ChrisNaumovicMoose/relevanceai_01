# Systems-Engineering Review — Work Orchestrator prompt & theory

A second-pass critique of the orchestrator design (v1 prompt and its underlying
theory), grounded in systems-engineering principles, cybernetics, human-factors
research on automation, and published research on agentic LLM systems. The
first-pass critique (`prompt-critique.md`) reviewed the prompt as a piece of
writing; this one reviews it as a **system design**.

**Headline findings:**

1. v1 is a *workflow specified as prose inside an agent* — the least reliable of
   the available architectures for the determinism it wants.
2. The design's only hard safety guarantee lives in the prompt, which is the
   softest layer available. Guarantees belong in the tool configuration.
3. The human-review gate — the load-bearing control — is the component the
   design most actively degrades, via approval fatigue. Fifty years of
   automation research says this is the predictable failure.
4. The theory's core move (fixed taxonomies as a variety filter) fights the one
   component that has requisite variety: the model itself.
5. The system has no feedback loop, so it can never get better than its first
   guess.

The parts of the theory that survive contact with the literature — and several
do, strongly — are listed at the end, along with the concrete changes applied.

---

## The frame: the prompt is not the system

Systems engineering's first demand is to draw the boundary correctly. The
deployed system is not a prompt; it is a control loop:

```
user ↔ agent(prompt + model) ↔ tools (Linear MCP) ↔ Linear (system of record)
                 ↑                                        │
                 └────────── feedback (none in v1) ───────┘
```

v1 spends ~4,500 words on one box (the prompt) and near-zero on the other
design surfaces: which tools the agent holds, what they're permitted to do,
what gets measured, and how the design learns. Anthropic's agent-building
guidance calls the tool surface the *agent-computer interface* and rates
crafting it as important as the prompt itself. Several v1 rules exist only
because the tool surface was never designed — see "policy vs mechanism" below.

---

## Finding 1 — A workflow written as an agent (architecture mismatch)

The foundational distinction in Anthropic's *Building Effective Agents*:
**workflows** orchestrate LLM calls through *predefined code paths* (giving
predictability), while **agents** direct their own process (giving
flexibility). You choose based on how well-defined the task is.

v1 wants workflow semantics — a fixed six-stage pipeline with typed outputs per
stage (intent + confidence → motions → workspace report → package → card →
commit), including a JSON contract between "stages." But it implements them as
prose instructions inside a single conversational agent. This is the worst
quadrant: you pay the full specification cost of a workflow and get none of its
enforcement. Nothing outside the model's goodwill guarantees Step 3 runs before
Step 4, that confidence is computed, or that the JSON is produced. The "Response
Modes" section then quietly concedes the pipeline doesn't survive contact with
conversation.

There's also a reliability argument against the pipeline's *depth*. The design
chains three classifications (intent → motion → archetype) in series, and an
error anywhere propagates forward — serial stages multiply failure. Illustrative
math: three 90%-accurate stages compound to ~73% before a human ever sees the
result. One routing decision (archetype) checked by a human review beats three
unverified hops. This matches the empirical failure data: the MAST study of
agentic LLM systems found **specification and design issues are the single
largest failure category (41.8%)** — ambiguous roles, poor decomposition,
over-specified flow — ahead of coordination and verification failures.

**Resolution.** Either move the genuinely fixed parts into actual mechanism
(e.g., a Relevance tool-chain that always runs search-before-draft), or accept
the agent architecture and specify *invariants* rather than *sequence*. v2 does
the latter: "never present a draft without having looked" is an invariant the
model can honor from any conversational state; "Step 3 precedes Step 4" is a
sequence it can't reliably self-enforce.

## Finding 2 — Policy where mechanism belongs

Classic systems principle: **separate policy from mechanism**, and enforce each
at the strongest available layer. A prompt is the *weakest* enforcement layer —
probabilistic, context-sensitive, and (per the instruction-density findings
below) increasingly leaky as it grows.

v1's most critical rules are all prompt-enforced:

| v1 rule (prose) | Stronger layer available |
|---|---|
| "Never commit without review" | Require approval-mode on every Linear *write* tool; read tools stay free. The gate becomes physics, not etiquette. |
| "Never modify workflow configuration / teams / statuses / global settings" | Don't attach those tools at all. A rule about a capability the agent doesn't have is dead weight in the attention budget. |
| "Never change labels... unless explicitly operating in admin mode" | An "admin mode" reachable by conversation is a privilege-escalation path through the *softest* layer. If admin operations are needed, they belong in a separately-provisioned agent, not a mode-switch word. |

This yields a proper **defense-in-depth stack**: least-privilege tool scoping
(hard) → prompt invariants (soft) → human review (oversight) → undo/revert
(recovery) → metrics (feedback). v1 stacks everything on the two middle layers.
Systems-engineering treatments of AI agents make the same point from the
accountability side: agents are provisioned and bounded systems, and the
*provisioner* remains accountable — so the provisioning, not the prompt, is
where the guarantees must live.

**Resolution.** Build-time actions (not prompt text): attach only
`search/list/get` + `create issue/project/comment/link` tools; set write tools
to require approval; do not create an admin mode. Then delete the corresponding
prose rules — each one removed buys compliance on the rules that remain.

## Finding 3 — The review gate will decay into rubber-stamping

The theory's centerpiece is human review before commit. The human-factors
literature is blunt about what happens next. Bainbridge's *Ironies of
Automation* (1983): automating the easy parts leaves humans with a vigilance
task they are poorly suited to. Parasuraman's work on **automation bias**:
humans over-trust automated recommendations, producing *commission errors*
(approving wrong output) and *omission errors* (missing failures) — and the
effect is **attentional, not epistemic**: experts rubber-stamp at similar rates
to novices. The gate doesn't fail by being bypassed; it fails by becoming
ceremonial while everyone believes it's working.

v1 accelerates this decay in three ways:

- **Uniform ceremony.** The same multi-section card for a one-line ticket and a
  twelve-ticket programme trains users that the card is boilerplate. Attention
  is a budget; v1 spends it flat, so none is left where stakes are high.
- **Confidence theatre.** Displaying uncalibrated scores ("confidence: 0.85")
  is exactly the over-trust amplifier the literature warns about — precision
  formatting without precision.
- **Restating the confident parts.** The card layout leads with what the agent
  is sure of (intent, motion mix) and buries what it isn't (open questions,
  assumptions) at the bottom — inverted relative to where human attention adds
  value.

**Resolution.** (a) Scale ceremony to blast radius — v2 already does. (b) Lead
the review card with *assumptions and open questions*, not conclusions — the
human's job is to check exactly the things the agent is least sure of; applied
to v2 in this pass. (c) Treat **edit rate at review** as a *vigilance metric*,
not just a quality metric: a sustained ~0% edit rate means the gate has gone
ceremonial and ceremony should be re-tuned. (d) Longer-term: graduate autonomy
by reversibility (below) so approvals stay rare enough to stay meaningful.

## Finding 4 — Requisite variety: the taxonomy fights the model

Ashby's **Law of Requisite Variety**: a regulator must have at least as much
variety as the disturbances it regulates. Real business requests are a
high-variety stream. v1 interposes a fixed, closed classification (9 intents ×
5 motions × 5 archetypes × 3 levels) between that stream and action — a
deliberate variety *attenuator*. Some attenuation is the whole point (that's
what "structure" is), but a *closed* set with mandatory classification forces
distortion at the edges: requests that fit no archetype get shoehorned into the
nearest one. v1's own worked example already exceeds its taxonomy (two primary
intents where the spec allows one) — the variety deficit showing up on page one.

The irony: the system contains a component with enormous requisite variety —
the LLM itself — and the taxonomy's job should be to *bias* it toward house
patterns, not to *replace* its judgment. And per the Conant-Ashby theorem
("every good regulator of a system must be a model of that system"), the
agent's real regulating model isn't the taxonomy at all — it's the **workspace
intelligence**, the live picture of what work exists. That deserves the
first-class treatment (bounded, fresh, and *citable* — issue IDs the human can
verify), while the taxonomy stays a default library.

**Resolution.** Archetypes as defaults with an explicit escape valve ("none of
these fit → design a bespoke package and say so") — applied to v2. Workspace
findings cited by ID so the human can audit the agent's model — applied to v2.
The human gate itself is *justified* by this analysis: the reviewer is the
variety amplifier of last resort. The theory keeps that piece rightly.

## Finding 5 — Gall's Law: which parts earned their complexity

Gall's Law: *a complex system that works is invariably found to have evolved
from a simple system that worked* — complex systems designed from scratch
don't work and can't be patched into working. Applied to the v1 design, the
test is: **which parts evolved from something real?**

- **The five archetype chains** — evolved. They encode observed practice (the
  OSSS PRD→RTM traceability chain, the BAU handover shape). Gall-compliant;
  keep them.
- **The nine-intent layer, confidence thresholds, JSON reasoning schema, four
  response modes** — designed. No usage ever validated them; they are
  speculative complexity of exactly the kind Gall's Law (and Anthropic's
  "start simple, add complexity only when it demonstrably improves outcomes")
  says to defer.

**Resolution.** Ship the minimal working loop (search → draft → review →
commit) and let traffic tell you what structure to add. Concretely: if
post-launch logs show a recurring request shape the archetypes miss, *that's*
when a sixth archetype earns its place — with evidence.

## Finding 6 — Instruction density is a measured budget, not a style preference

The first critique argued "shorter is more effective" qualitatively. The
quantitative version: the IFScale benchmark measured frontier-model adherence
as instruction count grows — even the best models degrade well before 500
simultaneous instructions (~68% adherence at the extreme), degradation begins
far earlier, and there is a systematic **primacy bias**: earlier instructions
are followed more reliably than later ones.

v1 contains well over a hundred discrete imperatives and format requirements.
Two implications beyond "trim it":

- **Ordering is load-bearing.** v1 places its most critical rule (the approval
  gate) at Step 5–6 and in a "Never" list near the end — the low-adherence
  zone. Hard rules belong at the top. Applied to v2 in this pass: "Hard rules"
  moved to directly under the identity section.
- **Every dead rule taxes the live ones.** Rules about capabilities the agent
  shouldn't have (admin mode, workflow config) don't just add words; they
  consume adherence probability from the rules that matter. Enforce them in
  tool scoping and delete the prose (Finding 2).

## Finding 7 — Fixed HITL is the wrong autonomy model long-term

The autonomy literature distinguishes **human-in-the-loop** (approve every
action), **human-on-the-loop** (act autonomously, human monitors and can
intervene), and full autonomy — and the engineering guidance is to match the
control mode to the action's **reversibility and blast radius**, not to pick
one mode for everything.

v1 hard-codes HITL for every write, forever. That's the correct *launch*
posture, but as a permanent design it guarantees the approval-fatigue failure
of Finding 3 — every trivial action spends the reviewer's finite vigilance.
A graduated map:

| Action | Reversibility | Control mode |
|---|---|---|
| Search / answer questions | read-only | autonomous (no gate) |
| Single issue, established project | trivially reversible | HITL now → HOTL-with-undo once edit rates prove trust |
| Multi-issue package | tedious to unwind | HITL (review card) |
| New project / cross-team / decisions | organizationally visible | HITL + named sponsor |

The enabler is **reversibility as a designed property**: a "revert package"
capability (close and unlink everything just created, in one action) converts
medium-risk actions into recoverable ones, which is what permits lighter
gates. v1 never mentions undo; Linear commits are treated as one-way.

**Resolution.** Keep HITL-everywhere at launch (v2 does). Add package-revert as
a build item. Revisit autonomy per action class once the metrics exist —
which requires Finding 8.

## Finding 8 — Open-loop control: the system cannot learn

Cybernetically, v1 is **open-loop**: it acts, and no signal ever returns to
adjust it. Nothing is logged, measured, or fed back. The Deming/systems dictum
applies — a system without feedback can't improve; it can only repeat its
initial design at scale. This also squares with the operating model's own
claim that "AI Lab owns governance and playbook rules": ownership without
instrumentation is a title, not a function.

The MAST data adds a second reason: **verification failures account for ~21%
of agentic-system failures** — systems that don't check their own output
before handing it over. v1's agent never verifies its draft against its own
rules before presenting it.

**Resolution.** Two loops, one fast and one slow:

- **Fast (per-draft) — self-check before showing any card**: every Decide has
  a named decider; every dependency points at an item in the package; nothing
  duplicates a cited existing issue; every owner traces to evidence. Four
  checks, applied to v2 in this pass.
- **Slow (per-month) — design feedback**: log archetype chosen, edits made at
  review, commit vs abandon, duplicate catches. Review-card *edit patterns*
  are the richest signal available — every edit is the user correcting the
  system's model — and they should flow into the Workspace Notes section (fast
  config layer) and, with evidence, into archetype changes (slow ontology
  layer). Owner: AI Lab, per the operating model.

This also completes the **shearing-layers** separation the first critique
started: config (weekly, workspace notes) / ontology (quarterly, archetypes,
evidence-driven) / policy (rare, hard rules + tool scoping). Each layer changes
at its own rate without destabilizing the others.

---

## What the theory gets right (validated by the same literature)

Fairness requires listing where v1's theory is *confirmed*:

- **The human-review gate itself.** Requisite variety says the human reviewer
  is the variety amplifier for cases the taxonomy and model both miss;
  the HITL literature endorses approval gates for consequential, hard-to-
  reverse actions. The gate is right — it just needs protecting from fatigue
  (Finding 3) and eventual graduation (Finding 7).
- **The archetype library.** Evolved from real work, Gall-compliant, and it
  encodes exactly the institutional knowledge an LLM can't infer. The most
  valuable content in the design.
- **The ownership model.** "Business owns outcomes / agent owns drafting / AI
  Lab owns governance / Linear owns record" is textbook responsibility
  assignment, and it maps cleanly onto the accountability framing in
  systems-engineering treatments of AI agents. It just needs instrumentation
  to make the AI Lab's governance role real (Finding 8).
- **Search-before-draft.** Building the agent's model of the environment
  before acting is Conant-Ashby in practice. Right idea; needed bounding and
  citability, not removal.
- **Plain-language translation as the core value proposition.** Hiding
  structural complexity from the humans who don't need it is good interface
  design; v1's sin was leaking the replacement taxonomy, not the ambition.

## Changes applied in this pass (v2 → v2.1)

1. **Hard rules moved to the top** of the prompt (primacy bias, Finding 6).
2. **Escape valve on archetypes** — explicit "none of these fit → say so and
   design bespoke" path (Finding 4).
3. **Pre-review self-check** — four verification bullets before any draft is
   shown (Finding 8).
4. **Citable workspace intelligence** — found issues referenced by Linear ID
   so the human can audit (Finding 4).
5. **Review card leads with assumptions/open questions** rather than burying
   them (Finding 3).

## Build-time actions (outside the prompt — for the Relevance/Linear config)

- Attach **least-privilege tools only**: Linear search/get/list + issue,
  project, comment, and link creation. No workflow-config, team, status, or
  label-admin tools. Then delete the corresponding prompt rules.
- Set **approval-mode on write tools**; leave read tools free (Finding 2).
- No conversational "admin mode" — separate agent if admin ops are ever needed.
- Build a **package-revert** action (Finding 7).
- Instrument the five metrics from `prompt-critique.md` plus **edit-rate as a
  vigilance signal**; route monthly to AI Lab (Finding 8).

## Sources

- Anthropic — [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)
  (workflows vs agents; simplicity, transparency, agent-computer interface)
- Cemri et al. — [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)
  (MAST failure taxonomy: specification 41.8%, misalignment 36.9%, verification 21.3%)
- Jaroslawicz et al. — [How Many Instructions Can LLMs Follow at Once?](https://arxiv.org/abs/2507.11538)
  (IFScale: density-driven degradation, primacy bias)
- Bainbridge — [Ironies of Automation](https://grokipedia.com/page/ironies_of_automation) (1983; vigilance and the out-of-the-loop problem)
- Parasuraman & Manzey — [Complacency and Bias in Human Use of Automation](https://journals.sagepub.com/doi/10.1177/0018720810376055)
  (automation bias is attentional; experts rubber-stamp too)
- Parasuraman, Sheridan & Wickens — [A Model for Types and Levels of Human Interaction with Automation](https://www.researchgate.net/publication/11596569_A_model_for_types_and_levels_of_human_interaction_with_automation_IEEE_Trans_Syst_Man_Cybern_Part_A_Syst_Hum_303_286-297)
  (levels of automation / HITL–HOTL)
- Ashby — [Law of Requisite Variety](https://www.edge.org/response-detail/27150)
  (regulator variety; with Conant-Ashby: "every good regulator must be a model of the system")
- Zargham — [A Systems Engineering Perspective on AI Agents](https://blog.block.science/systems-engineering-perspective-ai-agents/)
  (agents as provisioned, bounded, accountable systems)
- Gall — *Systemantics* (Gall's Law, via [conikee's summary of requisite variety & system design](https://conikeec.substack.com/p/ashbys-law-of-requisite-variety))
- [A Decoupled Human-in-the-Loop System for Controlled Autonomy in Agentic Workflows](https://arxiv.org/pdf/2604.23049)
  (decoupling approval from execution; controlled autonomy)
