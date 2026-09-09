# Architecture Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Backend framework | Python + FastAPI | Fast async support, automatic OpenAPI docs, and strong ecosystem for LLM agent tooling. |
| Frontend framework | Next.js | React-based with built-in routing, SSR/SSG options, and first-class Vercel deployment. |
| LLM provider | Google Gemini API (free tier) | Generous free tier with capable multimodal models suitable for planning and synthesis. |
| Database | Supabase (PostgreSQL, free tier) | Managed Postgres with real-time subscriptions, auth, and a generous free tier for step logs. |
| Third tool (beyond web search + file I/O) | Calculator / math evaluation | Enables quantitative research tasks (statistics, unit conversion, formula verification) that pure text search cannot reliably solve. |
