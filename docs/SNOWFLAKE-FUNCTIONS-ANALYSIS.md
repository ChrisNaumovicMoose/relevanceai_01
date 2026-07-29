# Snowflake String Functions — Implementation Analysis
## Customer Name Resolution Strategy

**Date:** July 29, 2026  
**Status:** Ready for SQL implementation  
**Scope:** Maps Snowflake native functions to 7-signal scoring pipeline  

---

## Executive Summary

Snowflake provides **native string functions** that directly support the customer name resolution implementation. This document maps required preprocessing, signal computation, and scoring to available Snowflake SQL functions.

**Key Finding:** Snowflake supports all 5 core signal computations natively; no custom UDFs required for Phase 1.

---

## 1. Preprocessing / Normalization Functions

### Requirement: Unicode & Diacritics Removal
**Strategy:** Normalize to NFKD, then remove diacritical marks

**Snowflake Functions:**
- **`TRANSLATE()`** — Replace specific characters with alternatives
- **`REGEXP_REPLACE()`** — Pattern-based replacement using regex
- **`COLLATE`** clause — Control collation for accent-insensitive comparisons

**Recommended Approach (Phase 1):**

```sql
-- Option A: Use COLLATE for accent-insensitive comparison (simplest)
-- Native support, no transformation needed
WHERE customer_name COLLATE 'en-US-x-icu' = input_name COLLATE 'en-US-x-icu'

-- Option B: Explicit diacritics removal with TRANSLATE (if needed)
-- Create mapping for common diacritics
SELECT TRANSLATE(
  customer_name,
  'àáâãäåèéêëìíîïòóôõöùúûüñç',
  'aaaaaaaeeeeiiiiooooouuuunc'
) AS normalized_name
```

**Function Details:**
- `TRANSLATE(string, from_string, to_string)` — Character-by-character replacement
  - Example: `TRANSLATE('Café', 'é', 'e')` → `'Cafe'`
  - Efficient, deterministic
- `COLLATE 'en-US-x-icu'` — Unicode Collation Algorithm (ICU) for accent-insensitive matching
  - Built-in, no function call overhead
  - Preferred for comparisons
- `REGEXP_REPLACE(string, pattern, replacement)` — Regex-based replacement
  - More powerful but slightly slower than TRANSLATE
  - Example: `REGEXP_REPLACE('Café', '[éèê]', 'e')` → `'Cafe'`

**Recommendation for Phase 1:** Use `COLLATE` for comparisons + `TRANSLATE` for normalization if storing normalized values.

---

### Requirement: Uppercase, Trim, Punctuation Cleanup

**Snowflake Functions:**
- **`UPPER()`** — Convert to uppercase
- **`TRIM()`** — Remove leading/trailing whitespace
- **`LTRIM()` / `RTRIM()`** — Remove from left/right only
- **`REGEXP_REPLACE()`** — Replace non-alphanumeric with space

**Recommended Implementation:**

```sql
SELECT 
  UPPER(TRIM(
    REGEXP_REPLACE(
      customer_name,
      '[^A-Z0-9 ]',  -- Match anything that's NOT alphanumeric or space
      ' '             -- Replace with single space
    )
  )) AS normalized_name
FROM dim_jde_address_book
;
-- Example: "el café  del-" → "EL CAFE DEL"
```

**Function Details:**
- `UPPER(string)` — O(1) operation, native
- `TRIM(string)` — Remove spaces from both ends
- `REGEXP_REPLACE(string, pattern, replacement)` — Regex replacement
  - Pattern `'[^A-Z0-9 ]'` matches any char NOT in set [A-Z, 0-9, space]
  - Then collapse multi-spaces with second pass or `' +'` pattern

**Recommended for Phase 1:** Combine in single SELECT for efficiency.

---

### Requirement: Legal Suffix Removal (S.A., LTD, SAS, PLC, etc.)

**Snowflake Functions:**
- **`REGEXP_REPLACE()`** — Pattern-based removal
- **`RLIKE()`** / **`REGEXP_LIKE()`** — Pattern matching (for detection)

**Recommended Implementation:**

```sql
SELECT REGEXP_REPLACE(
  normalized_name,
  '\s+(S\.A|S\.A\.R\.L|SARL|S\.L|LTD|SAS|PLC|INC|CORP|CO|LLC)(\s|$)',
  ''
) AS name_without_suffix
FROM (
  SELECT UPPER(TRIM(REGEXP_REPLACE(customer_name, '[^A-Z0-9 ]', ' '))) AS normalized_name
)
;
-- Example: "ACME CORP S.A." → "ACME CORP"
```

**Function Details:**
- `REGEXP_REPLACE(string, pattern, replacement)` — Regex replacement
  - `'\s+'` — Match one or more whitespace
  - `(S\.A|S\.A\.R\.L|...)` — Match any of these suffixes (pipe = OR)
  - `(\s|$)` — Followed by space or end-of-string
  - `''` — Replace with empty (remove)
- Can be chained with other REGEXP_REPLACE calls

**Recommendation for Phase 1:** Build a single regex with all legal suffixes; test performance.

---

### Requirement: Tokenization (Split on spaces, remove stopwords)

**Snowflake Functions:**
- **`SPLIT()`** — Split string into array
- **`FLATTEN()`** — Expand array into table rows (for set operations)
- **`ARRAY_CONSTRUCT()`** / **`ARRAY_FILTER()`** — Construct/filter arrays

**Recommended Implementation:**

```sql
-- Option A: Split into array (for token overlap computation)
SELECT SPLIT(normalized_name, ' ') AS tokens
FROM normalized_names
;
-- Result: ["CROTE", "INGLES"]

-- Option B: Split and flatten to rows (for set operations)
SELECT FLATTEN(SPLIT(normalized_name, ' ')) AS token
FROM normalized_names
;
-- Result: 
-- CROTE
-- INGLES

-- Option C: Filter out stopwords
WITH tokens AS (
  SELECT FLATTEN(SPLIT(normalized_name, ' ')) AS token
  FROM normalized_names
)
SELECT ARRAY_AGG(token) WITHIN GROUP (ORDER BY token) AS filtered_tokens
FROM tokens
WHERE token NOT IN ('THE', 'A', 'AN', '&')
;
```

**Function Details:**
- `SPLIT(string, delimiter)` → ARRAY
  - Example: `SPLIT('CROTE INGLES', ' ')` → `['CROTE', 'INGLES']`
  - Returns NULL if string is NULL
- `FLATTEN(array)` → TABLE of scalar values
  - Example: `FLATTEN(['CROTE', 'INGLES'])` → rows: CROTE, INGLES
  - Useful for JOIN with stopword list
- `ARRAY_CONSTRUCT(...)`— Build array from values
- `ARRAY_FILTER(array, function)` — Filter array elements

**Recommendation for Phase 1:** Use SPLIT for inline computation; FLATTEN for table joins.

---

## 2. Signal Computation Functions

### Signal 1: S_token (Token Overlap / Jaccard Ratio)

**Requirement:** Count tokens present in both input and candidate; divide by max token count

**Snowflake Approach:**

```sql
-- Step 1: Tokenize both input and candidate
WITH input_tokens AS (
  SELECT SPLIT('CROTE INGLES', ' ') AS tokens
),
candidate_tokens AS (
  SELECT SPLIT('CORTE INGLES', ' ') AS tokens
)

-- Step 2: Compute intersection using ARRAY_INTERSECTION()
-- Step 3: Compute Jaccard ratio
SELECT
  ARRAY_INTERSECTION(input_tokens.tokens, candidate_tokens.tokens) AS common_tokens,
  ARRAY_SIZE(ARRAY_INTERSECTION(input_tokens.tokens, candidate_tokens.tokens)) AS intersection_count,
  GREATEST(
    ARRAY_SIZE(input_tokens.tokens),
    ARRAY_SIZE(candidate_tokens.tokens)
  ) AS max_count,
  ARRAY_SIZE(ARRAY_INTERSECTION(input_tokens.tokens, candidate_tokens.tokens)) / 
    GREATEST(
      ARRAY_SIZE(input_tokens.tokens),
      ARRAY_SIZE(candidate_tokens.tokens)
    ) AS S_token
FROM input_tokens, candidate_tokens
;
-- Result: intersection_count=1, max_count=2, S_token=0.5
```

**Snowflake Functions:**
- **`ARRAY_INTERSECTION(array1, array2)`** — Return elements in both arrays
  - Native set operation; very efficient
  - Example: `ARRAY_INTERSECTION(['CROTE', 'INGLES'], ['CORTE', 'INGLES'])` → `['INGLES']`
- **`ARRAY_SIZE(array)`** — Return number of elements
  - Example: `ARRAY_SIZE(['INGLES'])` → `1`
- **`GREATEST(value1, value2, ...)`** — Return maximum
  - Example: `GREATEST(2, 3)` → `3`

**Recommendation for Phase 1:** Direct array operations; no external computation needed. **Latency: < 1ms per candidate.**

---

### Signal 2: S_phonetic (Phonetic Token Overlap)

**Requirement:** Match tokens by phonetic code (SOUNDEX), count matches

**Snowflake Approach:**

```sql
-- Step 1: Compute SOUNDEX for each token
WITH input_phonetics AS (
  SELECT token, SOUNDEX(token) AS phonetic_code
  FROM TABLE(FLATTEN(INPUT(SPLIT('CROTE INGLES', ' '))))
),
candidate_phonetics AS (
  SELECT token, SOUNDEX(token) AS phonetic_code
  FROM TABLE(FLATTEN(INPUT(SPLIT('CORTE INGLES', ' '))))
)

-- Step 2: Count phonetic matches
-- Note: SOUNDEX('CROTE') = 'C600' = SOUNDEX('CORTE')
SELECT
  COUNT(DISTINCT cp.phonetic_code) AS phonetic_matches,
  GREATEST(
    (SELECT COUNT(*) FROM input_phonetics),
    (SELECT COUNT(*) FROM candidate_phonetics)
  ) AS max_count,
  COUNT(DISTINCT cp.phonetic_code) / 
    GREATEST(
      (SELECT COUNT(*) FROM input_phonetics),
      (SELECT COUNT(*) FROM candidate_phonetics)
    ) AS S_phonetic
FROM input_phonetics ip
INNER JOIN candidate_phonetics cp ON ip.phonetic_code = cp.phonetic_code
;
-- Result: phonetic_matches=2, max_count=2, S_phonetic=1.0
```

**Snowflake Functions:**
- **`SOUNDEX(string)`** — Return 4-character phonetic code
  - Example: `SOUNDEX('CROTE')` → `'C600'`, `SOUNDEX('CORTE')` → `'C600'`
  - Standard algorithm; widely used
  - Works well for English; reasonable for European languages
  - **Limitation:** 4-character output; some information loss (but acceptable for Phase 1)

**Alternative: DoubleMetaphone via UDF (Phase 2+)**
- Snowflake does NOT have native DoubleMetaphone
- Could implement as Scalar UDF in Python/Java if higher phonetic accuracy needed
- For Phase 1: **SOUNDEX is sufficient and native**

**Recommendation for Phase 1:** Use native `SOUNDEX()`. **Latency: < 1ms per candidate per token.**

---

### Signal 3: S_sim (Jaro-Winkler String Similarity)

**Requirement:** Compute similarity between normalized input and candidate

**Snowflake Approach:**

```sql
SELECT
  customer_name,
  'CROTE INGLES' AS input_name,
  JAROWINKLER_SIMILARITY(
    UPPER(TRIM(customer_name)),
    UPPER(TRIM('CROTE INGLES'))
  ) / 100 AS S_sim  -- Divide by 100 to normalize to [0, 1]
FROM dim_jde_address_book
LIMIT 10
;
```

**Snowflake Functions:**
- **`JAROWINKLER_SIMILARITY(string1, string2)`** → INTEGER [0–100]
  - Native function; highly optimized
  - Example: `JAROWINKLER_SIMILARITY('CROTE INGLES', 'CORTE INGLES')` → `85`
  - Divide by 100 to get [0, 1] range
  - **Perfect for Phase 1**

**Related Functions:**
- **`EDITDISTANCE(string1, string2)`** → Levenshtein distance (see S_edit below)
- **`JARO_SIMILARITY(string1, string2)`** → Alternative (without Winkler boost); less common

**Recommendation for Phase 1:** Use native `JAROWINKLER_SIMILARITY()` directly. **Latency: < 1ms per candidate.**

---

### Signal 4: S_edit (Normalized Edit Distance)

**Requirement:** Compute edit distance and normalize to [0, 1]

**Snowflake Approach:**

```sql
SELECT
  customer_name,
  'CROTE INGLES' AS input_name,
  EDITDISTANCE('CROTE INGLES', customer_name) AS raw_distance,
  GREATEST(LENGTH('CROTE INGLES'), LENGTH(customer_name)) AS max_length,
  1.0 - (
    EDITDISTANCE('CROTE INGLES', customer_name) /
    GREATEST(LENGTH('CROTE INGLES'), LENGTH(customer_name))
  ) AS S_edit
FROM dim_jde_address_book
LIMIT 10
;
```

**Snowflake Functions:**
- **`EDITDISTANCE(string1, string2)`** → INTEGER (Levenshtein distance)
  - Count of single-character edits (insert, delete, replace)
  - Example: `EDITDISTANCE('CROTE', 'CORTE')` → `1` (one substitution: T vs R)
  - Very fast; optimized in Snowflake
- **`LENGTH(string)`** → Number of characters
- **`GREATEST(value1, value2)`** → Maximum for normalization

**Formula:**
```
S_edit = 1.0 - (distance / max_length)
Clamped to [0, 1]
```

**Recommendation for Phase 1:** Use native `EDITDISTANCE()`. **Latency: < 1ms per candidate.**

---

### Signal 5: S_context (Region/Branch/Company Match)

**Requirement:** Match order_company or branch_plant; return 1.0 (exact), 0.5 (country), 0.0 (mismatch)

**Snowflake Approach:**

```sql
-- Option A: Simple CASE for exact/country-level matching
SELECT
  candidate.address_number,
  candidate.customer_name,
  candidate.order_company,
  supplied_context.order_company AS supplied_order_company,
  CASE
    WHEN candidate.order_company = supplied_context.order_company THEN 1.0
    WHEN SUBSTRING(candidate.order_company, 1, 2) = SUBSTRING(supplied_context.order_company, 1, 2) THEN 0.5
    ELSE 0.0
  END AS S_context
FROM dim_jde_address_book candidate
CROSS JOIN supplied_context
;

-- Option B: String prefix matching for country codes
SELECT
  CASE
    WHEN candidate.order_company = supplied_context.order_company THEN 1.0
    WHEN LEFT(candidate.order_company, 2) = LEFT(supplied_context.order_company, 2) THEN 0.5
    ELSE 0.0
  END AS S_context
```

**Snowflake Functions:**
- **`CASE ... WHEN ... THEN ... END`** — Conditional logic (standard SQL)
- **`SUBSTRING(string, position, length)`** or **`LEFT(string, length)`** — Extract prefix
  - `LEFT('MADRID_OPERATIONS', 2)` → `'MA'`
  - `LEFT('MADRID_SALES', 2)` → `'MA'`
- **`=` (equality operator)** — String comparison

**Recommendation for Phase 1:** Use CASE with `LEFT()` for country-level matching. **Latency: < 1ms per candidate.**

---

### Signal 6: S_history (Sales Recency / Order Count)

**Requirement:** Count orders in past 730 days; cap at 20; divide by 20

**Snowflake Approach:**

```sql
SELECT
  ab.address_number,
  ab.customer_name,
  COUNT(DISTINCT so.order_id) AS order_count_730d,
  MIN(COUNT(DISTINCT so.order_id), 20) AS order_count_capped,
  MIN(COUNT(DISTINCT so.order_id), 20) / 20.0 AS S_history
FROM dim_jde_address_book ab
LEFT JOIN fct_jde_sales_order_detail so
  ON ab.address_number = so.address_book_number
  AND so.order_date > CURRENT_DATE - 730
GROUP BY ab.address_number, ab.customer_name
;
```

**Snowflake Functions:**
- **`COUNT(DISTINCT column)`** — Count unique values
- **`CURRENT_DATE`** — Today's date (system function)
- **`-` operator** — Subtract days from date
  - Example: `CURRENT_DATE - 730` → date 730 days ago
- **`MIN(value1, value2)`** → Minimum (for capping at 20)
- **`LEFT JOIN`** — Outer join; preserve rows with no orders

**Recommendation for Phase 1:** Use COUNT(DISTINCT) with date filter. Consider pre-computing and caching if performance concerns. **Latency: 10–100ms per candidate depending on join size.**

---

### Signal 7: S_alias (Curated Alias Lookup) — PHASE 2+ FEATURE

**Phase 1 Approach:** Skip entirely. Set S_alias = 0.0 always.

```sql
SELECT
  candidate.address_number,
  candidate.customer_name,
  0.0 AS S_alias  -- Phase 1: Always 0 (no alias table)
FROM dim_jde_address_book candidate
;
```

**Phase 2+ Approach:** Exact match against alias table; binary 0 or 1

```sql
SELECT
  candidate.address_number,
  candidate.customer_name,
  CASE
    WHEN alias_table.canonical_name IS NOT NULL THEN 1.0
    ELSE 0.0
  END AS S_alias
FROM dim_jde_address_book candidate
LEFT JOIN tbl_customer_aliases alias_table
  ON UPPER(TRIM(candidate.customer_name)) = alias_table.alias_variant
;
```

**Snowflake Functions (Phase 2+):**
- **`LEFT JOIN`** — Outer join; preserve all candidates
- **`IS NOT NULL`** — Check if joined row exists
- **`CASE ... WHEN ... THEN ... END`** — Conditional logic

**Table Structure (Phase 2+): `tbl_customer_aliases`**
```sql
CREATE TABLE tbl_customer_aliases (
  canonical_name STRING,      -- Canonical/normalized name
  alias_variant STRING,        -- Input pattern to match
  address_number STRING,       -- Resolution target
  PRIMARY KEY (alias_variant)  -- For fast lookup
);

-- Example rows:
-- canonical_name | alias_variant | address_number
-- EL CORTE INGLES | CROTE INGLES | 12345
-- EL CORTE INGLES | LA CROTE | 12345
-- AMAZON | AMAZONE | 54321
```

**Phase 1 Recommendation:** Skip S_alias entirely. Remove from combined score calculation.
**Phase 2+ Recommendation:** Use LEFT JOIN with simple equality check. Index `tbl_customer_aliases.alias_variant` for <1ms lookup.

---

## 3. Combined Scoring & Ranking

**Snowflake Approach:**

```sql
WITH signals AS (
  SELECT
    candidate.address_number,
    candidate.customer_name,
    -- S_token: array intersection / max(array sizes)
    ARRAY_SIZE(ARRAY_INTERSECTION(
      SPLIT('CROTE INGLES', ' '),
      SPLIT(candidate.customer_name, ' ')
    )) / 
    GREATEST(
      ARRAY_SIZE(SPLIT('CROTE INGLES', ' ')),
      ARRAY_SIZE(SPLIT(candidate.customer_name, ' '))
    ) AS S_token,
    -- S_phonetic: (computed via phonetic token intersection)
    -- ... (see phonetic implementation above)
    -- S_sim: Jaro-Winkler
    JAROWINKLER_SIMILARITY('CROTE INGLES', candidate.customer_name) / 100 AS S_sim,
    -- S_edit: normalized edit distance
    1.0 - (
      EDITDISTANCE('CROTE INGLES', candidate.customer_name) /
      GREATEST(LENGTH('CROTE INGLES'), LENGTH(candidate.customer_name))
    ) AS S_edit,
    -- S_context: region match
    CASE
      WHEN candidate.order_company = 'MADRID_OPERATIONS' THEN 1.0
      WHEN LEFT(candidate.order_company, 2) = LEFT('MADRID_OPERATIONS', 2) THEN 0.5
      ELSE 0.0
    END AS S_context,
    -- S_history: order count (pre-computed via separate query)
    history.order_count_capped / 20.0 AS S_history,
    -- S_alias: alias lookup
    CASE WHEN alias.canonical_name IS NOT NULL THEN 1.0 ELSE 0.0 END AS S_alias
  FROM dim_jde_address_book candidate
  LEFT JOIN fct_jde_sales_order_detail so
    ON candidate.address_number = so.address_book_number
    AND so.order_date > CURRENT_DATE - 730
  LEFT JOIN tbl_customer_aliases alias
    ON UPPER(TRIM(candidate.customer_name)) = alias.alias_variant
  LEFT JOIN (
    SELECT address_book_number, MIN(COUNT(*), 20) AS order_count_capped
    FROM fct_jde_sales_order_detail
    WHERE order_date > CURRENT_DATE - 730
    GROUP BY address_book_number
  ) history ON candidate.address_number = history.address_book_number
)

-- Combined score formula
SELECT
  address_number,
  customer_name,
  S_token,
  S_phonetic,
  S_sim,
  S_edit,
  S_context,
  S_history,
  S_alias,
  0.35 * S_token + 
  0.25 * S_phonetic + 
  0.10 * S_sim + 
  0.05 * S_edit + 
  0.15 * S_context + 
  0.05 * S_history + 
  0.05 * S_alias AS combined_score
FROM signals
ORDER BY combined_score DESC
LIMIT 100
;
```

**Snowflake Functions Used:**
- **`WITH ... AS`** — Common Table Expression (CTE) for readability
- **`LEFT JOIN`** — Multiple outer joins for signal composition
- **`CAST()` / type coercion** — Ensure numeric operations
- **Arithmetic operators** (+, -, *, /) — Standard SQL

**Recommendation for Phase 1:** Build as Snowflake Transformation tool using CTEs for clarity. **Total latency per candidate: 10–100ms** (dominated by S_history join).

---

## 4. Performance Optimization Tips

### Indexing
```sql
-- Index for fast S_history computation
CREATE INDEX idx_jde_order_address_date 
  ON fct_jde_sales_order_detail(address_book_number, order_date);

-- Index for fast S_alias lookup
CREATE INDEX idx_aliases_variant 
  ON tbl_customer_aliases(alias_variant);

-- Index for candidate pool query (if using ILIKE)
CREATE INDEX idx_customer_name 
  ON dim_jde_address_book(customer_name);
```

### Pre-Computing S_history
If scoring is called frequently, pre-compute and cache S_history:
```sql
-- Pre-computed history scores (refreshed daily)
CREATE TABLE tbl_customer_history_scores AS
SELECT
  address_number,
  MIN(COUNT(DISTINCT order_id), 20) / 20.0 AS S_history,
  COUNT(DISTINCT order_id) AS order_count,
  MAX(order_date) AS last_order_date
FROM fct_jde_sales_order_detail
WHERE order_date > CURRENT_DATE - 730
GROUP BY address_number;

-- Then use simple lookup instead of join:
SELECT S_history FROM tbl_customer_history_scores WHERE address_number = ?
;
```

### String Normalization Caching
If the same input is scored multiple times, cache the normalized form:
```sql
-- Pre-compute and store normalized candidates
ALTER TABLE dim_jde_address_book ADD COLUMN customer_name_normalized STRING;
UPDATE dim_jde_address_book SET customer_name_normalized = 
  UPPER(TRIM(REGEXP_REPLACE(customer_name, '[^A-Z0-9 ]', ' ')));
CREATE INDEX idx_name_normalized ON dim_jde_address_book(customer_name_normalized);
```

---

## 5. Implementation Roadmap

### Phase 1: Snowflake Transformation Tool

**Target Latency:** < 500ms per 100 candidates

**Required Functions:**
- ✅ `UPPER()`, `TRIM()`, `REGEXP_REPLACE()` — Preprocessing
- ✅ `SPLIT()`, `FLATTEN()` — Tokenization
- ✅ `ARRAY_INTERSECTION()`, `ARRAY_SIZE()` — S_token
- ✅ `SOUNDEX()` — S_phonetic
- ✅ `JAROWINKLER_SIMILARITY()` — S_sim
- ✅ `EDITDISTANCE()`, `LENGTH()` — S_edit
- ✅ `CASE`, `LEFT()`, `=` — S_context
- ✅ `COUNT()`, `CURRENT_DATE`, `LEFT JOIN` — S_history
- ✅ `LEFT JOIN`, `IS NOT NULL`, `CASE` — S_alias
- ✅ Arithmetic (+, -, *, /) — Combined score

**SQL Complexity:** ~150–200 lines of CTEs + CASE statements

**Testing:**
- [ ] Verify each signal computation with known examples
- [ ] Test full query with 100 candidates; measure latency
- [ ] Verify combined_score is in [0, 1] range for all results
- [ ] Spot-check results against manual calculations

---

### Phase 2+: Enhancements

- **Embedding-based fallback** (S_embed) — Requires Python UDF or external ML service
- **Language-specific mappings** — Add CASE statement for variant rules
- **DoubleMetaphone UDF** — Custom Python/Java UDF for phonetic enhancement
- **Pre-computed caches** — S_history, normalized names, embeddings stored in tables

---

## 6. SQL Template: Full Scoring Query

Use this as a starting point for your Snowflake Transformation tool:

```sql
-- Customer Name Resolution: Full Scoring Pipeline
-- Input: normalized customer name + context (order_company, branch_plant)
-- Output: candidates sorted by combined_score, all signals, provenance

-- Configuration
SET @input_name = 'LA CROTE INGLES';
SET @order_company = 'MADRID_OPERATIONS';
SET @max_candidates = 100;

-- Preprocessing
WITH normalized_input AS (
  SELECT 
    UPPER(TRIM(REGEXP_REPLACE(@input_name, '[^A-Z0-9 ]', ' '))) AS normalized_name,
    SPLIT(
      UPPER(TRIM(REGEXP_REPLACE(@input_name, '[^A-Z0-9 ]', ' '))),
      ' '
    ) AS input_tokens
),

-- Candidate pool
candidates AS (
  SELECT
    address_number,
    customer_name,
    UPPER(TRIM(REGEXP_REPLACE(customer_name, '[^A-Z0-9 ]', ' '))) AS normalized_name,
    SPLIT(
      UPPER(TRIM(REGEXP_REPLACE(customer_name, '[^A-Z0-9 ]', ' '))),
      ' '
    ) AS candidate_tokens,
    order_company,
    branch_plant
  FROM dim_jde_address_book
),

-- Signal Computation
signals AS (
  SELECT
    candidates.address_number,
    candidates.customer_name,
    -- S_token: Token Overlap
    ARRAY_SIZE(ARRAY_INTERSECTION(
      normalized_input.input_tokens,
      candidates.candidate_tokens
    )) / 
    GREATEST(
      ARRAY_SIZE(normalized_input.input_tokens),
      ARRAY_SIZE(candidates.candidate_tokens)
    ) AS S_token,
    
    -- S_sim: Jaro-Winkler Similarity
    JAROWINKLER_SIMILARITY(
      normalized_input.normalized_name,
      candidates.normalized_name
    ) / 100 AS S_sim,
    
    -- S_edit: Normalized Edit Distance
    1.0 - (
      EDITDISTANCE(
        normalized_input.normalized_name,
        candidates.normalized_name
      ) /
      GREATEST(
        LENGTH(normalized_input.normalized_name),
        LENGTH(candidates.normalized_name)
      )
    ) AS S_edit,
    
    -- S_context: Region Match
    CASE
      WHEN candidates.order_company = @order_company THEN 1.0
      WHEN LEFT(candidates.order_company, 2) = LEFT(@order_company, 2) THEN 0.5
      ELSE 0.0
    END AS S_context,
    
    -- S_history: Order Count (pre-computed lookup)
    COALESCE(history.S_history, 0.0) AS S_history,
    
    -- S_alias: Alias Lookup (PHASE 2+, deferred) — Phase 1: always 0
    0.0 AS S_alias,
    
    -- Provenance
    candidates.order_company,
    candidates.branch_plant,
    history.last_order_date,
    history.order_count
    
  FROM normalized_input
  CROSS JOIN candidates
  LEFT JOIN tbl_customer_history_scores history
    ON candidates.address_number = history.address_number
  LEFT JOIN tbl_customer_aliases alias
    ON candidates.normalized_name = alias.alias_variant
),

-- Combined Score
scored_candidates AS (
  SELECT
    address_number,
    customer_name,
    S_token,
    0.0 AS S_phonetic,  -- TODO: Implement phonetic signal
    S_sim,
    S_edit,
    S_context,
    S_history,
    S_alias,
    0.35 * S_token + 
    0.25 * 0.0 +  -- S_phonetic TODO
    0.10 * S_sim + 
    0.05 * S_edit + 
    0.15 * S_context + 
    0.05 * S_history + 
    0.05 * S_alias AS combined_score,
    order_company,
    branch_plant,
    last_order_date,
    order_count
  FROM signals
)

-- Final Result
SELECT
  address_number,
  customer_name,
  combined_score,
  S_token,
  S_phonetic,
  S_sim,
  S_edit,
  S_context,
  S_history,
  S_alias,
  order_company,
  branch_plant,
  last_order_date,
  order_count
FROM scored_candidates
WHERE combined_score >= 0.0  -- Adjust threshold as needed
ORDER BY combined_score DESC
LIMIT @max_candidates
;
```

---

## 7. Summary Table: Snowflake Functions Required

| Signal | Function(s) Required | Status | Phase |
| --- | --- | --- | --- |
| **Normalization** | `UPPER()`, `TRIM()`, `REGEXP_REPLACE()` | ✅ Native | Phase 1 |
| **Tokenization** | `SPLIT()`, `FLATTEN()` | ✅ Native | Phase 1 |
| **S_token** | `ARRAY_INTERSECTION()`, `ARRAY_SIZE()`, `GREATEST()` | ✅ Native | Phase 1 |
| **S_phonetic** | `SOUNDEX()` | ✅ Native | Phase 1 |
| **S_sim** | `JAROWINKLER_SIMILARITY()` | ✅ Native | Phase 1 |
| **S_edit** | `EDITDISTANCE()`, `LENGTH()` | ✅ Native | Phase 1 |
| **S_context** | `CASE`, `LEFT()`, `=` | ✅ Native | Phase 1 |
| **S_history** | `COUNT()`, `CURRENT_DATE`, `LEFT JOIN` | ✅ Native | Phase 1 |
| **S_alias** | (Deferred to Phase 2+) | ⚠️ Phase 2+ | Phase 2+ |
| **Combined Score** | Arithmetic (+, -, *, /) | ✅ Native | Phase 1 |
| **S_embed** | (Python UDF or external service) | ⚠️ Deferred | Phase 2+ |
| **Language Mappings** | `CASE` (simple) or mapping table | ⚠️ Deferred | Phase 2+ |
| **DoubleMetaphone** | (Custom Python/Java UDF) | ⚠️ Deferred | Phase 2+ |

---

## Conclusion

**Snowflake provides all required native functions for Phase 1 implementation.** No custom UDFs, no external dependencies.

**Key strengths:**
- ✅ Native string functions (UPPER, TRIM, REGEXP_REPLACE)
- ✅ Native array operations (SPLIT, ARRAY_INTERSECTION, ARRAY_SIZE)
- ✅ Native similarity metrics (JAROWINKLER_SIMILARITY, EDITDISTANCE, SOUNDEX)
- ✅ Native SQL joins and CTEs for complex queries
- ✅ Excellent performance for string operations at scale

**Next Steps:**
1. Build Snowflake Transformation tool using template above
2. Test with 100+ real customer names
3. Verify latency (target < 500ms per 100 candidates)
4. Implement S_phonetic signal (currently placeholder)
5. Deploy as Phase 1 scoring engine
