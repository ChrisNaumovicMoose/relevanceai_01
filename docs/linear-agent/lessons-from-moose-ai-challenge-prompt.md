# Lessons from the Moose AI Challenge Co-pilot prompt

Review of a live, unrelated Moose prompt (the "AI Challenge Co-pilot" — a chat
agent that helps colleagues shape and submit AI use-case ideas to a company
challenge, scoring and writing them to a portfolio table) for anything
transferable to the Linear Work Orchestrator. Different domain, same shape of
problem: a conversational agent that must extract structured facts from loose
human input, show its work, and commit exactly one real artifact per pass
without over-processing the person in front of it.

Four ideas were strong enough to fold directly into `orchestrator-prompt-v2.md`
(now v2.2). A few more are worth having but depend on a decision not yet
made (which chat surface) or are genuine trade-offs the user should weigh in
on rather than have decided for them. And one thing in the Moose prompt is
mostly a lesson about *how to judge prompt length*, not a feature to copy.

## Adopted directly into v2.2

**1. Idempotency on commit.** The Moose prompt has an extremely explicit rule:
once the portfolio tool has returned success for a pass, never call it again
for the same idea, "even if the person repeats the save request or a reply
seemed to go missing" — tell them it's already saved and move on. v2.1 never
addressed this. If a user says "commit" twice, or a message appears to drop
(connection hiccup, retry), nothing stopped the agent from creating the
package twice. Added to the "Committing to Linear" section: once committed,
never re-run the write for the same package; restate the existing links
instead. This is a real gap the Moose prompt exposed by having clearly thought
through repeated/duplicate triggers — worth calling out because it's exactly
the kind of failure that's invisible until a user actually double-taps
"commit" in production.

**2. A "rough beats perfect" one-liner.** Moose states its actual objective
bluntly: "A rough draft with a row counts. A polished idea with no row does
not." v2.1 had the same underlying philosophy (small tickets get a two-line
confirm, "when in doubt, draft small") but never said it as crisply. Added one
sentence to that effect — mostly a phrasing tightening, but a sharp one-liner
here does real work: it's the sentence an implementer reaches for when
deciding how hard to push exploration versus converging.

**3. "Deepening" as a real second pass, with concrete moves.** Moose's
post-save flow doesn't just offer "another idea or polish this one" — it
defines what deepening actually *means*: push it up the autonomy ladder,
offer alternative framings, name a concrete lever, ask for the 10x version,
stress-test the biggest risk. v2.1 had no post-commit continuation logic
at all beyond implicit "keep chatting." Added a "Deepening a committed
package" section with four moves tuned to work-orchestration instead of
use-case ideation (broaden the reach, escalate the motion, name the biggest
risk, look for the bigger win nearby). This is the most genuinely new addition
— v2.1 treated a commit as an endpoint; this treats it as an option to keep
going somewhere useful, and gives the agent concrete things to suggest rather
than a vague "want to keep working on this?"

**4. Silent lookups, cited results.** Moose is explicit: "never announce that
you are looking someone up (call the lookup tool silently, with no text before
it)." v2.1 already asks the agent to cite what it searched, but didn't say
anything about *not* narrating the search as it happens ("let me check
that..."). These aren't in tension once you separate them by timing: don't
narrate *before* the call (pure latency filler), but do cite *after* the
result lands as part of the reply. Tightened the "check the workspace" section
to say both explicitly, since a model left to its own devices tends to default
to "let me look that up" filler that adds nothing.

Also tightened the Voice section with two small, explicit constraints Moose
states as hard rules and v2.1 only implied: never stack two questions in one
message, and give a one-line acknowledgment of what you just heard before
asking the next thing. Cheap to add, and a real anti-pattern worth naming
directly rather than trusting the model to infer it from "ask one question at
a time."

## Validated, not changed

**Hiding computed scores from the person mid-conversation.** This is the
most interesting structural idea in the Moose prompt and it independently
confirms a call already made in `systems-engineering-review.md`. Moose
computes a dollar value, a 1–5 Value/Ease/Confidence score, a Priority number,
and a Proceed/Park/Reject decision — and shows the participant *none* of it.
They see the idea "turned into a score," never the number, never the verdict.
The stated reasons: false precision on a rough estimate reads as authority it
hasn't earned, and showing a mid-conversation verdict undermines the
encouraging tone the whole interaction depends on. That is exactly the
critique v1 got for its confidence scores and exactly why v2.1 already never
shows one. Nothing to change here — worth noting because it's independent
confirmation from a live, shipped prompt rather than just this project's own
theory. The general principle it sharpens: compute what internal governance
needs, route it to the internal/governance surface (for the Linear
orchestrator: the commit comment, not the chat), and never surface a bare
number or verdict to the person mid-conversation.

**Never invent a fact; only a real tool call counts.** Restates hard rules
v2.1 already has (no invented owners/projects/dates, no claimed success
without tool confirmation). No gap, just confirmation the instinct is sound.

## Worth having, not applied — feasibility- or judgment-dependent

**Hidden state markers for a live side panel.** Moose's case snapshot
(`<!--case:{...}-->`) and score marker are HTML comments the wrapping app
parses to drive a live "business case" panel beside the chat, updated
incrementally as fields are captured. This is a genuinely clever pattern —
using an HTML-comment convention means the marker is invisible in any
renderer that turns markdown into HTML, with no reliance on the model's
discretion to hide it. It's the same idea the idempotency addition above
already borrows (a marker that fires only on confirmed tool success), but
Moose goes further with an *incremental* snapshot that builds a UI panel
live. That only pays off if whatever surface hosts this agent can parse and
render such a marker — the native Relevance chat page almost certainly
can't out of the box; a custom Teams/Slack integration built specifically for
this might. Noted in the implementation plan as a stretch enhancement to
revisit once the chat-surface decision is made, with a concrete marker shape
proposed there.

**Quick-reply buttons instead of typed commands.** Moose's chip mechanism
(`<!--chips:[...]-->`) turns every closed-set question — yes/no, pick-one —
into tappable buttons, and explicitly omits them for open text. The review
card's "commit / edit / drop / cancel" menu in v2.1 is currently typed
free text. Buttons would lower friction on exactly the highest-value
interaction (the approval gate) — but, like the panel above, only if the
target chat surface supports them (Slack Block Kit buttons, Teams adaptive
cards, or a custom UI). Also noted in the implementation plan, tied to the
same open chat-surface decision.

**Propose-then-confirm for every inferred field, not just at review.** Moose
interleaves "propose X from the lookup, ask to confirm or correct" throughout
the conversation — sponsor, team size, country — rather than batching
everything into one final card. This is real diligence, but importing it
wholesale would cut directly against the engagement critique's central
finding: uniform ceremony is what kills adoption, and v2.1 deliberately
defers non-blocking assumptions to the review card so small requests stay
fast. The one place Moose's tighter discipline is worth considering on its
own merits is the highest-stakes single field — the named decision-maker on a
Decide ticket, the closest analogue to Moose's sponsor. Whether to add an
inline confirm there (trading one extra turn for lower error risk on the one
field that blocks a commit) is a real call for whoever owns this prompt to
make, not something to decide unilaterally — flagging it here rather than
folding it in.

**Multi-language handling.** Moose's prompt carries substantial machinery for
running the whole conversation in seven languages, with hard-pinned
exceptions (department names, autonomy codes, person names stay in English or
untranslated). Not adopted, and not recommended unless the Linear orchestrator
actually needs to serve non-English speakers — Moose Toys' multi-site
footprint (the language list implies Australia, the US, UK, Mexico, Hong Kong,
mainland China, Vietnam) makes it plausible this eventually matters here too,
but building it in now would be exactly the kind of speculative complexity
Gall's Law says to defer until a real need shows up. Worth asking, not worth
building yet.

## A note on prompt length

The Moose prompt is long — comparable to or longer than v1, the prompt this
whole project's first critique used the IFScale instruction-density findings
to argue *against*. Worth being honest about why that isn't a contradiction.
Length itself was never the problem with v1; *unjustified* length was — v1
spent most of its bulk restating things a capable model already knows ("Validation
is not building the solution"). The Moose prompt's length is overwhelmingly
irreducible specifics a model has no way to infer: exact marker syntax, exact
chip strings in seven languages, a canonical department-name mapping, hard
business numbers (a loaded hourly rate, an adoption-rate ceiling from a named
study), precise tool-calling contracts. That's the right test to apply to any
prompt's length, this project's own included: for each sentence, could a
capable model have produced the same behaviour without being told? If yes,
it's a candidate for deletion regardless of how correct it is. If no, its
length is earning its keep.
