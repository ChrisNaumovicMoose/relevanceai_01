# Customer Name Resolution — Implementation Checklist
## Quick-Reference for Building in Relevance AI

**Status:** Ready to implement  
**Phase:** 1 (SHORTLIST only — Phase 1 of 4)  
**Timeline:** Week 1 = Tool + Agent setup; Week 2–4 = Testing; Week 5+ = Phase 1 rollout  

---

## Pre-Implementation (Preparation)

- [ ] Read full strategy doc: `/docs/customer-name-resolution-strategy.md`
- [ ] Review agent prompt template: `/tmp/claude-0/-home-user-relevanceai-01/f776483b-1b62-5e7c-a780-afa10620a334/scratchpad/customer-name-resolution-agent-prompt.md`
- [ ] Confirm JDE Address Book structure (table: `DIM_JDE_ADDRESS_BOOK`, columns: "Address Number", "Customer Name", "Branch Plant", "Order Company")
- [ ] Confirm sales order history table (table: `FCT_JDE_SALES_ORDER_DETAIL`, columns: "Address Book Number", "Order Date")
- [ ] Identify test cases (20+ real customer names from orders, diverse: typos, phonetic variants, language variants, known aliases)

---

## Step 1: Create Scoring Tool (Transformation or Custom API)

### 1a. Choose Implementation Mode
- [ ] **Transformation Tool** (Snowflake SQL-based, recommended for simpler deployments)
  - Pros: Built-in to Relevance AI, fast iteration, no external dependencies
  - Cons: Limited to Snowflake; requires SQL expertise
- [ ] **Custom API Tool** (external microservice, recommended for reusable/complex deployments)
  - Pros: Language-agnostic, can host anywhere, reusable across platforms
  - Cons: Additional infrastructure, requires deployment pipeline

**Recommendation:** Start with **Transformation Tool** for Phase 1; migrate to API if needed for Phase 3+ scale.

### 1b. Implement Normalization Function
- [ ] Unicode/diacritics removal (NFKD normalize, strip diacritics → ASCII)
- [ ] Uppercase + trim + punctuation cleanup
- [ ] Legal suffix removal (S.A., LTD, SAS, PLC, Inc., Ltd., Corp., etc.)
- [ ] Tokenization (split on spaces, remove stopwords: THE, A, AN, &)
- [ ] Output: Normalized string + token array

**PARKED FOR PHASE 2+:**
- [ ] Language-specific mappings (configurable lookup table) — **DEFERRED**
  - Would include: ANGALAIS → INGLES, ANGLAIS → INGLES, CROTE → CORTE, FRANCAIS → FRANCES, etc.
  - Phase 1 relies on phonetic matching to handle variants instead
  - Can add mapping table in Phase 2 based on operator override patterns from Phase 1 data

### 1c. Implement Signal Computations

**S_token (Token Overlap):**
- [ ] FLATTEN(SPLIT(...)) to tokenize both input and candidate
- [ ] Compute intersection (tokens in both)
- [ ] Jaccard ratio: `intersection_count / max(input_token_count, candidate_token_count)`
- [ ] Result: 0–1 float

**S_phonetic (Phonetic Token Overlap):**
- [ ] SOUNDEX() for each token (or UDF for DoubleMetaphone if available)
- [ ] Count phonetic matches (tokens with same phonetic code)
- [ ] Ratio: `phonetic_intersection_count / max(input_token_count, candidate_token_count)`
- [ ] Result: 0–1 float

**S_sim (Jaro-Winkler):**
- [ ] JAROWINKLER_SIMILARITY(normalized_input, normalized_candidate)
- [ ] Divide by 100 to normalize to [0, 1]
- [ ] Result: 0–1 float

**S_edit (Edit Distance):**
- [ ] EDITDISTANCE(normalized_input, normalized_candidate)
- [ ] Normalize: `1 - (distance / max(len(input), len(candidate)))`, clamp to [0, 1]
- [ ] Result: 0–1 float

**S_context (Region/Company/Branch Match):**
- [ ] If order_company supplied: look up candidate's order_company, compare
  - [ ] Exact match (e.g., MADRID_OPERATIONS == MADRID_OPERATIONS): 1.0
  - [ ] Country-level match (e.g., MADRID vs MADRID): 0.5
  - [ ] Mismatch or absent: 0.0
- [ ] If branch_plant supplied: repeat for branch field
- [ ] Return: max(order_company_score, branch_plant_score)
- [ ] Result: 0–1 float

**S_history (Sales Recency/Frequency):**
- [ ] For each candidate address_number:
  - [ ] `SELECT COUNT(DISTINCT order_id) FROM FCT_JDE_SALES_ORDER_DETAIL WHERE address_number = ? AND order_date > CURRENT_DATE - 730`
  - [ ] Cap at 20 (tuning constant): `MIN(count, 20) / 20`
- [ ] Result: 0–1 float

**S_alias (Curated Alias Lookup) — PARKED FOR PHASE 2+**
- [ ] **SKIPPED FOR PHASE 1** — No alias table available
- [ ] Phase 2+: Create/reference table: `tbl_customer_aliases` (columns: canonical_name, alias_variant, address_number)
- [ ] Phase 2+: Exact match lookup: if normalized_input matches any alias_variant, S_alias = 1.0
- [ ] Phase 2+: Otherwise: 0.0
- [ ] Phase 1: Set S_alias = 0.0 always (remove from combined score calculation)

### 1d. Implement Combined Score Formula

**Phase 1 (without S_alias):**
- [ ] `combined_score = 0.35*S_token + 0.25*S_phonetic + 0.10*S_sim + 0.05*S_edit + 0.15*S_context + 0.05*S_history`
- [ ] Clamp to [0, 1]
- [ ] Return per-candidate: combined_score + all 6 signals (S_alias = 0.0 always)

### 1e. Implement Candidate Ranking & Output

- [ ] Order candidates by combined_score DESC
- [ ] Limit to top 100 candidates (tuning constant)
- [ ] Return output schema:
  ```json
  {
    "input_normalized": "...",
    "candidates": [
      {
        "rank": 1,
        "address_number": "...",
        "customer_name": "...",
        "combined_score": 0.94,
        "signals": {
          "S_token": 0.90,
          "S_phonetic": 0.88,
          ...
        },
        "provenance": {
          "order_company": "...",
          "branch_plant": "...",
          "last_order_date": "..."
        }
      }
    ]
  }
  ```

### 1f. Test Scoring Tool

- [ ] Test with 100+ real customer names (known good / bad matches)
- [ ] Verify accuracy of signal computation (spot-check calculations)
- [ ] Measure latency (target: < 500ms per request)
- [ ] Validate output schema matches expected format
- [ ] **Test examples:**
  - [ ] Input: "la crote angalais", context: {order_company: "MADRID_OPERATIONS"} → Expected: EL CORTE INGLES scores ≥ 0.90
  - [ ] Input: "amazon", context: none → Expected: Hard block (score < 0.50 for all candidates)
  - [ ] Input: exact alias variant → Expected: S_alias = 1.0, top candidate auto-resolvable

---

## Step 2: Create Agent in Relevance AI

### 2a. Agent Setup
- [ ] Navigate to Relevance AI console → Create new agent
- [ ] **Name:** "Customer Name Resolution Agent"
- [ ] **Description:** "Resolves free-text customer names to Address Book records using semantic-first matching"
- [ ] **System Prompt:** Copy from `/tmp/claude-0/-home-user-relevanceai-01/f776483b-1b62-5e7c-a780-afa10620a334/scratchpad/customer-name-resolution-agent-prompt.md`
  - [ ] Replace placeholders (e.g., "[Company Name]" with actual company)
  - [ ] Customize examples if needed

### 2b. Attach Scoring Tool
- [ ] Call `relevance_attach_tools_to_agent`:
  - [ ] `agent_id`: [newly created agent ID]
  - [ ] `tool_ids`: [Scoring Tool ID from Step 1]
  - [ ] `action_behaviour`: "never-ask" (deterministic scoring, no permission needed)
- [ ] Note the returned `action_id` (16-char hex string)

### 2c. Update System Prompt with Action Pills
- [ ] Read returned `action_id` from attach step
- [ ] Call `relevance_edit_agent_system_prompt`:
  - [ ] Find text: `{{_actions.ACTION_ID_CUSTOMER_NAME_SCORER}}`
  - [ ] Replace with: actual `action_id` (e.g., `{{_actions.abc123def4567890}}`)
  - [ ] Save to draft

### 2d. Agent Configuration
- [ ] Set `autonomy_limit`: 50 (max tool calls per task)
- [ ] Set `autonomy_limit_behaviour`: "terminate-conversation"
- [ ] Set initial phase: **"phase_1_shortlist_only"** (disable auto-resolve)

### 2e. Test Agent (Draft Mode)
- [ ] Trigger agent with test input:
  ```json
  {
    "customer_name": "la crote angalais",
    "order_company": "MADRID_OPERATIONS",
    "branch_plant": null,
    "context": { "sales_region": "EMEA", "request_source": "test" }
  }
  ```
- [ ] Expected output: SHORTLIST with top 3 candidates
- [ ] Verify: signals are all present, combined_score is correct, provenance is populated
- [ ] **Do NOT publish yet** — still in draft, Phase 1 testing

---

## Step 3: Set Up Observability & Logging — DEFERRED TO PHASE 1.5+

**Status:** ⏸️ Parked after agent is live in SHORTLIST-only mode (1–2 weeks into Phase 1)

### 3a. Create Logging Sink (Phase 1.5, after agent is live)
- [ ] Choose destination: Snowflake table, cloud storage (S3/GCS), or observability platform
- [ ] Create table: `tbl_customer_name_resolution_logs` with columns:
  ```sql
  CREATE TABLE tbl_customer_name_resolution_logs (
    timestamp TIMESTAMP,
    request_id STRING,
    input_raw STRING,
    input_normalized STRING,
    decision_outcome STRING,  -- AUTO_RESOLVED / SHORTLIST / HARD_BLOCK
    combined_score FLOAT,
    signals OBJECT,  -- JSON: S_token, S_phonetic, etc.
    resolved_address_number STRING,  -- NULL if SHORTLIST/HARD_BLOCK
    operator_action STRING,  -- For SHORTLIST: which candidate was chosen
    latency_ms INT,
    request_source STRING
  );
  ```

### 3b. Configure Agent to Log
- [ ] Add logging step to agent (after decision rule application)
- [ ] Log schema above; include all 7 signals + decision outcome + operator action

### 3c. Create Daily KPI Dashboard
- [ ] Set up dashboard with metrics:
  - [ ] Auto-resolve precision: `(AUTO_RESOLVED - overridden) / AUTO_RESOLVED` (target ≥ 98%)
  - [ ] Shortlist resolution rate: `confirmed / SHORTLIST` (track latency)
  - [ ] Hard block rate: `HARD_BLOCK / total_requests` (target < 5%)
  - [ ] Top-5 false positives (review manually)
  - [ ] Alias hit rate: `(S_alias=1 matches) / total_requests` (target 15–25%)
- [ ] Set up alerts:
  - [ ] If auto-resolve precision < 95% → Alert: revert to SHORTLIST-only
  - [ ] If hard block rate > 10% → Alert: escalate to data quality team

---

## Step 4: Phase 1 Rollout (SHORTLIST ONLY, 30–90 days)

### 4a. Configuration for Phase 1
- [ ] Agent config: `"rollout_phase": "phase_1_shortlist_only"`
- [ ] Thresholds: `AUTO_THRESH_HIGH = ∞` (disable auto-resolve entirely)
- [ ] All matches → SHORTLIST (no exceptions)

### 4b. Publish Agent (Draft → Live)
- [ ] Call `relevance_publish_agent`:
  - [ ] `agent_id`: [agent ID]
  - [ ] `version_name`: "Phase 1 - SHORTLIST Only"
  - [ ] `version_description`: "Initial rollout with SHORTLIST only; collecting operator override data"
- [ ] Wait for approval card
- [ ] Confirm publish

### 4c. Deploy to Production
- [ ] Enable in stock-availability-ai agent (or integration point)
- [ ] Monitor logs (real-time dashboard)
- [ ] Confirm no errors/exceptions in first 100 requests

### 4d. Phase 1 Data Collection (30–90 days)
- [ ] **Goal:** Collect operator override telemetry; validate top-ranked precision ≥ 90%
- [ ] **Daily:** Review dashboard; watch for anomalies
- [ ] **Weekly:** Pull override logs; identify patterns (e.g., which customers/regions have high disagreement)
- [ ] **Monthly:** Analyze top-5 false positives; update alias table if needed

### 4e. Phase 1 Success Criteria (Advance to Phase 2 when ALL met)
- [ ] Top-ranked candidate confirmed by operator ≥ 90% of the time
- [ ] Operator latency < 30 seconds on average
- [ ] No false positives in top-3 candidates
- [ ] 30+ days of data collected (goal: 1000+ requests)

---

## Step 5: Phase 2 Rollout (AUTO-RESOLVE WITH ALIAS ONLY, 30–60 days after Phase 1)

- [ ] **Configuration:**
  - [ ] `AUTO_THRESH_HIGH = 0.92`
  - [ ] **Only auto-resolve if:** `S_alias = 1` (exact alias match)
  - [ ] All others → SHORTLIST
- [ ] **Success criteria:** Auto-resolve precision ≥ 99.5%
- [ ] Advance to Phase 3 only after 30–60 days if precision target met

---

## Step 6: Phase 3 Rollout (AUTO-RESOLVE WITH CORROBORATORS, 90+ days after Phase 2)

- [ ] **Configuration:**
  - [ ] `AUTO_THRESH_HIGH = 0.92`
  - [ ] **Auto-resolve if:** `S_score >= 0.92` + at least ONE corroborator:
    - [ ] `S_context >= 0.75` (exact region match), OR
    - [ ] `S_history >= 0.50` (10+ orders in 730 days), OR
    - [ ] `S_alias = 1`, OR
    - [ ] `S_phonetic >= 0.75` (strong phonetic agreement)
  - [ ] Others → SHORTLIST or HARD_BLOCK
- [ ] **Success criteria:** Auto-resolve precision ≥ 98%, hard block rate < 5%
- [ ] **Monitoring:** Daily KPI dashboard; tune weights monthly

---

## Step 7: Ongoing Tuning & Maintenance

### 7a. Monthly Weights Tuning (Phase 3+)
- [ ] Analyze false positive incidents
- [ ] Recalculate optimal weights using override data (e.g., upgrade S_phonetic from 0.25 → 0.30 if phonetic-only matches have high precision)
- [ ] A/B test new weights on subset of requests before rollout

### 7b. Quarterly Alias Table Updates
- [ ] Collect new brand synonyms from operator overrides
- [ ] Add to `tbl_customer_aliases`
- [ ] Re-test Phase 1–2 with updated alias table

### 7c. Threshold Reviews (Quarterly or Event-Driven)
- [ ] If auto-resolve precision dips < 98%, investigate:
  - [ ] New customer type entering system?
  - [ ] Address book data quality issue?
  - [ ] Language variant not in mappings?
- [ ] Adjust thresholds (e.g., lower AUTO_THRESH_HIGH from 0.92 → 0.88) and monitor

### 7d. Document Decisions
- [ ] Maintain changelog: version history, weight changes, threshold adjustments
- [ ] Link to PR/commits in version control
- [ ] Quarterly retrospective: what worked, what didn't

---

## Files & Resources

| File | Purpose | Location |
| --- | --- | --- |
| **customer-name-resolution-strategy.md** | Full specification | `/docs/customer-name-resolution-strategy.md` |
| **customer-name-resolution-agent-prompt.md** | Agent system prompt (copy/paste into Relevance AI) | `/tmp/claude-0/.../scratchpad/` |
| **customer-name-resolution-implementation-checklist.md** | This file (quick reference) | `/docs/customer-name-resolution-implementation-checklist.md` |

---

## Support & Escalation

- **Scoring Tool Issues:** Check SQL syntax, verify Snowflake connectivity, test signal formulas with spot samples
- **Agent Integration Issues:** Check `action_id` is correct in system prompt, verify tool output schema matches expected format
- **Observability Issues:** Verify logging schema matches agent output, check dashboard SQL queries for accuracy
- **Phase Advancement Blockers:** Review KPI dashboard; if success criteria not met, analyze override logs and adjust weights/thresholds

---

## Timeline & Milestones

| Milestone | Duration | Key Activities |
| --- | --- | --- |
| **Step 1: Scoring Tool** | 1–2 weeks | Implement, test, verify latency |
| **Step 2: Agent Setup** | 3–5 days | Create, attach tool, test draft |
| **Step 3: Observability** | 3–5 days | Set up logging, dashboard, alerts |
| **Step 4: Phase 1 Rollout** | 30–90 days | Live SHORTLIST mode, collect telemetry |
| **Step 5: Phase 2 Rollout** | 30–60 days | Auto-resolve for aliases only |
| **Step 6: Phase 3 Rollout** | 90+ days | Full semantic-first auto-resolve |
| **Step 7: Ongoing** | Continuous | Tune weights, manage thresholds, monitor KPIs |

**Total to Phase 3 go-live:** ~6 months (conservative, telemetry-driven approach)

---

**Status:** ✅ Ready to begin implementation  
**Next Step:** Assign ownership for Steps 1–3; schedule Step 1 kickoff
