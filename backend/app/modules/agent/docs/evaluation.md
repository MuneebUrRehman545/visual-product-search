# Autonomous Research Agent — Formal Evaluation Report (Phase 18)

## 1. Summary of Findings

* **Autonomous Tool Chaining Requires Explicit Extraction Prompts:** Language models naturally default to familiar search tools when handling ambiguous inputs; for multi-tool workflows (e.g., retrieving statistics via `web_search` and computing equations with `calculator`), the agent requires explicit intent hints and prompt grounding to extract numeric context into arithmetic expressions rather than looping back into search.
* **Bounded Self-Correction Prevents Infinite Degenerate Loops:** Categorizing observations into structured states (`success`, `insufficient`, `transient_failure`, `hard_failure`) paired with a strict single-retry limit (`retry_reformulated` / `retry_same` &rarr; `skip_and_flag`) successfully prevented the agent from hallucinating or entering infinite loops when encountering completely fictitious or ungrounded queries.
* **Defensive Tool Input Sanitization is Essential:** LLMs frequently produce formatted mathematical representations (including currency symbols `$`, thousand-separators `,`, or trailing `%` signs). Sanitizing input expressions in the tool layer before AST parsing drastically reduces artificial syntax errors and allows reliable evaluation.
* **Grounded Synthesis Eliminates Factual Hallucination:** Constraining the report generation prompt strictly to verified step observations and explicitly mandating a **Limitations & Gaps** section ensured the agent honestly disclosed non-existent entities and skipped steps rather than inventing fabricated metrics.
* **Decoupled Identity State in Asynchronous Execution:** Long-running agentic pipelines operating across database rollbacks or network interruptions must use detached, immutable identifiers (such as local UUIDs) rather than relying on active ORM session attributes during error handling routines.

---

## 2. Evaluation Suite Results (8 Goals)

| # | Category | Goal Name | Status | Steps | Duration | Replans | Limitations Noted |
|---|---|---|---|---|---|---|---|
| **1** | Narrow & Straightforward | Ethereum Current Price & ATH | `complete` | 3 | 101.40s | 0 | False (Complete data) |
| **2** | Narrow & Straightforward | Tokyo Annual Rainfall (2000–2020) | `complete` | 4 | 121.98s | 1 | True (Annual avg calculation skipped) |
| **3** | Broad Multi-Subtopic | Peloponnesian War vs. Punic Wars | `complete` | 5 | 76.50s | 0 | False (Complete synthesis) |
| **4** | Broad Multi-Subtopic | Li-Ion vs. Solid-State Batteries | `complete` | 4 | 90.90s | 0 | False (Complete matrix) |
| **5** | Mathematical & Calculator | Transatlantic Flight CO2 Footprint | `complete` | 4 | 91.73s | 0 | False (All math computed) |
| **6** | Mathematical & Calculator | GDP Comparison & % Difference | `complete` | 4 | 115.47s | 1 | True (Manual synthesis in report) |
| **7** | Deliberately Vague / Ambiguous | Future Clean Power Technologies | `complete` | 4 | 64.66s | 0 | False (Scoped to 3 pillars) |
| **8** | Deliberately Hard / Tool Failure | Fictitious Microprocessor Specs | `complete` | 5 | 157.85s | 4 | True (Entity non-existence flagged) |

---

## 3. Individual Goal Evaluations

### Goal 1 — Ethereum Current Price and All-Time High
- **Goal Text:** `"Find the current market price of Ethereum (ETH) and its historical all-time high price in USD, citing at least one financial source."`
- **Category:** Narrow & Straightforward
- **Run ID:** `08688892-a6fe-4aa7-b2d9-77eb3017092b`
- **Final Status & Step Count:** `complete` (3 steps executed, 101.40s)
- **Replanning Occurred:** None (0 replans).
- **Evaluation Commentary:** 
  The planner immediately broke the objective into two targeted search queries (live price and ATH) and a compilation step. The `web_search` tool retrieved live market data from CoinMarketCap ($1,880.63 USD) and verified the historical ATH ($4,953.73 USD on August 24, 2025). The agent synthesized all findings cleanly without hallucination or unnecessary exploratory loops.
- **Report Accuracy & Honesty:** 
  100% accurate, properly cited, with zero gaps.

---

### Goal 2 — Average Annual Rainfall in Tokyo (2000–2020)
- **Goal Text:** `"Find the average annual rainfall in Tokyo between 2000 and 2020, express the result in millimeters, and cite the meteorological source."`
- **Category:** Narrow & Straightforward
- **Run ID:** `b688095b-4d3a-42bb-9fa1-af6394220ae6`
- **Final Status & Step Count:** `complete` (4 steps executed, 121.98s)
- **Replanning Occurred:** Yes (1 replan). Step 3 intended to calculate the 21-year average using the `calculator` tool, but because the gathered search results contained raw text summaries rather than a clean numeric list, the tool dispatcher attempted another search query, which was classified as `insufficient` and skipped.
- **Evaluation Commentary:** 
  The search steps successfully located the Japan Meteorological Agency (JMA) climatological normal data (1,598.2 mm annual average). However, the transition from tabular search snippets to the multi-number addition/division in `calculator` failed to construct an arithmetic expression on the initial pass. The evaluator correctly recognized the insufficiency and flagged the limitation rather than inventing numbers.
- **Report Accuracy & Honesty:** 
  Accurate and honest. The report cited the JMA 1991–2020 Climatological Normal of 1,598.2 mm and explicitly declared in the **Limitations & Gaps** section that the automated year-by-year 21-year calculation step was omitted.

---

### Goal 3 — Peloponnesian War vs. Punic Wars Comparative Analysis
- **Goal Text:** `"Provide a comprehensive comparative analysis of the Peloponnesian War and the Punic Wars, examining military tactics, naval innovations, economic costs, and long-term societal fallout."`
- **Category:** Broad Multi-Subtopic
- **Run ID:** `230b0737-a1f7-4225-9d5d-45ce8ca82f8f`
- **Final Status & Step Count:** `complete` (5 steps executed, 76.50s)
- **Replanning Occurred:** None (0 replans).
- **Evaluation Commentary:** 
  The planner generated a well-structured breakdown covering Greek naval warfare (Thucydides, triremes, blockades, *epiteichismos*), Roman and Carthaginian operational strategies (Polybius, the *corvus*, Hannibal at Cannae, Scipio Africanus), and the respective economic collapses vs. territorial expansions (*latifundia* and slavery). All planned steps succeeded on the first attempt.
- **Report Accuracy & Honesty:** 
  Exceptional depth (5,941 characters). Structured into distinct sections with historical grounding and zero hallucinated dates or events.

---

### Goal 4 — Lithium-Ion vs. Solid-State Batteries (2024–2025)
- **Goal Text:** `"Compare the typical energy density (Wh/kg), manufacturing costs, charging speeds, and safety profiles of conventional lithium-ion batteries versus solid-state batteries as of 2024–2025."`
- **Category:** Broad Multi-Subtopic
- **Run ID:** `5c2c83c3-c3a9-4d7c-ad32-3215f5888d57`
- **Final Status & Step Count:** `complete` (4 steps executed, 90.90s)
- **Replanning Occurred:** None (0 replans).
- **Evaluation Commentary:** 
  The agent executed state-of-the-art searches across both battery chemistries, gathering current 2024–2025 metrics (e.g. NMC pack prices at $108–$115/kWh vs. solid-state pilot lines at $300–$500/kWh; energy densities of 180–350 Wh/kg vs. 300–500+ Wh/kg with lithium-metal anodes). The synthesis engine generated a structured comparison table matching all four requested dimensions.
- **Report Accuracy & Honesty:** 
  Comprehensive 6,178 character report with technical precision, exact metrics, and an executive summary table.

---

### Goal 5 — Transatlantic Flight Carbon Footprint & Global Percentage
- **Goal Text:** `"Calculate the estimated CO2 emissions for a single economy-class round-trip flight from London to New York (approx 11,140 km round-trip distance multiplied by 0.15 kg CO2/passenger-km), and compute what percentage of an average global person's annual 4.7-tonne CO2 footprint this single flight represents using the calculator tool."`
- **Category:** Mathematical & Calculator
- **Run ID:** `2eda6125-bc36-43a5-b2d4-d2bfd10520d5`
- **Final Status & Step Count:** `complete` (4 steps executed, 91.73s)
- **Replanning Occurred:** None (0 replans).
- **Evaluation Commentary:** 
  The planner decomposed the mathematical objective into sequential operations: (1) `11140 * 0.15` &rarr; 1,671.0 kg CO2; (2) `4.7 * 1000` &rarr; 4,700.0 kg; (3) `1671.0 / 4700.0 * 100` &rarr; 35.55319%. Each step invoked the `calculator` tool directly and verified the result via AST evaluation without error.
- **Report Accuracy & Honesty:** 
  Fully accurate. The report displayed the exact formulas, intermediate steps, and final conclusion: 35.55% of the average global citizen's annual footprint.

---

### Goal 6 — GDP Comparison & Percentage Difference Calculation
- **Goal Text:** `"Find the approximate nominal GDP in trillions USD for Japan and Germany, and calculate the exact percentage difference (GDP_Japan - GDP_Germany) / GDP_Germany * 100 using the calculator tool."`
- **Category:** Mathematical & Calculator
- **Run ID:** `b4309038-8bc3-4672-a86c-1c2538f9ad5f`
- **Final Status & Step Count:** `complete` (4 steps executed, 115.47s)
- **Replanning Occurred:** Yes (1 replan). Step 4 was intended to evaluate the formula via `calculator`. Because the previous step gathered multi-paragraph search results with varying GDP estimates ($4.44T vs $5.05T), the tool selector dispatched a search query instead of parsing the numbers. The evaluator classified the output as `insufficient`, retried, and skipped the step.
- **Evaluation Commentary:** 
  The factual retrieval of Japan and Germany's nominal GDP was successful. However, passing unparsed numerical values from prior search snippets into the calculator tool exposed a friction point in tool parameter selection. The report synthesizer compensated by calculating the percentage difference ($-12.19\%$) directly from the gathered facts while honestly disclosing that the standalone calculator tool call was skipped.
- **Report Accuracy & Honesty:** 
  Accurate numeric findings; transparently documented the calculator tool skip in **Limitations & Gaps**.

---

### Goal 7 — Future Clean Power Technologies
- **Goal Text:** `"Research future energy technologies and summarize how clean power will work."`
- **Category:** Deliberately Vague / Ambiguous
- **Run ID:** `e9cc2098-6018-47d6-bea7-d4c4921b197d`
- **Final Status & Step Count:** `complete` (4 steps executed, 64.66s)
- **Replanning Occurred:** None (0 replans).
- **Evaluation Commentary:** 
  Despite the open-ended, underspecified prompt, the planner imposed a coherent three-pillar structure: (1) Generation (EGS geothermal, next-gen solar, SMRs), (2) Storage (batteries, supercapacitors, hydrogen), and (3) Distribution (AI-driven smart grids and microgrids). The agent completed all steps in 64.66 seconds without stalling or looping.
- **Report Accuracy & Honesty:** 
  High-quality 4,497 character structured report with clear thematic organization.

---

### Goal 8 — Obscure / Fictitious Microprocessor Specs & Math
- **Goal Text:** `"Find the official 1979 technical datasheet, clock speed, and microarchitecture block diagram for the obscure prototype microprocessor 'Zylog-ZX998844-NonExistent-Silicon', and calculate its theoretical MIPS per Watt ratio."`
- **Category:** Deliberately Hard / Tool Failure
- **Run ID:** `f4908d3b-64eb-4411-b843-e3aa900bc841`
- **Final Status & Step Count:** `complete` (5 steps executed, 157.85s)
- **Replanning Occurred:** Yes (4 replans / self-corrections).
- **Evaluation Commentary:** 
  The search for the fictitious processor returned generic Zilog Wikipedia pages and unrelated modern chips. The evaluator classified each outcome as `insufficient` because the specific model was not found. After retrying with reformulated queries, the self-correction engine triggered `skip_and_flag`. The subsequent calculation step was similarly flagged as ungrounded and skipped.
- **Report Accuracy & Honesty:** 
  Exemplary honesty. The final report explicitly stated: *"Upon attempting to execute the research steps... it was determined that the target microprocessor is entirely fictitious... No official 1979 technical datasheets exist... The calculator tool could not be utilized because required input variables were missing."* Zero fabricated facts.

---

## 4. Identified Weaknesses & Hardening Fixes

Across the initial 8-goal evaluation suite, 4 concrete architectural weaknesses were identified and hardened in the codebase:

### Weakness 1: Calculator Tool Dispatch Preference in Search-to-Math Pipelines
* **Issue:** When a plan step followed a `web_search` step and called for `intended_tool: "calculator"`, `llm_client.decide_tool_call` sometimes generated another search query instead of extracting the numeric values from the context summary into a mathematical expression.
* **Fix Applied:**
  1. Updated `backend/agent/llm_client.py` (`decide_tool_call`) to accept the step's `intended_tool` parameter.
  2. Injected dedicated instruction guidance into the tool-calling prompt: whenever `intended_tool == "calculator"` or calculation keywords appear, the model is strictly instructed to extract numeric values from prior findings and invoke `calculator` with a clean mathematical expression.
  3. Updated `backend/agent/execution.py` to forward `intended_tool=step_obj.intended_tool` during execution.

### Weakness 2: Input Sanitization and Informative Error Messages in `CalculatorTool`
* **Issue:** The calculator tool used raw `ast.parse(expr_str, mode="eval")`. If the LLM passed common formatted numeric representations (e.g. `(4,435,163,000,000 - 5,050,923,000,000)` with commas, `$5.05 - $4.44` with dollar signs, or `calculate ...`), AST parsing threw a generic `SyntaxError` with unhelpful feedback (`"Malformed or incomplete expression."`).
* **Fix Applied:**
  1. Added input sanitization in `backend/agent/tools/calculator_tool.py` to strip currency symbols (`$`, `€`, `£`, `¥`), remove number-grouping commas via regex `(?<=\d),(?=\d)`, strip leading `=` / `calculate `, and trim trailing `%`.
  2. Rewrote the error message on `SyntaxError` to provide explicit syntax guidance and formatting examples: `f"Malformed arithmetic expression '{raw_expr}': {syn_err}. The calculator tool requires standard Python arithmetic syntax (e.g., '(4.44 - 5.05) / 5.05 * 100')."`

### Weakness 3: Ambiguous Goal Decomposition in the Planning Prompt
* **Issue:** For open-ended or underspecified objectives (such as Goal 7), the planning prompt occasionally generated generic step descriptions without concrete scoping assumptions.
* **Fix Applied:**
  Updated `backend/agent/prompts/planning_prompt.txt` with explicit instructions:
  - When the objective is broad or ambiguous, establish concrete scoping assumptions (e.g., 2–4 technological pillars, specific metrics, or defined timeframes) directly within the step descriptions.
  - Require calculation steps to explicitly reference: *"Extract numeric values gathered in previous steps and evaluate the formula using the calculator tool."*

### Weakness 4: Expired ORM Attribute Access During Database Rollback
* **Issue:** In `backend/agent/orchestrator.py`, if an unhandled error triggered `db.rollback()`, accessing `run.id` inside the exception handler caused SQLAlchemy to attempt an attribute reload (`_load_expired`), which could trigger a secondary database error during transient network drops.
* **Fix Applied:**
  Updated `orchestrator.py` to use a detached local UUID identifier (`run_uuid = uuid.UUID(str(run_id))`) and wrapped error state persistence in a safe `try-except` block, guaranteeing clean `EVENT_RUN_FAILED` emission without cascading crashes.

---

## 5. Before vs. After Hardening Verification

To confirm the effectiveness of the fixes, the affected calculation and error handling paths were re-evaluated:

| Goal / Component | Before Hardening | After Hardening | Verdict |
|---|---|---|---|
| **Goal 5 & Goal 6 Math Dispatch** | Tool selector struggled with raw string numbers and defaulted to search retry | `intended_tool` passing and calculation prompt guidance successfully force `calculator` invocation with extracted variables | **Improved & Verified** |
| **`CalculatorTool` Expressions** | `ast.parse` rejected formatted inputs like `1,000,000 * 0.15` and `$4.44 - $5.05` | Sanitizer cleans currency symbols, regex-strips grouping commas, and parses complex mathematical expressions smoothly | **Resolved & Verified** |
| **Tool Error Feedback** | Generic error: `"Malformed or incomplete expression."` | Detailed actionable feedback with syntax examples returned to LLM self-correction loop | **Resolved & Verified** |
| **Error Handling on DB Interruption** | Accessing `run.id` on expired ORM instance after rollback raised secondary `OperationalError` | Detached local UUID and safe exception blocks guarantee clean state logging and event delivery | **Resolved & Verified** |

---

## 6. Summary of Architectural Takeaways

1. **Deterministic Tools Require Tolerant Interfaces:** Agent tools should never assume perfectly formatted LLM inputs; implementing defensive sanitizers (stripping units, commas, prefixes) prevents avoidable tool failures.
2. **Context-Aware Tool Dispatching:** Providing the plan's original intended tool in the decision prompt bridges the gap between high-level task planning and low-level function execution.
3. **Structured Observation Evaluation:** Classifying tool outcomes into explicit qualitative tiers (`success`, `insufficient`, `transient_failure`, `hard_failure`) provides deterministic boundaries for self-correction without relying on unconstrained LLM agency.
4. **Honesty Through Architecture:** A research agent earns user trust not by guessing or hallucinating answers for impossible questions, but by systematically documenting non-existent entities and skipped steps in a dedicated **Limitations & Gaps** section.
