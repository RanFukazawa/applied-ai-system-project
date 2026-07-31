# AI Interactions Log

## PawPal+ Scheduling Agent — Reasoning Traces (Agentic Workflow Enhancement)

> This section documents PawPal+'s own in-app agent (`Scheduler._run_agentic_loop()`), not an AI coding assistant. It's a genuine multi-step decision chain: **detect** conflicts → **decide** which task loses via priority/duration tie-break rules → **act** by shifting it → **re-check** the whole plan → **repeat**, bounded by `max_revision_attempts`, until clean or the budget runs out. All traces below are real `attempt_log` output captured by actually running the scheduler — not hand-written examples.

### Trace 1 — Multi-step cascading resolution across two independent conflicts

**Setup:** Buddy has Breakfast (07:00) and Heartworm pill (07:05) — a same-pet conflict. Separately, Luna's Brushing (07:45, grooming — exclusive attention) overlaps Buddy's Morning walk (07:30–08:00) — a cross-pet conflict, since grooming can't be split across pets the way walking can.

```
attempt_log:
  {'attempt': 1, 'status': 'shifted',
   'conflict': "[Buddy] 'Heartworm pill' at 07:05 vs [Buddy] 'Breakfast' at 07:00",
   'shifted_task': 'Heartworm pill', 'shifted_pet': 'Buddy',
   'old_time': '07:05', 'new_time': '07:15'}
  {'attempt': 2, 'status': 'shifted',
   'conflict': "[Luna] 'Brushing' at 07:45 vs [Buddy] 'Morning walk' at 07:30",
   'shifted_task': 'Brushing', 'shifted_pet': 'Luna',
   'old_time': '07:45', 'new_time': '08:05'}

explain_reasoning():
  "Tasks were sorted by priority (high → medium → low), then by duration
  (shorter first). Owner 'Alex' has 3h (180 min) available on a office day.
  4 task(s) scheduled (3 high, 1 medium, 0 low), using 60 min. Agentic
  conflict resolution: Attempt 1: shifted Buddy's 'Heartworm pill' from
  07:05 to 07:15 to resolve a conflict with [Buddy] 'Heartworm pill' at
  07:05 vs [Buddy] 'Breakfast' at 07:00. Attempt 2: shifted Luna's
  'Brushing' from 07:45 to 08:05 to resolve a conflict with [Luna]
  'Brushing' at 07:45 vs [Buddy] 'Morning walk' at 07:30."
```

Each attempt is a fresh planning step: the agent re-scans the *entire* plan after every shift, rather than fixing everything it sees in one pass — attempt 2 only exists because attempt 1's fix didn't touch the walk/grooming conflict, which required its own separate decision.

### Trace 2 — Retrieval feeding directly into the agent's decision (RAG → Agentic)

**Setup:** Buddy's "Trip to the dog park" (`dog_park` type) and Luna's "Annual checkup" (`vet_visit` type), both at 09:00. Neither type existed in the original hardcoded design — both are entries retrieved from `task_rules.json` at Task-creation time.

```
attempt_log:
  {'attempt': 1, 'status': 'shifted',
   'conflict': "[Buddy] 'Trip to the dog park' at 09:00 vs [Luna] 'Annual checkup' at 09:00",
   'shifted_task': 'Trip to the dog park', 'shifted_pet': 'Buddy',
   'old_time': '09:00', 'new_time': '09:35'}
```

The agent's decision here is *entirely* dependent on retrieved data: `task_rules.json` marks `vet_visit` as `exclusive_attention: true` and `dog_park` as `exclusive_attention: false`. That single retrieved flag is what makes this a real conflict at all (an exclusive task beats a combinable one, regardless of which pet or task name is involved) — the agent isn't reasoning about "vets" or "dog parks" semantically, it's reasoning over the retrieved classification.

### Trace 3 — Bounded termination when the agent can't fully resolve everything

**Setup:** Six identical "Walk" tasks (same pet, same priority, same duration, same time) — a deliberately adversarial stress test, with the attempt budget left at its default (5).

```
attempt_log:
  {'attempt': 1, 'status': 'shifted', 'shifted_task': 'Walk 1', 'new_time': '08:35', ...}
  {'attempt': 2, 'status': 'shifted', 'shifted_task': 'Walk 2', 'new_time': '08:35', ...}
  {'attempt': 3, 'status': 'shifted', 'shifted_task': 'Walk 3', 'new_time': '08:35', ...}
  {'attempt': 4, 'status': 'shifted', 'shifted_task': 'Walk 4', 'new_time': '08:35', ...}
  {'attempt': 5, 'status': 'shifted', 'shifted_task': 'Walk 5', 'new_time': '08:35', ...}
  {'attempt': None, 'status': 'stopped after 5 attempt(s); 4 conflict(s) remain unresolved'}
```

This is the "check its own work" half of the loop working as intended: rather than looping forever or crashing, the agent recognizes it's out of attempts and reports exactly how many conflicts it couldn't resolve. Investigating *why* 4 remained led to a genuine discovery — see `model_card.md`'s "Surprises in Reliability Testing" section for the full explanation (each shifted task lands on the *same* target time rather than cascading past one another, since `revise_plan()` only checks the newly-shifted task against the original anchor, not against other already-shifted tasks). Confirmed via direct testing that this only manifests with 4+ *fully identical* tasks for one pet — a normal 2-pet household with realistic, varied tasks resolves completely within 1–2 attempts.