# Customer Name Resolution — Implementation Decisions

**Updated:** July 29, 2026

---

## Decision 1: Language-Specific Mappings — PARKED FOR PHASE 2+

**Date:** July 29, 2026  
**Status:** ✅ **APPROVED** — Parked/Deferred  
**Scope:** Affects: Preprocessing step in Scoring Tool  

### Decision
**Skip language-specific mappings (ANGALAIS → INGLES, CROTE → CORTE, etc.) for Phase 1 implementation.**

Instead, rely on **phonetic matching (SOUNDEX)** to handle linguistic variants.

### Rationale
1. **Phonetic matching is language-agnostic** — SOUNDEX captures phonetic equivalence without explicit mapping
2. **Reduces Phase 1 scope** — No need to curate variant tables upfront
3. **Data-driven Phase 2** — Phase 1 operator overrides reveal actual variants in use; Phase 2 adds mappings based on real telemetry
4. **Simplifies deployment** — One less dependency; easier to test and validate

### Tradeoff
- **Pro:** Faster Phase 1 rollout (weeks vs. weeks+); phonetic handles most cases
- **Con:** May miss exact misspellings (e.g., "CR0TE" with zero → "CORTE"); phonetic less precise than curated mappings

### Phase 2+ Plan
- Analyze Phase 1 operator override logs to identify actual variant patterns
- Build curated `language_mappings` lookup table based on real data
- Add to Scoring Tool with config table `tbl_customer_language_mappings`
- Re-weight signals if needed to leverage exact-match bonus

### Files Affected
- ✅ `customer-name-resolution-strategy.md` — marked as Phase 2+ deferral
- ✅ `customer-name-resolution-implementation-checklist.md` — marked as optional/Phase 2+
- ✅ `IMPLEMENTATION-SUMMARY.md` — noted in FAQ
- ✅ Agent prompt — no changes needed (agent is agnostic to this layer)

### Next Steps
1. Implement Phase 1 without language mappings
2. During Phase 1 (days 30–90), collect operator override patterns
3. At Phase 1 review, identify top-10 variant pairs (e.g., "CROTE" vs "CORTE" overrides)
4. Build mapping table in Phase 2 based on data

---

## Decision 2: Alias Table Strategy — APPROVED

**Date:** July 29, 2026  
**Status:** ✅ **APPROVED**  
**Scope:** Affects: S_alias signal (5% weight)  

### Decision
**Build alias table incrementally**, starting with known brand synonyms, expanding based on Phase 1 operator overrides.

### Implementation
- **Phase 1:** Populate with ~20–50 known aliases (manually curated)
  - Example: "CROTE INGLES" variant → "EL CORTE INGLES"
  - Example: "AMAZONE" → "AMAZON"
- **Phase 2+:** Add variants discovered in Phase 1 override logs
- **Table:** `tbl_customer_aliases` with columns:
  - `canonical_name` (normalized target)
  - `alias_variant` (input pattern)
  - `address_number` (resolution target)

### Tradeoff
- **Pro:** Binary signal (1.0 or 0.0) is highest-confidence, enables Phase 2 alias-only auto-resolve
- **Con:** Requires manual curation; scale depends on domain expertise available

### Files Affected
- ✅ All references to S_alias already documented
- ✅ Implementation checklist includes alias lookup step

---

---

## Decision 3: S_alias Signal — PARKED FOR PHASE 2+

**Date:** July 29, 2026  
**Status:** ✅ **APPROVED** — Parked/Deferred  
**Scope:** Affects: S_alias signal (5% weight), corroborator rules  

### Decision
**Skip S_alias signal entirely for Phase 1 implementation.**

No curated alias table available; defer to Phase 2+ when table is prepared from Phase 1 telemetry.

### Impact on Phase 1
- **Combined score formula:** Remove S_alias term
  ```
  Phase 1: combined_score = 0.35*S_token + 0.25*S_phonetic + 0.10*S_sim + 0.05*S_edit + 0.15*S_context + 0.05*S_history
  (S_alias = 0.0 always)
  ```
- **Corroborator rules:** Remove S_alias = 1 as option
  - Phase 1 corroborators: S_context ≥ 0.75 OR S_history ≥ 0.50 OR S_phonetic ≥ 0.75
  - Phase 2+ corroborators: Add back S_alias = 1
- **SQL template:** Set `S_alias = 0.0` always; remove LEFT JOIN to alias table
- **SQL complexity:** Reduced by ~5 lines

### Rationale
1. **Simplifies Phase 1** — No alias table to curate/maintain
2. **Data-driven Phase 2** — Use Phase 1 operator overrides to build initial alias table
3. **Phonetic handles most cases** — S_phonetic (25% weight) covers variant detection
4. **Lower implementation risk** — Phase 1 focuses on core 6 signals

### Tradeoff
- **Con:** Loss of 5% weight from highest-confidence signal (binary)
- **Pro:** Faster Phase 1; phonetic matching is good fallback

### Phase 2+ Plan
1. Analyze Phase 1 operator override logs
2. Identify operators choosing "alternative" candidates over top-ranked
3. Build alias mappings from these patterns
4. Restore S_alias signal in Phase 2 with real data

---

---

## Decision 4: Mandatory Logging (Audit Trail & Telemetry) — PARKED FOR PHASE 1.5+

**Date:** July 29, 2026  
**Status:** ✅ **APPROVED** — Parked/Deferred  
**Scope:** Affects: Observability infrastructure, KPI dashboard, alert configuration  

### Decision
**Defer comprehensive mandatory logging (every resolution attempt) until Scoring Tool + Agent are live and stable.**

### Rationale
1. **Core system first** — Get scoring + resolution logic working before adding logging infrastructure
2. **Reduced Phase 1 complexity** — No need to build logging infrastructure during agent setup
3. **Simpler testing** — Test resolution accuracy first; logging can be added without changing resolution logic
4. **Phase 1.5 implementation** — After agent is live in SHORTLIST-only mode (1–2 weeks), add logging

### Phase 1 Approach (Minimal, Deferred)
- ✅ Agent **does NOT** log every resolution attempt
- ✅ Agent **does NOT** write to Snowflake logging table
- ✅ Agent **does NOT** track operator overrides
- ❌ No telemetry collection during Phase 1
- ❌ No daily KPI dashboard
- ❌ No precision alerts

### Phase 1.5 Approach (After Agent is Live)
- ✅ Create `tbl_customer_resolution_logs` Snowflake table
- ✅ Create Logging Tool in Relevance AI
- ✅ Integrate logging into agent (one-time update)
- ✅ Collect 30–90 days of telemetry for Phase 2 tuning
- ✅ Build KPI dashboard
- ✅ Set up precision/hard-block alerts

### Phase 2+ Approach
- ✅ Use Phase 1 override telemetry to tune weights
- ✅ Build alias table from operator override patterns
- ✅ Enhanced analytics (deep-dive on false positives)

### Impact
- **Phase 1 (Weeks 1–2):** Build Scoring Tool + Agent. No logging overhead.
- **Phase 1.5 (Week 3–4):** Add logging infrastructure. Agent already live and stable.
- **Phase 2+ (Month 2+):** Use logs to inform tuning decisions.

### Files Affected
- ✅ LOGGING-OBSERVABILITY-GUIDE.md — Mark as Phase 1.5+
- ✅ Implementation checklist — Move logging to "Step 3.5" (after agent is live)
- ✅ IMPLEMENTATION-SUMMARY.md — Clarify logging is deferred
- ✅ DECISIONS.md — Document this decision

---

## Summary: Phase 1 Simplified Scope (Final)

| Feature | Phase 1 | Phase 1.5 | Phase 2+ |
| --- | --- | --- | --- |
| **Language Mappings** | ❌ | ❌ | ✅ Add |
| **S_alias Signal** | ❌ | ❌ | ✅ Add |
| **Mandatory Logging** | ❌ | ✅ Add | ✅ Enhanced |
| **Phonetic Matching** | ✅ SOUNDEX | ✅ Keep | ✅ +DoubleMetaphone |
| **Auto-Resolve** | ❌ SHORTLIST | ❌ SHORTLIST | ✅ Enable |
| **KPI Dashboard** | ❌ | ✅ Build | ✅ Enhanced |

**Phase 1 Implementation (Weeks 1–2):**
- ✅ Scoring Tool (6 signals, Snowflake SQL)
- ✅ Agent Prompt (decision orchestration)
- ✅ Agent + Tool integration
- ❌ Logging infrastructure (deferred to Phase 1.5)

**Phase 1 Testing:**
- ✅ Scoring accuracy (manual spot-checks)
- ✅ Agent decision rules (SHORTLIST-only)
- ✅ Operator UX (SHORTLIST presentation)
- ❌ Telemetry (deferred; not needed for Phase 1 testing)

---

## Implementation Impact

### Scoring Tool (Phase 1)
**Simplified normalization pipeline:**
```
Input → Unicode/diacritics → Uppercase + trim → Legal suffix removal → Tokenize
         (NO language mappings)
```

**Total preprocessing steps:** 5 (instead of 6)

### Agent (No Changes)
Agent prompt is unaffected. Phonetic signal (S_phonetic at 25%) carries the variant handling.

### Testing
**Phase 1 test cases should include:**
- ✅ Exact matches
- ✅ Phonetic variants (CROTE vs CORTE) — will be handled by S_phonetic
- ✅ Legal suffix noise (test with + without S.A., LTD, etc.)
- ✅ Alias matches (from ~20–50 curated list)
- ⚠️ Language variants — will test phonetic matching, add mappings in Phase 2 if needed

---

## Approval

- **Decision Owner:** Implementation Team
- **Stakeholders:** Strategy, Engineering, Operations
- **Approved By:** Product Lead
- **Date:** July 29, 2026

---

**Next Step:** Proceed with Phase 1 implementation without language mappings. Revisit in Phase 2 review.
