# Customer Name Resolution Strategy — Implementation Summary
## PoC R02 Ready for Production

**Prepared:** July 29, 2026  
**Status:** ✅ **PRODUCTION-READY**  
**Target Platform:** Relevance AI  

---

## What You Have

You now have **three complete, production-ready documents** that specify how to build and deploy a best-in-class customer name resolution system for your stock-availability agent.

### 1. **Full Strategy Document** (`customer-name-resolution-strategy.md`)
**810 lines of comprehensive specification covering:**

- **Problem & Solution** — Why semantic-first matching works better than naive string similarity
- **7-Signal Scoring Architecture**
  - Tier 1 (Semantic): Token overlap (35%), Phonetic matching (25%)
  - Tier 2 (Fallback): Jaro-Winkler (10%), Edit distance (5%)
  - Tier 3 (Validation): Context/region (15%), Sales history (5%), Alias (5%)
- **Preprocessing/Normalization** — 6-step pipeline to handle diacritics, legal suffixes, language variants, tokenization
- **Decision Rules (Deterministic)**
  - AUTO_RESOLVED: score ≥ 0.92 + corroborator + no ties → instant resolution
  - SHORTLIST: score 0.80–0.92 or tied → operator picks from top 3
  - HARD_BLOCK: score < 0.50 → escalate to sales/data team
- **Tie-Breaking Logic** — Priority order (ID → alias → context → history → tokens)
- **Observability** — Mandatory logging, 5 daily KPIs, tuning triggers
- **Rollout Phases** — 4-phase conservative approach (SHORTLIST-only → alias auto-resolve → full auto-resolve → phonetic fast-track)
- **Configuration & Tuning** — All parameters with defaults; adjustable by telemetry
- **Examples** — End-to-end walkthrough of *"La Crote Angalais"* → *"EL CORTE INGLES"* resolution

### 2. **Production-Ready Agent Prompt** (in scratchpad)
**Ready to copy/paste into Relevance AI agent system prompt:**
- Role definition and responsibilities
- All 7 signals explained in plain language
- Combined score formula
- Preprocessing steps
- Deterministic decision rules with JSON examples (AUTO_RESOLVED, SHORTLIST, HARD_BLOCK)
- Input/output contract
- Observability requirements
- Rollout phases and special cases
- Usage workflow

### 3. **Implementation Checklist** (`customer-name-resolution-implementation-checklist.md`)
**343 lines of step-by-step instructions for:**
- Pre-implementation preparation
- Step 1: Create Scoring Tool (normalization, 7 signals, combined score, ranking)
- Step 2: Create Agent in Relevance AI (attach tool, update prompt)
- Step 3: Observability setup (logging, KPI dashboard, alerts)
- Step 4–6: Phase 1–3 rollout (with success criteria for advancing phases)
- Step 7: Ongoing tuning (monthly weights, quarterly reviews)
- Timeline: 6-month path to full production

---

## Why This Approach Is Best

### ✅ **Semantic-First, Not String-Based**
- Token overlap (35%) + phonetic (25%) = 60% of score
- Handles "CROTE" vs "CORTE", "ANGALAIS" vs "INGLES", multi-lingual variants
- Jaro-Winkler is fallback (10%), not primary

### ✅ **Validated by Orthogonal Evidence**
- Corroborator signals (context, history, alias) = 25% of score
- Can't auto-resolve without at least ONE corroborator
- Example: Exact alias match (S_alias=1) + confirmed order company → auto-resolve at 0.94 score

### ✅ **Deterministic & Auditable**
- Every decision logged with full signal breakdown
- Tie-breaking order is fixed (no randomness)
- Reasons for AUTO_RESOLVED, SHORTLIST, or HARD_BLOCK are explicit
- Override telemetry feeds back into weights & alias table

### ✅ **Safe Progressive Rollout**
- Phase 1 (30–90 days): SHORTLIST only — collect data, validate top-ranked precision ≥ 90%
- Phase 2 (30–60 days): Auto-resolve aliases only → measure precision ≥ 99.5%
- Phase 3 (90+ days): Full semantic auto-resolve → maintain precision ≥ 98%
- Phase 4 (optional): Phonetic fast-track → only after 6+ months of proof

### ✅ **Production Observability**
- Daily KPIs: auto-resolve precision, hard block rate, false positives, alias hit rate
- Alerts: threshold breaches trigger immediate action
- Tuning: monthly weights adjustment, quarterly alias table updates
- Evidence: every decision is logged for audit

### ✅ **Easy to Tune**
- All parameters are knobs: thresholds (AUTO_HIGH, AUTO_LOW, HARD_BLOCK), weights (0.35, 0.25, etc.), delta_competitor
- Tuning guided by telemetry, not guesswork
- Language mappings are configurable (ANGALAIS → INGLES, etc.)

---

## Architecture: Two-Tier Implementation

### **Tier 1: Scoring Tool** (Computation)
Handles all deterministic, repeatable logic:
- Normalization (diacritics, legal suffixes, language mappings, tokenization)
- 7 signal computations (token, phonetic, similarity, edit, context, history, alias)
- Combined score formula & ranking
- Output: candidates sorted by score + all signals + provenance

**Implementation:** Transformation (Snowflake SQL) or Custom API  
**Latency target:** < 500ms per request  
**Benefit:** Single source of truth; reusable; auditable

### **Tier 2: Agent** (Decision Orchestration)
Handles human-in-the-loop & policy decisions:
- Receives input, invokes scoring tool
- Applies decision rules: AUTO_RESOLVED / SHORTLIST / HARD_BLOCK
- Presents SHORTLIST to operator (if needed)
- Logs all decisions + operator actions for telemetry
- Returns final resolution or escalation

**Implementation:** Relevance AI agent prompt  
**Integration:** Attach Scoring Tool via `{{_actions.ACTION_ID}}`  
**Benefit:** Clean separation of concerns; easy to test & debug

---

## Quick Start: Next Steps

### This Week (Days 1–5)
1. **Review** the three strategy documents (read full strategy first)
2. **Identify owner** for Scoring Tool development + Agent setup
3. **Gather test cases** (20+ real customer names; known good/bad matches)
4. **Confirm data access** (DIM_JDE_ADDRESS_BOOK, FCT_JDE_SALES_ORDER_DETAIL, Snowflake credentials)

### Next Week (Days 6–12)
5. **Implement Scoring Tool** (Transformation or API)
   - Normalization function
   - 7 signal computations
   - Combined score formula
   - Test with 100+ examples; verify latency
6. **Create Agent in Relevance AI**
   - Use provided system prompt (copy/paste)
   - Attach scoring tool
   - Update prompt with real `action_id`
   - Test draft mode (SHORTLIST output)

### Week 3+ (Days 13+)
7. **Set up observability** (logging, dashboard, alerts)
8. **Phase 1 production rollout** (SHORTLIST-only; 30–90 days)
9. **Collect telemetry** & validate success criteria
10. **Phase 2 rollout** (when Phase 1 success criteria met)
11. **Ongoing tuning** (monthly weights, quarterly reviews)

---

## Files & Locations

| File | Purpose | Lines | Status |
| --- | --- | --- | --- |
| `docs/customer-name-resolution-strategy.md` | Full specification | 810 | ✅ Committed |
| `docs/customer-name-resolution-implementation-checklist.md` | Step-by-step checklist | 343 | ✅ Committed |
| `docs/IMPLEMENTATION-SUMMARY.md` | This file (overview) | — | ✅ Committed |
| Agent Prompt (in scratchpad) | Copy/paste into Relevance AI | 450 | Ready to use |

---

## Key Success Metrics (Phase 1)

| Metric | Target | When |
| --- | --- | --- |
| Top-ranked candidate confirmed by operator | ≥ 90% | Weekly review |
| Operator average latency | < 30 sec | Weekly review |
| False positives in top-3 | 0 | Weekly review |
| Data collection period | 30+ days | End of Phase 1 |
| Requests evaluated | ≥ 1,000 | End of Phase 1 |

**Advance to Phase 2 when:** All targets met for 30+ days  
**Revert if:** Any metric falls below target (e.g., precision drops < 90%)

---

## Key Success Metrics (Phase 3, Full Auto-Resolve)

| Metric | Target |
| --- | --- |
| Auto-resolve precision (not overridden) | ≥ 98% |
| Hard block rate | < 5% |
| Shortlist rate | 15–25% |
| Operator average latency (shortlist) | < 30 sec |
| Daily availability | ≥ 99.5% |

---

## Questions & Answers

**Q: Why start with SHORTLIST-only (Phase 1)?**  
A: It validates the ranking is correct before automation. If top-1 candidate is right ≥ 90% of the time, auto-resolve is safe. Low risk, high confidence data collection.

**Q: How do you handle new customers not in the Address Book?**  
A: HARD_BLOCK decision → escalate to sales team. Address Book is source of truth; if customer isn't there, resolution isn't possible. Log for data quality investigation.

**Q: What if two customers have very similar names?**  
A: Tie-breaking logic handles it. If scores are within 0.05 (delta_competitor), both candidates go to SHORTLIST for operator choice. Deterministic, auditable.

**Q: Can I tune the weights later?**  
A: Yes! All weights are parameters. After Phase 1 telemetry, re-weight based on override patterns. Example: if phonetic-only matches have high precision, upgrade S_phonetic from 0.25 → 0.30.

**Q: What about new languages or regions?**  
A: Add language-specific mappings to the configurable lookup table (e.g., Italian variants, German company suffixes). No code changes needed.

**Q: How do I integrate with my stock-availability agent?**  
A: Call this customer-name-resolution agent as a sub-step in your stock-availability workflow. It returns (address_number, confidence, signals). Use address_number for inventory lookup.

**Q: What if performance degrades over time?**  
A: Monitor daily KPIs. If auto-resolve precision drops, investigate: new data type entering system? Address book corruption? Language variant not covered? Then tune weights, update mappings, or lower thresholds temporarily.

---

## Risk Mitigation

| Risk | Mitigation |
| --- | --- |
| **Phonetic variant not in mappings** | Phase 1 data collection captures these; add to `language_mappings` table for Phase 2 |
| **Address book data quality** | Monitor NULL names; create data cleanup tickets if > 2% of records. HARD_BLOCK logs these. |
| **Operator override rate > 10%** | Revert to SHORTLIST-only; retrain weights; investigate root cause (new customer type? region? language?) |
| **Auto-resolve precision drops < 95%** | Automatic alert triggers; revert to Phase 1; analyze false positives to identify signal mismatch |
| **Scoring latency > 500ms** | Consider indexing on normalized names; test with full address book before Phase 3; migrate to API if needed |
| **Alias table doesn't scale** | Phase 1–2 build comprehensive alias table; Phase 3+ maintain quarterly with operator overrides |

---

## Success Looks Like

✅ **Week 12 (End of Phase 1)**
- Scoring Tool is live, latency < 500ms, 0 errors
- Agent is live in SHORTLIST-only mode, top-1 precision ≥ 90%
- Logging is working; 1000+ requests evaluated
- Daily KPI dashboard shows consistent metrics
- No false positives in top-3 candidates

✅ **Month 4–5 (End of Phase 2)**
- Auto-resolve for aliases enabled, precision ≥ 99.5%
- ~20% of requests auto-resolved via alias
- Operator confirms ~30% via SHORTLIST; < 5% HARD_BLOCK
- No regressions in precision from Phase 1

✅ **Month 8+ (End of Phase 3)**
- Full semantic-first auto-resolve live
- ~70–80% of requests auto-resolved (alias + context + history)
- ~15–25% SHORTLIST (human confirmed)
- < 5% HARD_BLOCK (escalated)
- Precision ≥ 98%, stable KPIs, < 2% override rate

✅ **Ongoing (Production)**
- Monthly weight tuning based on override patterns
- Quarterly alias table expansion
- Sub-second latency, 99.5% availability
- Audit trail captures every decision
- Telemetry feeds continuous improvement

---

## Contact & Support

- **Strategy Questions:** Refer to `customer-name-resolution-strategy.md` (section index at top)
- **Implementation Blockers:** Check `customer-name-resolution-implementation-checklist.md` (troubleshooting steps)
- **Relevance AI Integration:** Read agent skill guide: `relevance://skills/managing-relevance-agents/SKILL`
- **Tuning & Threshold Adjustments:** Use KPI dashboard + override logs to guide weights

---

## Version History

| Version | Date | Status | Changes |
| --- | --- | --- | --- |
| 1.0 | 2026-07-29 | Production Ready | Initial specification; all 3 documents complete |

---

**Next step:** Assign implementation ownership and schedule kickoff.  
**Questions?** Review the full strategy doc or implementation checklist before escalating.

✅ **Status: READY TO BUILD**
