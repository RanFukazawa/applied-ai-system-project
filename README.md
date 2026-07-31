# PawPal+: An Agentic, Retrieval Informed Pet Care Scheduler

(Applied AI Systems Project. Extends PawPal+ from Modules 1 through 3.)

## Original Project

This project extends PawPal+, originally built in Modules 1 through 3. Full original documentation is preserved in [`ORIGINAL_README.md`](ORIGINAL_README.md).

The original PawPal+ was a Streamlit application built around four core classes: `Owner`, `Pet`, `Task`, and `Scheduler`. It let an owner register pets and tasks, then generate a daily plan by priority and duration. It supported recurring tasks and flagged simple time conflicts, but every overlap was treated the same way, and once a conflict was found, the tool made no attempt to resolve it.

## Title and Summary

PawPal+ now attempts to solve problems, not just notice them. The scheduler still sorts and fits tasks into the day, but also runs an agentic loop that corrects the plan on its own:

* Detects real conflicts.
* Decides which task should move.
* Shifts it, then checks the whole plan again.
* Repeats until the plan is clean or an attempt limit is reached.

What counts as a genuine conflict is driven by an external, editable retrieval source, `task_rules.json`, which classifies each task type by how much attention it demands. This lets the system treat walking two dogs together as acceptable while still flagging two pets that each require full attention at once.

This project implements three of the four available AI features, each substantively developed:

* Agentic Workflow
* Retrieval Augmented Generation
* Reliability and Testing System

## Architecture Overview

Full diagrams are in [`diagrams/architecture.mmd`](diagrams/architecture.mmd) and [`diagrams/uml_final.mmd`](diagrams/uml_final.mmd). At a general level:

* **Input**: Owner, Pet, and Task data entered or edited through `app.py` (Streamlit) or `main.py` (terminal demo).
* **Retrieval**: `task_rules.json` loads once into `TASK_RULES`. Every `Task` looks up its type here, both at creation and on edit, to derive `attention_required`, `exclusive_attention`, and a plain language reason. These fields directly drive the agent's decisions, not just accompany them.
* **Agent**: `Scheduler.generate_plan()` sorts and fits tasks, then hands off to `_run_agentic_loop()`, which cycles `detect_conflicts()` and `revise_plan()` until clean or the attempt limit (five by default) is reached. Every decision is logged to `attempt_log`.
* **Output**: the Streamlit interface (timeline, attention column, an expander explaining the plan) and the terminal demo in `main.py`.
* **Testing**: `tests/test_pawpal.py` (fifty five tests) and `eval_scenarios.py` (a separate scenario harness), validating the agent and retrieval layer independently.
* **Human in the loop**: the owner reviews the plan, edits or deletes tasks directly, and either lets it update automatically or resets it with the Generate Schedule button.

## Setup Instructions

```bash
# clone the repository, then from the project root:
python -m venv .venv
source .venv/bin/activate       # on Windows: .venv\Scripts\activate
pip install streamlit pytest

# run the application
streamlit run app.py

# run the terminal demonstration
python main.py

# run the standalone evaluation harness
python eval_scenarios.py

# run the full test suite
python -m pytest tests/test_pawpal.py -v
```

Place `task_rules.json` in the same directory as `pawpal_system.py`. The loader resolves its path relative to the module file, so it works regardless of where `streamlit run` is launched from.

## Sample Interactions

**Same pet conflict, resolved automatically.**
Buddy has Breakfast (feeding, 07:00, 10 minutes) and a Heartworm pill (medication, 07:05, 5 minutes). Same pet overlaps are always flagged, regardless of type. The agent shifts the pill to 07:15 and logs the reason directly.

**Combinable versus exclusive attention, across two pets.**
Buddy and Rex are both scheduled for a walk at 08:00. No conflict is flagged, since walking can be shared across pets. Change one task to grooming instead, and the same overlap is flagged and resolved, since grooming requires full, undivided attention.

**Extensibility without code changes.**
Buddy is scheduled for a dog park visit and Luna for a veterinary visit, both at 09:00. Neither type existed in the original design. The agent still resolves the conflict correctly, since both classifications came from two new entries in `task_rules.json`. Neither `pawpal_system.py` nor `app.py` needed modification.

## Design Decisions

* **Owner level scheduling, not per pet.** The owner's available hours are one shared pool, not a separate budget per pet. Most consumer pet care apps track each pet in isolation and never reason across pets at all.
* **Exclusive versus combinable attention.** Two dogs can be walked together, but two pets cannot be groomed at once. No existing pet scheduling software models this distinction.
* **External, editable task classification.** Task type knowledge lives in `task_rules.json` rather than fixed Python sets, so new types can be added by editing configuration instead of code.
* **Separate original and live scheduled times.** The agent modifies a task's live scheduled time directly. Storing `original_scheduled_time` separately, and supporting `reset_to_original`, lets Generate Schedule mean a full reset while automatic updates remain incremental.
* **Simple, greedy tie break logic.** `revise_plan()` decides by priority, then duration, then a deterministic fallback. This is predictable and fast, but not globally optimal. The cost of this tradeoff is documented as a known limitation below.

## Testing Summary

`tests/test_pawpal.py` (fifty five tests) covers:

* Task completion, recurrence, and sorting.
* Attention classification for new and unrecognized task types.
* The attention aware conflict rule in isolation.
* The full agentic loop, including cascading shifts and attempt limit exhaustion.
* Determinism, and the loading and fallback behavior of `task_rules.json`.
* The Generate versus Refresh distinction, including a case where an edit changes which task the agent moves.

`eval_scenarios.py` is a separate, standalone harness. It runs nine end to end scenarios reflecting realistic usage and prints a pass or fail summary for each.

Testing surfaced several genuine defects:

* A tie break rule implemented in reverse, shifting the longer task instead of the shorter one. Caught only by running an actual scenario.
* A variable name typo (`self.generate_plan` instead of `self.generated_plan`) and a dictionary key typo (`conflcit` instead of `conflict`), either of which would have caused a crash.
* A missing method, `get_attention_required()`, caught directly by the test suite.
* A session state defect in `app.py` where pets silently disappeared from the generated plan, traced to two lists drifting out of agreement. Resolved by making `owner.pets` the single source of truth.

**Known limitation.** `revise_plan()` compares a shifted task only against the original anchor task, not against other tasks already shifted in the same run. When four or more identical tasks share a pet, priority, duration, and time, several land on the same new time instead of cascading in sequence.

| Identical tied tasks | Conflicts remaining after the default attempt limit |
|---|---|
| 2 | 0 |
| 3 | 0 |
| 4 | 1 |
| 5 | 2 |
| 6 | 4 |
| 7 | 5 |

Direct testing confirmed this does not affect realistic use. A household with two pets and varied tasks resolves within one or two attempts. The limitation only appears with four or more perfectly duplicate tasks for one pet, which the Streamlit interface makes unlikely to occur by accident.

## Reflection

The graded responsible AI reflection, covering AI collaboration, one helpful suggestion, one flawed suggestion, and system limitations, is documented in [`model_card.md`](model_card.md) rather than here, per the assignment's grading structure.