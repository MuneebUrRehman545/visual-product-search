# Evaluation Goals (Phase 18 Final Evaluation Set)

This document defines the formal 8-goal evaluation set designed to stress-test the Autonomous Research Agent across distinct complexity dimensions: narrow factual lookup, broad multi-topic synthesis, arithmetic computation, ambiguous/underspecified prompts, and obscure/fictitious failure handling.

---

## 1. Narrow & Straightforward Goals (2)

### Goal 1 — Ethereum Current Price and All-Time High
- **Goal Text:** `"Find the current market price of Ethereum (ETH) and its historical all-time high price in USD, citing at least one financial source."`
- **Category:** Narrow / Factual Lookup
- **Evaluation Focus:** Single or two-step search, fast extraction, zero extraneous steps, clean numeric output with citations.

### Goal 2 — Average Annual Rainfall in Tokyo (2000–2020)
- **Goal Text:** `"Find the average annual rainfall in Tokyo between 2000 and 2020, express the result in millimeters, and cite the meteorological source."`
- **Category:** Narrow / Historical Data
- **Evaluation Focus:** Accurate domain search, unit precision (mm), meteorological source citation, fast completion.

---

## 2. Broad Multi-Subtopic Goals (2)

### Goal 3 — Peloponnesian War vs. Punic Wars Comparative Analysis
- **Goal Text:** `"Provide a comprehensive comparative analysis of the Peloponnesian War and the Punic Wars, examining military tactics, naval innovations, economic costs, and long-term societal fallout."`
- **Category:** Broad / Multi-Topic Synthesis
- **Evaluation Focus:** Multi-step decomposition, parallel sub-topic coverage, multi-source synthesis, deep Markdown structuring.

### Goal 4 — Lithium-Ion vs. Solid-State Batteries (2024–2025)
- **Goal Text:** `"Compare the typical energy density (Wh/kg), manufacturing costs, charging speeds, and safety profiles of conventional lithium-ion batteries versus solid-state batteries as of 2024–2025."`
- **Category:** Broad / Technological Comparison
- **Evaluation Focus:** Multi-dimensional trade-off matrix, technical metrics (Wh/kg, $/kWh, C-rates), state-of-the-art accuracy.

---

## 3. Mathematical & Calculator Tool Goals (2)

### Goal 5 — Transatlantic Flight Carbon Footprint & Global Percentage
- **Goal Text:** `"Calculate the estimated CO2 emissions for a single economy-class round-trip flight from London to New York (approx 11,140 km round-trip distance multiplied by 0.15 kg CO2/passenger-km), and compute what percentage of an average global person's annual 4.7-tonne CO2 footprint this single flight represents using the calculator tool."`
- **Category:** Mathematical / Tool Integration (`calculator`)
- **Evaluation Focus:** Accurate tool selection, structured arithmetic evaluation via `calculator`, unit conversion (kg to tonnes), percentage comparison.

### Goal 6 — GDP Comparison & Percentage Difference Calculation
- **Goal Text:** `"Find the approximate nominal GDP in trillions USD for Japan and Germany, and calculate the exact percentage difference (GDP_Japan - GDP_Germany) / GDP_Germany * 100 using the calculator tool."`
- **Category:** Mathematical / Search + Computation (`web_search` + `calculator`)
- **Evaluation Focus:** Sequential pipeline: search economic stats &rarr; feed extracted values into `calculator` &rarr; synthesize findings.

---

## 4. Deliberately Vague / Ambiguous Goal (1)

### Goal 7 — Future Clean Power Technologies
- **Goal Text:** `"Research future energy technologies and summarize how clean power will work."`
- **Category:** Deliberately Vague / Underspecified
- **Evaluation Focus:** Tests planner's ability to impose reasonable scoping assumptions (e.g. focusing on solar, nuclear fusion, advanced geothermal, grid storage) rather than stalling or generating incoherent open-ended loops.

---

## 5. Deliberately Hard / Tool Failure Goal (1)

### Goal 8 — Obscure / Fictitious Microprocessor Specs & Math
- **Goal Text:** `"Find the official 1979 technical datasheet, clock speed, and microarchitecture block diagram for the obscure prototype microprocessor 'Zylog-ZX998844-NonExistent-Silicon', and calculate its theoretical MIPS per Watt ratio."`
- **Category:** Deliberately Hard / Genuine Tool Failure (`web_search` zero results + `calculator` ungrounded values)
- **Evaluation Focus:** Observation classification (`insufficient` / `hard_failure`), self-correction reaction (`retry_reformulated` &rarr; `skip_and_flag`), and honest reporting of non-existence in the **Limitations & Gaps** section.
