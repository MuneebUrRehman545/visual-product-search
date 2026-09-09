# Frontend Manual Test Checklist — Phase 5 & Phase 16

This document outlines the manual test scenarios to verify the Next.js frontend implementation for the Autonomous Research Agent, including Phase 16 real-time streaming dashboard, agent trace feed, plan status, and markdown report rendering.

---

## 1. Goal Submission & Navigation (Home Page)

- [ ] **Valid Goal Submission**
  1. Navigate to `http://localhost:3000/`.
  2. Enter a valid research goal in the textarea (e.g., *"What was the average annual rainfall in Tokyo between 2000 and 2020?"*).
  3. Click **Start Research**.
  4. Verify that the button shows a loading spinner and text (*"Starting Research..."*) while the request is in flight.
  5. Verify that upon backend response, the browser automatically navigates to `/runs/[run_id]`.

- [ ] **Empty Submission Blocking (Client-Side & Backend)**
  1. Leave the goal textarea empty (or type only spaces).
  2. Verify that the **Start Research** button is disabled or, if submitted, displays a clear error banner (*"Please enter a valid research goal."*).
  3. Verify that no `POST /runs` request is made or, if sent to backend with empty text, the backend's 422 error detail is parsed and displayed clearly to the user.

- [ ] **Backend Unreachable Error Handling**
  1. Stop the backend server or set `NEXT_PUBLIC_BACKEND_URL` to an unreachable port.
  2. Enter a valid research goal and click **Start Research**.
  3. Verify that a clear red error banner appears explaining that the backend server is unreachable.

---

## 2. Live Run Detail & Streaming Dashboard (`/runs/[id]`)

- [ ] **WebSocket Live Connection & Real-Time Trace Updates (No Manual Refresh)**
  1. Start a new research run and open `/runs/[run_id]`.
  2. Observe the top status indicator displaying `Live Stream` (pulsing green indicator).
  3. Verify that the trace feed automatically populates events in real time without clicking refresh:
     - `plan_created`: Checklist of initial formulated steps with tool assignments.
     - `step_started`: Step header with animated pulsing indicator.
     - `tool_call_started`: Tool name (e.g. `web_search`) with spinning indicator and input parameters.
     - `tool_call_result`: Green checkmark on success (or red X on failure) with collapsible preview of output.
     - `observation_made`: Colored classification badge (`success`, `insufficient`, `transient_failure`, `hard_failure`) and reasoning.
     - `step_completed`: Step status update.
  4. Verify auto-scrolling keeps the latest events in view, and scrolling up shows the "Jump to Latest" button.

- [ ] **Visually Distinct Self-Correction / Replan Events**
  1. Trigger or execute a run that encounters a replan/retry (e.g. invalid query or deliberate failure test).
  2. Verify that the `replan_triggered` event appears with a prominent, visually distinct amber/orange bordered banner.
  3. Verify that the banner explicitly displays the agent's strategy (`retry_same`, `retry_reformulated`, `skip_and_flag`), retry attempt count, and plain-English explanation of why it is self-correcting.

- [ ] **Live Plan Status View Checklist**
  1. Check the Plan Checklist column alongside the trace feed.
  2. Verify that each step dynamically updates its status (`pending` -> `in-progress` (spinner) -> `completed` (green checkmark) / `skipped`).
  3. Verify that the progress bar updates its percentage accordingly.

- [ ] **Markdown Research Report View & Limitations Section Highlight**
  1. When execution finishes and `report_ready` fires, switch to or view the **Report** tab.
  2. Verify that markdown headings, paragraphs, lists, bold text, code blocks, and tables render cleanly.
  3. Verify that any "Limitations" or "Caveats" section is styled with an amber callout box and an **Important** badge.
  4. Click **Copy Markdown** and confirm text is copied to clipboard.
  5. Click **Download .md** and confirm file downloads as `research-report-[id].md`.

- [ ] **Connection Resilience & Late Connection / Reconnection**
  1. Start a run via CLI or curl, wait 15 seconds, and open `/runs/[run_id]` in the browser.
  2. Verify that the `catch_up` event accurately populates past steps and tool calls in both the Plan checklist and Trace feed without duplication.
  3. Temporarily disconnect network or drop connection; verify the badge displays `Reconnecting...` and recovers automatically within 2.5s.

---

## 3. History Page (`/history`)

- [ ] **Polished Run Status Badges & Report Intro Preview**
  1. Navigate to `http://localhost:3000/history`.
  2. Verify all runs render with real colored status badges:
     - `Completed` (Emerald badge)
     - `In Progress` (Blue pulsing badge)
     - `Failed` (Rose badge)
     - `Pending` (Zinc badge)
  3. Verify that completed runs with reports display a one-line italicized preview snippet of the report summary below the goal text.
  4. Clicking any history card navigates to `/runs/[run_id]`.

---

## 4. Mobile Viewport Responsiveness (375px Viewport)

- [ ] **Mobile Trace Feed & Plan Checklist (375px)**
  1. Open Chrome DevTools and switch to responsive device mode at 375px width (e.g. iPhone SE).
  2. On `/runs/[id]`, verify:
     - The mobile tab switcher allows seamlessly toggling between **Live Trace Feed** and **Plan Checklist**.
     - Long tool names, input parameter JSON strings, and observation texts wrap properly (`break-words`) without horizontal page overflow.
     - Collapsible output cards ("Show more" / "Show less") allow expanding without breaking layout.
     - Report view renders within 375px with horizontal scroll for wide tables or code blocks.
