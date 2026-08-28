# Vision Module Integration Contract (Week 4 Draft — Superseded)

> [!IMPORTANT]
> **CANONICAL CONTRACT LOCATION:**
> This document was the Day 1 preliminary proposal. It has been superseded by the **frozen Day 2 contract**:
> 👉 **[docs/integration/vision-rag-contract.md](file:///d:/visual-product-search/docs/integration/vision-rag-contract.md)**
>
> **Key Revisions in Frozen Contract:**
> 1. **Schema Cleanup:** Removed unapproved top-level fields (`producer`, `match_status`, `error` on success) to align with the team's standard JSON contract.
> 2. **Shared Database & Trace Handoff:** Added explicit schema fields for `extracted_data_id` and PostgreSQL persistence across `assets`, `extracted_data`, and `module_events`.
> 3. **Error Semantics:** Enforced standard HTTP status codes (`4xx`/`5xx`) for errors rather than returning HTTP 200 with error payloads.
> 4. **Strict `pipeline_run_id`:** Enforced orchestrator-supplied UUID with no fallback generation by Vision.
>
> Please refer exclusively to [docs/integration/vision-rag-contract.md](file:///d:/visual-product-search/docs/integration/vision-rag-contract.md) for implementation and testing.

---

## Historical Archive (Day 1 Proposal Reference)

For the canonical specification, see [docs/integration/vision-rag-contract.md](file:///d:/visual-product-search/docs/integration/vision-rag-contract.md).
