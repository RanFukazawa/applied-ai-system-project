# Model Card / Responsible AI Reflection: PawPal+ (Agentic, Retrieval Informed Pet Care Scheduler)

## Overview

This file is scoped to the graded responsible AI reflection only. For a full description of the system, see [`README.md`](README.md).

## Limitations and Biases

* **Owner time window not enforced.** `preferred_morning_start` and `preferred_evening_end` are collected and displayed, but `generate_plan()` never checks a task's time against them. This gap existed in the original design and remains true.
* **Only forward shifts.** `revise_plan()` only ever moves a task later. It never considers an earlier slot or reordering the day, so it functions as a forward push rather than a true optimizer.
* **Dense identical task limitation.** Four or more fully identical tasks (same pet, priority, duration, and time) can exceed the default attempt limit, since shifted tasks are compared only against the original anchor, not against each other. Confirmed by testing to have no effect on realistic use.
* **Conservative bias in the catch all type.** Tasks classified as other default to requiring full, exclusive attention, since the system cannot know what an unrecognized task involves. Two unrelated tasks of this type may be falsely flagged as conflicting.
* **Single owner assumption.** The exclusivity model assumes one person is doing the scheduling and does not account for a second household member who could supervise a second pet.

## Potential Misuse and Safeguards

Pet care scheduling is inherently low stakes, so misuse of this specific tool is unlikely. The larger risk lies in the pattern itself: an agent that silently shifts times could cause real harm if applied to a higher stakes domain, such as medical scheduling, without a person noticing the change.

The existing safeguard is that no shift happens invisibly. Every decision is recorded in `attempt_log`, including the original time, the new time, and the reason, and is shown in both the terminal demo and the Streamlit expander. This principle, always show the reasoning and never resolve silently, is the part most worth carrying into any higher stakes extension of this pattern.

## Surprises in Reliability Testing

**The dense task limitation was not anticipated.** The agentic loop worked correctly across realistic scenarios during development. The limitation only appeared once a stress test scenario, six identical tasks for one pet, was deliberately constructed. Investigating the pattern of unresolved conflicts, zero, zero, one, two, four, and five remaining for two through seven identical tasks, revealed that shifted tasks are always compared against the original anchor rather than against each other. The system still terminated cleanly and reported an accurate count rather than looping or crashing, but the specific cause was not something the design anticipated.

**Several genuine defects were caught only by running real scenarios**, including a reversed tie break rule, a variable name typo, and a dictionary key typo. Each appeared correct on inspection. This reinforced why the reliability and testing component earns its place in this project rather than serving as a formality.

## AI Collaboration: Helpful and Flawed Suggestions

### Helpful suggestion

When the conflict rule needed to change to distinguish same pet conflicts from cross pet conflicts involving exclusive attention, the same logic had to be checked in two places, `detect_conflicts()` and `revise_plan()`. Claude suggested consolidating the rule into a single shared method, `_is_real_conflict()`. This prevented a category of defect that had already appeared once before, where two independent copies of the same rule drifted apart as the design changed.

### Flawed or incorrect suggestion

The first implementation of the duration tie break rule was reversed. The intended rule was to shift the shorter, less disruptive task, but the code instead shifted the longer one. The error was a single inverted comparison and appeared correct on a straightforward reading. It was only caught by running a concrete scenario, a ten minute task overlapping a five minute task, and observing that the wrong one moved. This was a clear reminder that a plausible looking rule still requires verification against actual behavior.