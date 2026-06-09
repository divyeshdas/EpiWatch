# EpiWatch — Project Context (CLAUDE.md)

> Save this file at the **repo root**. Claude Code reads it automatically and uses it
> as persistent context for every prompt in this project. Do not rebuild this from
> scratch each session — refer back to it.

---

## 1. What EpiWatch is

EpiWatch is a **dual-pillar epidemic monitoring and emergency-response platform**.

- **Pillar A — Emergency Response (operational, real-time):** Given an emergency at a
  geographic location, compute the optimal route through a road-network graph and select
  the best hospital using a multi-factor scoring model.
- **Pillar B — Outbreak Surveillance (analytical + real-time):** Ingest historical and
  recent disease-outbreak data, visualize it interactively, cluster outbreaks into
  geographic hotspots, and detect abnormal spikes that raise alerts.

### The spine that makes it ONE platform (most important design decision)

The two pillars are connected by an **event bus**. Surveillance detection feeds routing:

```
Pillar B detects an outbreak hotspot / spike in Region X
      → emits event: OutbreakDetected { region, severity }
Pillar A's hospital scorer consumes it
      → hospitals in/near Region X get a "surge penalty" in their score
      → ambulances are routed away from soon-to-be-saturated hospitals, ahead of the surge
```

This is the headline narrative: **surveillance-aware emergency routing.** Neither pillar
reaches into the other's code — they only communicate through events. Preserve this
boundary strictly.

### Framing / data reality

This is a **coordination platform**, not a data scraper. Hospitals are *data providers*:
they (in a real deployment) authenticate and update their own bed/ICU/capacity/specialization
state. An admin operates the system and can simulate emergencies. The system reads live DB
state and optimizes on top of it. For development, data is **seeded and simulated** — this is
explicitly hypothetical, and that framing is fine and realistic (mirrors real systems like
EMResource). Do not pretend to have live hospital feeds.

---

## 2. Stack (fixed — do not substitute)

| Layer            | Choice                                              |
|------------------|-----------------------------------------------------|
| Backend          | Python 3.11+, FastAPI (async)                       |
| Frontend         | SvelteKit + TypeScript                              |
| Charts           | Apache ECharts                                      |
| Database         | PostgreSQL (relational + geo coordinates)           |
| Cache            | Redis                                               |
| Background jobs  | Celery (Redis broker)                               |
| Real-time        | WebSockets + Redis Pub/Sub                          |
| Event bus        | In-process pub/sub abstraction, **swappable** for Kafka later |
| Infra (dev)      | Docker Compose (Postgres + Redis + app)             |

Backend (FastAPI) and frontend (SvelteKit) are a clean, justified split — this is normal
architecture, not a messy polyglot.

---

## 3. Algorithms / DSA inventory (implement from scratch — no routing libraries)

| Concept                         | Used for                          | Pillar |
|---------------------------------|-----------------------------------|--------|
| Weighted graph (adjacency list) | Road network                      | A      |
| K-D tree                        | Nearest-node lookup from a coord  | A      |
| Min-heap / priority queue       | Dijkstra & A* frontier            | A      |
| Dijkstra's algorithm            | Shortest-path baseline            | A      |
| A* + Haversine heuristic        | Optimized routing                 | A      |
| Config-driven weighted scoring  | Hospital selection (triage)       | A      |
| Union-Find / DBSCAN             | Outbreak hotspot clustering       | B      |
| Sliding window + z-score        | Spike / anomaly detection         | B      |
| Event-driven pub/sub            | The spine connecting A ↔ B        | both   |

**Every algorithm must have documented time & space complexity** in a docstring or comment.
Dijkstra and A* must be **benchmarked against each other** on the same graph.

### Hospital scoring model (Pillar A core)

1. **Filter** candidates first: reachable via graph, travel_time ≤ threshold,
   beds available (and ICU available if patient is critical).
2. **Normalize** each factor to [0,1] (travel time, bed availability, ICU availability,
   load factor, specialization match).
3. **Weighted score**, where weights are **config-driven and change by patient condition**
   (critical → prioritize ICU + speed; stable → prioritize load-balancing; cardiac →
   prioritize specialization). Weights live in a config file, not hardcoded in logic.
4. Return ranked candidates with a **breakdown of why** (per-factor contribution) so the
   selection is explainable, not a black box.

---

## 4. Real-time first (architecture principle)

The event bus + WebSocket backbone is built in **Phase 0**, before features. Everything
added later just emits into it. Target: changes propagate to all connected clients quickly
(reference point: sub-100ms broadcast, similar to a Redis Pub/Sub + WebSocket fan-out).

Events (initial set): `HospitalUpdated`, `EmergencyReported`, `AmbulanceAssigned`,
`RouteComputed`, `OutbreakDetected`, `HotspotRecomputed`, `AlertGenerated`.

---

## 5. Design philosophy (frontend) — avoid the "AI-generated" look

The app is a **command center / operations console**, not a marketing landing page.
This aesthetic is domain-appropriate and naturally avoids AI-frontend clichés.

**Banned (these are AI-frontend tells):**
- Purple/indigo gradient hero, big centered headline
- Three equal "feature cards" with emoji icons
- Everything `rounded-2xl shadow-lg` floating in oceans of whitespace
- Emoji in headers; decorative motion with no meaning

**Required direction:**
- **Information density over whitespace** — map + live emergency table + alert feed visible together.
- **Dark, muted base**; color used *meaningfully* — severity scale green→amber→red maps to
  LOW→MEDIUM→HIGH→CRITICAL, never decorative.
- **Asymmetry and intentional hierarchy**, not stacked identical cards.
- **Motion follows data, never decoration.** Every animation is tied to a real system event:
  - Route animates edge-by-edge along the graph when a hospital is selected
  - Live counters tick when a WebSocket update arrives
  - Heatmap re-shades smoothly when clustering recomputes
  - New alerts slide in with a severity-colored pulse (CRITICAL pulses, LOW doesn't)
  - ECharts timeline scrubber plays through outbreak history (curve + map animate together)
  - Hospital scoring reveal animates the per-factor breakdown bars
- Borrow sensibility: OWID's editorial restraint for charts; real ops/SOC dashboards for the live view.

---

## 6. Engineering standards (pragmatic, not cargo-cult)

- Typed (Python type hints, TS on frontend). Pydantic models for API I/O.
- **Repository pattern** for data access — but only where it earns its place; don't wrap
  trivial queries in five abstraction layers. Avoid over-engineered "clean architecture"
  ceremony; favor clear, modular code.
- Custom error types; explicit error handling; structured logging (use `logging`/`tracing`-style).
- **Tests focus on the algorithmic core** (graph, Dijkstra, A*, K-D tree, clustering,
  scoring, spike detection) — these are correctness-critical and the interview talking points.
- Fault tolerance where it matters: timeouts + retries on external/background work.

---

## 7. How to work with me (Claude Code workflow rules)

1. **Build phase by phase. Never scaffold beyond the current phase's scope.** If a phase
   says "Dijkstra," do not also stub A*, Celery, or auth.
2. **Each phase must end in something that runs and can be demonstrated** (a curl, a test,
   or a visible UI change). State the demo step at the end of each phase.
3. **Explain non-obvious decisions in plain language** as you go. The project owner must be
   able to defend every design choice in an interview — teach, don't just emit code.
4. **Ask before any large architectural move** not already specified here.
5. Keep the event-bus boundary between pillars intact.
6. Document complexity for every algorithm.

### End-of-phase protocol (applies to EVERY phase)

At the end of each phase, before starting the next:

1. **Brief me** — summarize in plain language what was built this phase and why, so I
   understand and can defend it. Then **stop and wait for my review** before the next phase.
2. **Commit** — stage everything and make a clean commit with an accurate
   [conventional-commit](https://www.conventionalcommits.org/) message describing the real
   work (e.g. `feat(routing): implement Dijkstra shortest-path over the road graph`).
   The commit contains all the actual code and changes — nothing hidden, nothing fabricated.
3. **Authorship** — commits are authored as **Divyesh Das <divyeshdas.ofcl@gmail.com>**.
4. **No AI attribution anywhere** — there must be **no mention of Claude or any AI assistant**
   anywhere in the project: not in code, comments, docstrings, READMEs, docs, config, commit
   messages, and **no `Co-Authored-By` trailer**. Do not add "generated by" notes. The repo
   is a normal repo authored by Divyesh Das. (One-time setup, run before the first commit:
   `git config user.name "Divyesh Das"` and `git config user.email "divyeshdas.ofcl@gmail.com"`;
   also confirm no co-author trailer is appended by default.)

---

## 8. Build order

```
Phase 0   Foundation (shared spine)         ← build first, always
Pillar A  Routing      A1 → A5
Pillar B  Surveillance B1 → B4              ← A and B build on Phase 0 independently
Phase C   Integration (wire the spine + polish)  ← build last
```
