# Customer Name Resolution Agent — Deployment Summary

**Date:** July 29, 2026  
**Status:** ✅ Phase 1 Agent & Scoring Tool Created  
**Platform:** Relevance AI Sandbox (Garage_56 project, region: f1db6c)

---

## Artifacts Created

### 1. Scoring Tool
- **Title:** Customer Name Resolution Scorer
- **Type:** Snowflake Transformation Tool
- **Studio ID:** `5ee25344-8e14-46f1-83af-9f658065bfb3`
- **Action ID:** `ee4768fcfc3c4e5e` (for wiring into agent prompt)
- **Signals:** 6-signal semantic-first scoring (Phase 1)
  - S_token: 35% (token overlap)
  - S_phonetic: 25% (SOUNDEX phonetic matching)
  - S_sim: 10% (Jaro-Winkler similarity)
  - S_edit: 5% (normalized edit distance)
  - S_context: 15% (order company / branch plant match)
  - S_history: 5% (730-day order recency/frequency)
- **Parameters:** customer_name, order_company, branch_plant, sales_region, max_candidates
- **Output:** Ranked candidates with all 6 signal breakdowns + combined_score + provenance
- **Latency:** < 500ms per 100 candidates

**SQL Template:** See `/docs/SCORING-TOOL-SQL.md`

### 2. Agent
- **Name:** Customer Name Resolution Agent
- **Agent ID:** `aaa08007-5c73-4d80-82ff-7dfaa8302c63`
- **Mode:** Phase 1 - SHORTLIST-ONLY
- **URL:** https://app.relevanceai.com/agents/f1db6c/098ae5da-7d30-4b81-94d8-3b63fa1757ae/aaa08007-5c73-4d80-82ff-7dfaa8302c63/edit/instructions
- **Tools Attached:** Customer Name Resolution Scorer (1 tool)
- **System Prompt:** 292 lines, Phase 1 optimized
  - All 6 signals explained
  - Combined score formula (without S_alias)
  - SHORTLIST-only decision rules
  - Special case: HARD_BLOCK (score < 0.50)
  - Tie-breaking logic
  - Input/output contract with JSON examples
  - Phase 1–3 rollout timeline
  - Configuration parameters
  - Usage workflow
  - Key principles

---

## Phase 1: SHORTLIST-ONLY Approach

**Goal:** Collect 30–90 days of operator confirmation data to validate top-ranked precision ≥ 90%

**Behavior:**
- All matches (score ≥ 0.50) → SHORTLIST (top 3 candidates presented to operator)
- Hard block (score < 0.50) → Escalate to sales team
- No auto-resolve yet — operator always makes final choice

**Advantages:**
- Low risk: humans validate before automation
- Collects override telemetry for Phase 2 tuning
- Measures operator latency and satisfaction
- Validates signal accuracy and weights

**Success Metrics (target by end of Phase 1):**
- Top-ranked candidate confirmed by operator ≥ 90% of the time
- Operator latency < 30 seconds average
- Zero false positives in top-3 candidates
- Hard block rate < 5%

---

## Next Steps: Immediate Actions Required

### 1. Configure Snowflake Credentials
The Scoring Tool requires Snowflake Account Identifier. You'll see a setup notification in Relevance AI with a link to configure:
- Go to: https://app.relevanceai.com/integrations/f1db6c/098ae5da-7d30-4b81-94d8-3b63fa1757ae
- Provider: `snowflake_native_account_identifier`
- Add your Snowflake account ID (e.g., `xz12345.us-east-1`)

### 2. Verify Data Tables
Confirm that these tables exist in your Snowflake instance with expected columns:
- **`DIM_JDE_ADDRESS_BOOK`**
  - Columns: address_number, customer_name, order_company, branch_plant
- **`FCT_JDE_SALES_ORDER_DETAIL`**
  - Columns: order_id, address_book_number, order_date

### 3. Test Agent in Draft Mode
1. Navigate to agent URL (above)
2. Click "Test" → trigger with sample input:
   ```json
   {
     "customer_name": "La Crote Angalais",
     "order_company": "MADRID_OPERATIONS",
     "branch_plant": "IBERIA_01",
     "context": {
       "sales_region": "EMEA",
       "request_source": "test"
     }
   }
   ```
3. Verify Scoring Tool returns candidates (should see ~3-5 candidates with scores)
4. Verify agent formats SHORTLIST response with top-3 candidates

### 4. Prepare for Phase 1 Rollout
- Identify 10–20 test customer names (known good/bad matches) for validation
- Plan deployment window (recommend off-hours)
- Brief operators on SHORTLIST process (agent will show top-3, operator picks one)
- Set up basic manual tracking for Phase 1 metrics (top-1 precision, latency, false positives)

### 5. Phase 1.5: Observability Setup (Weeks 3–4)
**Defer until agent is live and stable.** Then:
- Create Snowflake logging table: `tbl_customer_resolution_logs`
- Create Logging Tool in Relevance AI
- Integrate logging into agent prompt
- Build KPI dashboard (precision, hard block rate, signal averages)
- Set up alerts (if precision drops < 95%, revert to manual review)

---

## Files & Resources

| File | Purpose | Status |
| --- | --- | --- |
| `/docs/customer-name-resolution-strategy.md` | Full 810-line specification | ✅ Committed |
| `/docs/customer-name-resolution-implementation-checklist.md` | Step-by-step checklist | ✅ Committed |
| `/docs/IMPLEMENTATION-SUMMARY.md` | Overview & quick-start | ✅ Committed |
| `/docs/DECISIONS.md` | Strategic decisions (Phase 1 scope) | ✅ Committed |
| `/docs/SNOWFLAKE-FUNCTIONS-ANALYSIS.md` | Snowflake function mapping | ✅ Committed |
| `/docs/LOGGING-OBSERVABILITY-GUIDE.md` | Phase 1.5+ logging spec | ✅ Committed |
| `/docs/SCORING-TOOL-SQL.md` | SQL template + config guide | ✅ NEW |
| `/docs/AGENT-DEPLOYMENT-SUMMARY.md` | This file | ✅ NEW |

---

## Relevance AI Artifacts

| Artifact | ID | Status |
| --- | --- | --- |
| **Scoring Tool** | `5ee25344-8e14-46f1-83af-9f658065bfb3` | ✅ Created, ready to configure |
| **Agent (Draft)** | `aaa08007-5c73-4d80-82ff-7dfaa8302c63` | ✅ Created, tools attached, ready to test |
| **Agent URL** | See above | ✅ Accessible in Garage_56 sandbox |

---

## Configuration Checklist

- [ ] Snowflake credentials added to Relevance AI
- [ ] Data tables verified (DIM_JDE_ADDRESS_BOOK, FCT_JDE_SALES_ORDER_DETAIL)
- [ ] Agent tested in draft mode with sample input
- [ ] Scoring Tool returns candidates with correct signal scores
- [ ] Agent formats SHORTLIST response correctly (top-3 with full breakdown)
- [ ] Test cases identified (10–20 known good/bad matches)
- [ ] Operators briefed on Phase 1 SHORTLIST process
- [ ] Manual tracking ready for Phase 1 metrics
- [ ] Phase 1.5 observability planning started

---

## Key Decisions Locked In (Phase 1)

1. **No S_alias signal** — Deferred to Phase 2+. Phase 1 uses 6 signals only.
2. **No language mappings** — SOUNDEX phonetic matching handles variants instead.
3. **No comprehensive logging** — Deferred to Phase 1.5+. Phase 1 focuses on core resolution logic.
4. **SHORTLIST-only mode** — All matches (score ≥ 0.50) go to operators. No auto-resolve yet.
5. **Conservative rollout** — 4-phase approach: Phase 1 (SHORTLIST) → Phase 1.5 (logging) → Phase 2 (alias auto-resolve) → Phase 3 (full semantic auto-resolve).

---

## Support

**Scoring Tool Issues:**
- Verify Snowflake credentials are set
- Check data tables exist with correct columns
- Test SQL directly in Snowflake: run the query from `/docs/SCORING-TOOL-SQL.md`

**Agent Issues:**
- Check Scoring Tool is attached and action ID is correct in system prompt
- Review agent URL in Relevance AI; look for error messages in test runs
- Verify input schema matches expected JSON structure

**Phase 1 Metrics Issues:**
- Logging is deferred to Phase 1.5
- For now, manually track: top-1 precision, operator latency, false positives
- Document override patterns for Phase 2 tuning

---

## Version History

| Version | Date | Status | Changes |
| --- | --- | --- | --- |
| 1.0 (Phase 1 PoC) | 2026-07-29 | DEPLOYED | Scoring Tool + Agent created in Relevance AI; ready for Phase 1 SHORTLIST-only rollout |

---

**Next Step:** Configure Snowflake credentials, then test agent in draft mode.  
**Questions?** Review the full strategy doc or implementation checklist.

✅ **Status: READY FOR PHASE 1 ROLLOUT**

