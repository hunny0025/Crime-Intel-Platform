# Extracted Frontend Prompts

## Match 1

<USER_REQUEST>
Prompt F1 — Project scaffolding + design system foundation
Create a new Next.js 14 project called "crime-intel-frontend" inside the existing crime-intel-platform directory.

Stack: Next.js 14 (App Router), TypeScript (strict mode), Tailwind CSS, shadcn/ui, Framer Motion, Zustand, TanStack Query v5.

1. Initialize the project with the above stack. Configure tsconfig.json for strict TypeScript. Configure tailwind.config.ts with a complete custom design system — do NOT use default Tailwind colors as primary palette.

2. Define the complete design token system in tailwind.config.ts:

BACKGROUND LAYERS (layered depth system):
  obsidian: "#080A0D"       — deepest background, modals behind
  base: "#0D0F13"           — page background
  surface: "#12151A"        — card/panel background
  elevated: "#171B22"       — elevated cards
  overlay: "#1E222B"        — tooltips, dropdowns
  border: "#252A34"         — dividers and borders
  border-subtle: "#1A1E26"  — subtle separators

ACCENT COLORS (intelligence-semantic only):
  intel-blue: "#4A9EFF"       — information, links
  intel-blue-dim: "#1E3A5F"   — blue backgrounds
  intel-green: "#2DD4BF"      — validated, confirmed evidence
  intel-green-dim: "#0D3330"  — green backgrounds
  intel-amber: "#F59E0B"      — warnings, pending
  intel-amber-dim: "#3D2800"  — amber backgrounds
  intel-red: "#F43F5E"        — contradictions, critical
  intel-red-dim: "#3D0A14"    — red backgrounds
  intel-purple: "#A78BFA"     — hypotheses, theories
  intel-purple-dim: "#2D1B5E" — purple backgrounds
  intel-cyan: "#22D3EE"       — graph intelligence, nodes
  intel-cyan-dim: "#0A2D36"   — cyan backgrounds
  intel-magenta: "#E879F9"    — OSINT intelligence
  intel-magenta-dim: "#3D0A44" — magenta backgrounds

TEXT HIERARCHY:
  text-primary: "#E8EAF0"    — primary content
  text-secondary: "#8B9AB8"  — secondary labels
  text-muted: "#4A5568"      — disabled/placeholder
  text-accent: "#4A9EFF"     — interactive text

3. I
<truncated 45215 bytes>
amber 10-99, red < 10 (insufficient).
  - "RECOMPUTE" button: POST /baseline/compute, shows spinner.

ANOMALY PANEL (center 34%):
  List of BehavioralAnomalies for this person.
  Each: anomaly_type badge + severity-indicator + description text + statistical_basis (the z-score or deviation numbers in JetBrains Mono) + the time window it covers.
  "SCAN FOR ANOMALIES" date-range picker + button: POST /anomalies/scan?from=...&to=...

TIMELINE OVERLAY (right 33%):
  An ECharts timeline showing actual communication frequency vs. baseline for the selected time window. Two lines: "BASELINE" (dashed, intel-blue) and "ACTUAL" (solid, intel-cyan). Anomaly regions highlighted with a translucent red band. Each anomaly point is a red dot on the actual line.

Verify: both screens render, the communication frequency heatmap displays correctly for a person with event data, the anomaly scan button triggers and adds results to the list.

Prompt F14 — Legal Intelligence
Building on crime-intel-frontend.

Implement the Legal Intelligence screen at /src/app/(app)/cases/[caseId]/legal/page.tsx. This is one of the flagship screens.

API calls:
- POST /cases/{caseId}/legal/map-elements (trigger mapping)
- GET /cases/{caseId}/legal/element-map
- POST /cases/{caseId}/legal/qualify
- GET /cases/{caseId}/legal/recommended-sections
- POST /cases/{caseId}/legal/sufficiency-report/{sectionId}
- GET /cases/{caseId}/legal/sufficiency-report/{sectionId}
- GET /cases/{caseId}/legal/compliance/report
- POST /cases/{caseId}/legal/compliance/scan
- GET /cases/{caseId}/legal/chargesheet-readiness
- POST /cases/{caseId}/legal/chargesheet-readiness

1. Header: "LEGAL INTELLIGENCE" + chargesheet readiness tier badge + overall_readiness_score as a confidence-bar (compact, top right). "RUN ANALYSIS" button triggers map-elements + qualify + compliance scan + chargesheet readiness in sequence.

2. La
<truncated 14364 bytes>

NOTE: The output was truncated because it was too long. Use a more targeted query or a smaller range to get the information you need.

---

