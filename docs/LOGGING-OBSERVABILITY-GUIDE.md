# Mandatory Logging & Observability Guide
## Customer Name Resolution Strategy — Implementation

**Date:** July 29, 2026  
**Status:** Implementation specification  

---

## Overview

**Every customer name resolution attempt** must be logged with complete audit trail. This enables:
- **Telemetry** for KPI tracking (precision, false positives, hard blocks)
- **Debugging** (why did signal X score so low?)
- **Regulatory compliance** (audit trail for customer lookup decisions)
- **Continuous improvement** (override patterns feed Phase 2 tuning)

---

## 1. Logging Architecture

### Two-Layer Logging Approach

#### **Layer 1: In-Memory Logging (Agent)**
- Agent captures all request/response metadata
- Formats as JSON record
- Passes to logging sink asynchronously

#### **Layer 2: Persistent Storage (Cloud/Data Warehouse)**
- Logs written to durable storage (Snowflake table, S3, Cloud Logging)
- Queryable for analytics, dashboarding, alerting
- Retained for 12+ months (audit trail)

---

## 2. What Gets Logged

### Complete Request Context

```json
{
  "timestamp": "2026-07-29T14:23:45.123Z",
  "request_id": "res_abc123def456",
  "request_source": "stock_availability_agent",
  
  // INPUT
  "input": {
    "customer_name_raw": "la crote angalais",
    "order_company": "MADRID_OPERATIONS",
    "branch_plant": "IBERIA_01",
    "sales_region": "EMEA",
    "user_id": "agent_system"
  },
  
  // PREPROCESSING
  "preprocessing": {
    "customer_name_normalized": "CROTE INGLES",
    "steps_applied": [
      "uppercase",
      "trim",
      "punctuation_cleanup",
      "legal_suffix_removal",
      "tokenization"
    ],
    "tokens": ["CROTE", "INGLES"]
  },
  
  // SCORING DETAILS
  "scoring_details": {
    "candidates_evaluated": 100,
    "top_candidate": {
      "rank": 1,
      "address_number": "12345",
      "customer_name": "EL CORTE INGLES",
      "combined_score": 0.94,
      "signals": {
        "S_token": 0.90,
        "S_phonetic": 0.88,
        "S_sim": 0.85,
        "S_edit": 0.92,
        "S_context": 1.00,
        "S_history": 0.65
      },
      "provenance": {
        "order_company": "MADRID_OPERATIONS",
        "branch_plant": "IBERIA_01",
        "last_order_date": "2026-07-15",
        "order_count_730d": 12
      }
    },
    "competitor": {
      "rank": 2,
      "address_number": "54321",
      "customer_name": "CORTES ESPAÑOLAS",
      "combined_score": 0.81,
      "gap_from_top": 0.13
    }
  },
  
  // DECISION & OUTCOME
  "decision": {
    "outcome": "AUTO_RESOLVED",  // or SHORTLIST, HARD_BLOCK
    "reason": "Exact score 0.94 >= threshold 0.92 + corroborator S_context=1.0 + no competitor within delta 0.05",
    "corroborator_satisfied": "S_context=1.00"
  },
  
  // HUMAN INTERACTION (if SHORTLIST)
  "operator_action": null,  // or { operator_id, choice, timestamp, latency_ms }
  
  // PERFORMANCE
  "execution": {
    "scoring_latency_ms": 45,
    "total_request_latency_ms": 87,
    "sql_queries_executed": 3,
    "sql_join_size": 2847,  // candidates evaluated
    "cache_hit": false
  },
  
  // COMPLIANCE
  "audit_trail": {
    "trace_id": "abc123def456",
    "session_id": "sess_xyz789",
    "version": "phase_1_shortlist_only"
  }
}
```

---

## 3. Logging Implementation

### Option A: Agent Prompt (Simple, Recommended for Phase 1)

Add to agent system prompt, after decision rule applied:

```
## Logging Requirement

After each resolution attempt, log the following JSON structure to {{_actions.LOGGER_ACTION_ID}}:

{
  "timestamp": <ISO 8601 now>,
  "request_id": <unique ID>,
  "input": { customer_name_raw, order_company, branch_plant, sales_region },
  "preprocessing": { customer_name_normalized, steps_applied, tokens },
  "scoring_details": {
    "candidates_evaluated": <number>,
    "top_candidate": { address_number, customer_name, combined_score, signals, provenance },
    "competitor": { address_number, customer_name, combined_score, gap_from_top }
  },
  "decision": { outcome, reason, corroborator_satisfied },
  "operator_action": <null or { operator_id, choice, timestamp, latency_ms }>,
  "execution": { scoring_latency_ms, total_request_latency_ms, sql_queries_executed, cache_hit }
}

Send this JSON to the logging tool. Do not wait for confirmation; fire asynchronously.
```

**Relevance AI Implementation:**
```yaml
Attach tool: "Logging Tool" (custom HTTP POST or Snowflake insert tool)
Action behavior: "never-ask" (fire and forget, no operator interaction)
```

### Option B: Scoring Tool (Advanced, for Phase 2+)

If using a dedicated Snowflake Transformation tool, add logging directly in SQL:

```sql
-- After scoring query completes, INSERT result into logging table
INSERT INTO tbl_customer_resolution_logs (
  timestamp, request_id, input_customer_name_raw, input_normalized,
  candidates_evaluated, top_address_number, top_customer_name, combined_score,
  signal_token, signal_phonetic, signal_sim, signal_edit, signal_context, signal_history,
  decision_outcome, decision_reason, execution_latency_ms
)
SELECT
  CURRENT_TIMESTAMP(),
  :request_id,
  :input_name,
  normalized_input.normalized_name,
  (SELECT COUNT(*) FROM scored_candidates),
  scored_candidates.address_number,
  scored_candidates.customer_name,
  scored_candidates.combined_score,
  scored_candidates.S_token,
  scored_candidates.S_phonetic,
  scored_candidates.S_sim,
  scored_candidates.S_edit,
  scored_candidates.S_context,
  scored_candidates.S_history,
  CASE
    WHEN scored_candidates.combined_score >= 0.92 THEN 'AUTO_RESOLVED'
    WHEN scored_candidates.combined_score >= 0.80 THEN 'SHORTLIST'
    ELSE 'HARD_BLOCK'
  END,
  'Automatic scoring decision',
  DATEDIFF(ms, query_start_time, CURRENT_TIMESTAMP())
FROM scored_candidates
WHERE rank = 1
LIMIT 1;
```

---

## 4. Logging Table Schema (Snowflake)

```sql
CREATE TABLE tbl_customer_resolution_logs (
  -- Metadata
  log_id STRING PRIMARY KEY DEFAULT UUID(),
  timestamp TIMESTAMP_NTZ NOT NULL,
  request_id STRING NOT NULL,
  trace_id STRING,
  session_id STRING,
  
  -- Input Context
  input_customer_name_raw STRING,
  input_customer_name_normalized STRING,
  input_order_company STRING,
  input_branch_plant STRING,
  input_sales_region STRING,
  
  -- Preprocessing
  normalization_steps_applied ARRAY,
  input_tokens ARRAY,
  
  -- Scoring
  candidates_evaluated NUMBER,
  top_rank_address_number STRING,
  top_rank_customer_name STRING,
  top_rank_combined_score FLOAT,
  top_rank_S_token FLOAT,
  top_rank_S_phonetic FLOAT,
  top_rank_S_sim FLOAT,
  top_rank_S_edit FLOAT,
  top_rank_S_context FLOAT,
  top_rank_S_history FLOAT,
  
  second_rank_address_number STRING,
  second_rank_combined_score FLOAT,
  score_gap_to_competitor FLOAT,
  
  -- Decision
  decision_outcome STRING,  -- AUTO_RESOLVED, SHORTLIST, HARD_BLOCK
  decision_reason STRING,
  corroborator_satisfied STRING,  -- Which signal enabled auto-resolve
  
  -- Operator Action (if SHORTLIST)
  operator_id STRING,
  operator_choice_address_number STRING,
  operator_action_timestamp TIMESTAMP_NTZ,
  operator_response_latency_ms NUMBER,
  
  -- Performance
  scoring_latency_ms NUMBER,
  total_request_latency_ms NUMBER,
  sql_queries_executed NUMBER,
  sql_candidates_join_size NUMBER,
  
  -- Audit
  request_source STRING,
  version STRING,
  
  -- Indexes
  INDEX idx_timestamp (timestamp),
  INDEX idx_request_id (request_id),
  INDEX idx_decision_outcome (decision_outcome),
  INDEX idx_operator_id (operator_id)
);
```

---

## 5. Logging Sink Options

### Option 1: Snowflake Table (Recommended)
**Best for:** Data warehouse integration, easy querying

```sql
-- Agent calls tool: "Insert Log"
-- Tool: Custom Snowflake INSERT Transformation
-- Latency: ~100ms per log entry
-- Retention: 12+ months
-- Queryable: Direct SQL for analytics
```

**Setup:**
```sql
-- Create logging table
CREATE TABLE tbl_customer_resolution_logs (...);

-- Create Relevance AI tool that accepts JSON + inserts
-- Tool: POST to /api/logging with JSON payload
-- Snowflake INSERT via Snowflake connector
```

### Option 2: Cloud Logging Service (Google Cloud Logging, AWS CloudWatch)
**Best for:** Real-time alerting, structured log search

```
Agent → Cloud Logging Sink → BigQuery/Athena for analytics
```

**Setup:**
- Relevance AI → HTTP POST to logging service
- JSON schema enforced at ingestion
- Real-time KPI dashboards

### Option 3: Hybrid (Dual Write)
**Best for:** Immediate alerts + long-term analytics

```
Agent → Cloud Logging (real-time alerts)
     → Snowflake (batch analytics)
```

---

## 6. How Users Interact with Logs

### For Operators (SHORTLIST Mode)

**Workflow:**
1. Agent presents SHORTLIST with top 3 candidates
2. Operator clicks "Confirm" for selected customer
3. Agent logs:
   - `operator_action.choice = selected_address_number`
   - `operator_action.timestamp = now()`
   - `operator_action.latency_ms = time_since_shortlist_presented`
4. Log written to storage asynchronously

**Example Log Entry (SHORTLIST with Operator Override):**
```json
{
  "request_id": "res_xyz789",
  "decision": {
    "outcome": "SHORTLIST",
    "reason": "score 0.88 in range [0.80, 0.92)"
  },
  "operator_action": {
    "operator_id": "ops_maria_gonzalez",
    "choice": "12345",  // Chose top-ranked
    "timestamp": "2026-07-29T14:24:10Z",
    "latency_ms": 12  // 12 seconds from presentation
  }
}
```

### For Data Analysts (Phase 1 Telemetry)

**Query: Daily Auto-Resolve Precision**
```sql
SELECT
  DATE(timestamp) AS date,
  decision_outcome,
  COUNT(*) AS count,
  COUNT(CASE WHEN operator_choice_address_number IS NULL THEN 1 END) AS accepted,
  COUNT(CASE WHEN operator_choice_address_number IS NOT NULL 
    AND operator_choice_address_number != top_rank_address_number THEN 1 END) AS overridden,
  ROUND(
    (COUNT(*) - COUNT(CASE WHEN operator_choice_address_number IS NOT NULL 
      AND operator_choice_address_number != top_rank_address_number THEN 1 END)) / COUNT(*),
    4
  ) AS precision
FROM tbl_customer_resolution_logs
WHERE decision_outcome IN ('AUTO_RESOLVED', 'SHORTLIST')
GROUP BY DATE(timestamp), decision_outcome
ORDER BY DATE(timestamp) DESC;
```

**Query: Top-5 False Positives (Overridden AUTO_RESOLVED)**
```sql
SELECT
  top_rank_customer_name,
  operator_choice_address_number,
  COUNT(*) AS override_count,
  ROUND(AVG(top_rank_combined_score), 3) AS avg_score,
  ROUND(AVG(top_rank_S_token), 3) AS avg_S_token,
  ROUND(AVG(top_rank_S_phonetic), 3) AS avg_S_phonetic
FROM tbl_customer_resolution_logs
WHERE decision_outcome = 'AUTO_RESOLVED'
  AND operator_choice_address_number IS NOT NULL
  AND operator_choice_address_number != top_rank_address_number
GROUP BY top_rank_customer_name, operator_choice_address_number
ORDER BY override_count DESC
LIMIT 5;
```

**Query: Operator Response Latency (SHORTLIST)**
```sql
SELECT
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY operator_response_latency_ms) AS median_latency_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY operator_response_latency_ms) AS p95_latency_ms,
  MAX(operator_response_latency_ms) AS max_latency_ms,
  COUNT(*) AS total_shortlist_confirmations
FROM tbl_customer_resolution_logs
WHERE decision_outcome = 'SHORTLIST'
  AND operator_id IS NOT NULL;
```

### For DevOps / SRE (Operational Monitoring)

**Alert Rules (Cloud Logging):**
```yaml
# Alert: Auto-resolve precision drops below 95%
- name: auto_resolve_precision_alert
  condition: |
    COUNT(decision_outcome='AUTO_RESOLVED') - 
    COUNT(decision_outcome='AUTO_RESOLVED' AND operator_choice != top_rank) 
    < 0.95 * COUNT(decision_outcome='AUTO_RESOLVED')
  window: 1_hour
  threshold: trigger if true
  notification: email ops-team@company.com

# Alert: Hard block rate > 10%
- name: hard_block_rate_alert
  condition: |
    COUNT(decision_outcome='HARD_BLOCK') / COUNT(*) > 0.10
  window: 1_hour
  notification: slack #stock-availability-alerts
```

---

## 7. Logging Lifecycle

### Real-Time Flow (Agent)

```
1. Agent receives request (customer name + context)
   ↓
2. Agent invokes Scoring Tool → returns signals + decision
   ↓
3. Agent applies decision rule → AUTO_RESOLVED / SHORTLIST / HARD_BLOCK
   ↓
4. If SHORTLIST: Present to operator; wait for confirmation
   ↓
5. Agent formats log JSON (includes operator choice if applicable)
   ↓
6. Agent invokes Logging Tool (async, fire-and-forget)
   ↓
7. Logging Tool writes to Snowflake / Cloud Logging
   ↓
8. Return result to caller (no wait for logging)
```

**Timeline:**
- Total latency to user: ~100ms (agent + scoring + logging fire-and-forget)
- Logging latency: ~100–500ms (background write)

### Batch Analytics (Daily)

```
1. Snowflake table accumulates logs (24 hours)
   ↓
2. Daily scheduled query: Compute KPIs
   - Auto-resolve precision
   - Hard block rate
   - Operator latency
   - Top-5 false positives
   ↓
3. Results written to analytics table
   ↓
4. Dashboard pulls from analytics table (1-day refresh latency)
   ↓
5. Alert rules trigger on KPI thresholds
```

---

## 8. Phase 1 Logging Scope

### Required for Phase 1

- ✅ Log every resolution attempt (all outcomes)
- ✅ Capture all 6 signals + combined score
- ✅ Capture input context (order company, branch, region)
- ✅ Capture preprocessing (normalized name, tokens)
- ✅ Capture decision outcome + reason
- ✅ Capture operator action (if SHORTLIST)
- ✅ Capture latency metrics
- ✅ Write to persistent storage (Snowflake table)

### Optional for Phase 1

- ⚠️ Real-time alerting (can add in Phase 2)
- ⚠️ Cloud Logging integration (Snowflake table sufficient)
- ⚠️ Advanced analytics dashboard (basic SQL queries sufficient)

### Deferred to Phase 2+

- ❌ Structured logging library (simple JSON sufficient)
- ❌ Distributed tracing (trace_id included for future use)
- ❌ Log aggregation service (Snowflake table is sufficient)

---

## 9. SQL Query Examples for KPI Dashboard

### KPI 1: Daily Precision

```sql
WITH daily_precision AS (
  SELECT
    DATE(timestamp) AS date,
    ROUND(
      (COUNT(*) - COUNT(CASE 
        WHEN decision_outcome = 'AUTO_RESOLVED' 
        AND operator_choice_address_number IS NOT NULL 
        AND operator_choice_address_number != top_rank_address_number 
        THEN 1 
      END)) / NULLIF(COUNT(CASE WHEN decision_outcome = 'AUTO_RESOLVED' THEN 1 END), 0),
      4
    ) AS auto_resolve_precision
  FROM tbl_customer_resolution_logs
  GROUP BY DATE(timestamp)
)
SELECT * FROM daily_precision ORDER BY date DESC;
```

### KPI 2: Hard Block Rate

```sql
SELECT
  DATE(timestamp) AS date,
  ROUND(COUNT(CASE WHEN decision_outcome = 'HARD_BLOCK' THEN 1 END) / COUNT(*), 4) AS hard_block_rate,
  COUNT(*) AS total_requests
FROM tbl_customer_resolution_logs
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

### KPI 3: Top-5 Signals (Highest S_token Average)

```sql
SELECT
  DATE(timestamp) AS date,
  ROUND(AVG(top_rank_S_token), 3) AS avg_S_token,
  ROUND(AVG(top_rank_S_phonetic), 3) AS avg_S_phonetic,
  ROUND(AVG(top_rank_S_context), 3) AS avg_S_context,
  COUNT(*) AS resolution_count
FROM tbl_customer_resolution_logs
WHERE decision_outcome IN ('AUTO_RESOLVED', 'SHORTLIST')
GROUP BY DATE(timestamp)
ORDER BY date DESC;
```

### KPI 4: Operator Latency (SHORTLIST)

```sql
SELECT
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY operator_response_latency_ms) AS p50_latency_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY operator_response_latency_ms) AS p95_latency_ms,
  COUNT(*) AS shortlist_count
FROM tbl_customer_resolution_logs
WHERE decision_outcome = 'SHORTLIST' AND operator_response_latency_ms IS NOT NULL
GROUP BY TRUNC(timestamp, 'DAY')
ORDER BY TRUNC(timestamp, 'DAY') DESC;
```

---

## 10. Privacy & Compliance

### Data Retention
- **Logs retained for:** 12 months (tunable)
- **Deletion policy:** Auto-delete logs older than 12 months
- **PII handling:** Customer names are business data (not PII by default); confirm with compliance team

### Audit Trail
- Every log entry includes:
  - `trace_id` — unique request identifier
  - `timestamp` — exact when decision was made
  - `decision_reason` — why this outcome was selected
  - `operator_id` (if human-in-the-loop) — who confirmed

### Access Control
- **Read:** Analytics team, data scientists, customer support (if investigating issue)
- **Write:** Agent system only (via logging tool)
- **Delete:** Admin only (via retention policy)

---

## Summary: Logging Checklist

- [ ] Create logging table in Snowflake (`tbl_customer_resolution_logs`)
- [ ] Create Logging Tool in Relevance AI (INSERT transformation or HTTP POST)
- [ ] Add logging call to agent prompt (after decision rule)
- [ ] Test logging with 10 manual requests (verify JSON structure)
- [ ] Create KPI dashboard (Looker / Google Sheets pulling from Snowflake)
- [ ] Set up daily KPI alerts (low precision, high hard block rate)
- [ ] Document logging schema for analytics team
- [ ] Configure log retention policy (12 months)
- [ ] Test operator override capture (SHORTLIST mode)
- [ ] Verify logs queryable for Phase 1 → Phase 2 tuning

---

**Status: ✅ Ready to implement logging infrastructure**
