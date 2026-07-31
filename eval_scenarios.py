"""
eval_scenarios.py - PawPal+ evaluation harness

A standalone script (distinct from tests/test_pawpal.py) that runs the
scheduler against a fixed set of predefined, realistic scenarios and
reports a pass/fail scorecard. Where tests/test_pawpal.py checks internal
units of logic in isolation, this evaluates end-to-end system behavior on
scenarios chosen to mirror how the app is actually used, plus the specific
edge case discovered during reliability testing (see model_card.md).

Run with: python eval_scenarios.py
"""

from pawpal_system import Owner, Pet, Task, Scheduler


class ScenarioResult:
    def __init__(self, name: str, passed: bool, detail: str):
        self.name = name
        self.passed = passed
        self.detail = detail


def make_owner(hours: int = 5) -> Owner:
    owner = Owner(name="Alex")
    owner.set_availability(
        work_schedule="office", available_hours=hours,
        preferred_morning_start="07:00", preferred_evening_end="20:00",
    )
    return owner


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_same_pet_conflict_auto_resolves() -> ScenarioResult:
    """A realistic same-pet time overlap should be auto-resolved by the agent."""
    owner = make_owner()
    dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    dog.add_task(Task("Breakfast", 10, priority=1, type="feeding", scheduled_time="07:00"))
    dog.add_task(Task("Medication", 5, priority=1, type="medication", scheduled_time="07:05"))
    owner.add_pet(dog)

    sched = Scheduler(owner=owner)
    sched.generate_plan()
    med = next(t for t in dog.get_tasks() if t.name == "Medication")

    passed = (
        sched.detect_conflicts() == []
        and len(sched.attempt_log) == 1
        and med.scheduled_time == "07:15"
    )
    return ScenarioResult(
        "Same-pet conflict auto-resolves",
        passed,
        f"conflicts={sched.detect_conflicts()}, Medication at {med.scheduled_time}",
    )


def scenario_cross_pet_combinable_no_conflict() -> ScenarioResult:
    """Two different pets walked at the same time should NOT conflict."""
    owner = make_owner()
    buddy = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    rex = Pet(name="Rex", species="Dog", gender="Male", age=4)
    buddy.add_task(Task("Morning walk", 30, priority=2, type="walk", scheduled_time="08:00"))
    rex.add_task(Task("Morning walk", 30, priority=2, type="walk", scheduled_time="08:00"))
    owner.add_pet(buddy)
    owner.add_pet(rex)

    sched = Scheduler(owner=owner)
    sched.generate_plan()

    passed = sched.detect_conflicts() == [] and sched.attempt_log == []
    return ScenarioResult(
        "Cross-pet combinable tasks don't conflict",
        passed,
        f"conflicts={sched.detect_conflicts()}, attempt_log={sched.attempt_log}",
    )


def scenario_cross_pet_exclusive_resolves() -> ScenarioResult:
    """Two different pets groomed at the same time SHOULD conflict, then resolve."""
    owner = make_owner()
    buddy = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    luna = Pet(name="Luna", species="Cat", gender="Female", age=2)
    buddy.add_task(Task("Brushing", 15, priority=2, type="grooming", scheduled_time="08:00"))
    luna.add_task(Task("Brushing", 15, priority=2, type="grooming", scheduled_time="08:00"))
    owner.add_pet(buddy)
    owner.add_pet(luna)

    sched = Scheduler(owner=owner)
    sched.generate_plan()

    passed = sched.detect_conflicts() == [] and len(sched.attempt_log) == 1
    return ScenarioResult(
        "Cross-pet exclusive tasks conflict and resolve",
        passed,
        f"conflicts={sched.detect_conflicts()}, attempts={len(sched.attempt_log)}",
    )


def scenario_extensible_type_via_task_rules() -> ScenarioResult:
    """dog_park (combinable) vs. vet_visit (exclusive) -- both retrieved from
    task_rules.json, neither hardcoded -- should conflict and resolve."""
    owner = make_owner()
    buddy = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    luna = Pet(name="Luna", species="Cat", gender="Female", age=2)
    buddy.add_task(Task("Trip to the dog park", 45, priority=2, type="dog_park", scheduled_time="09:00"))
    luna.add_task(Task("Annual checkup", 30, priority=1, type="vet_visit", scheduled_time="09:00"))
    owner.add_pet(buddy)
    owner.add_pet(luna)

    sched = Scheduler(owner=owner)
    sched.generate_plan()

    passed = sched.detect_conflicts() == [] and len(sched.attempt_log) == 1
    return ScenarioResult(
        "Extensible types (task_rules.json) drive real conflict decisions",
        passed,
        f"conflicts={sched.detect_conflicts()}, attempts={len(sched.attempt_log)}",
    )


def scenario_unknown_type_defaults_safely() -> ScenarioResult:
    """A type not in task_rules.json should default to no attention required,
    not crash and not falsely conflict with anything."""
    owner = make_owner()
    dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    dog.add_task(Task("Something new", 10, priority=1, type="totally_unknown_type", scheduled_time="08:00"))
    dog.add_task(Task("Breakfast", 10, priority=1, type="feeding", scheduled_time="08:00"))
    owner.add_pet(dog)

    sched = Scheduler(owner=owner)
    sched.generate_plan()
    unknown_task = next(t for t in dog.get_tasks() if t.name == "Something new")

    # Same pet, so it SHOULD still conflict (same-pet rule applies regardless
    # of type) -- this checks the fallback classification doesn't crash and
    # the same-pet rule still fires correctly around it.
    passed = unknown_task.attention_required is False and len(sched.attempt_log) == 1
    return ScenarioResult(
        "Unknown task type defaults safely, doesn't crash",
        passed,
        f"attention_required={unknown_task.attention_required}, attempts={len(sched.attempt_log)}",
    )


def scenario_skipped_task_reported() -> ScenarioResult:
    """A task that doesn't fit in available time should be reported, not silently dropped."""
    owner = make_owner(hours=1)
    dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    dog.add_task(Task("Breakfast", 10, priority=1, type="feeding", scheduled_time="07:00"))
    dog.add_task(Task("Long walk", 90, priority=2, type="walk", scheduled_time="08:00"))
    owner.add_pet(dog)

    sched = Scheduler(owner=owner)
    sched.generate_plan()

    passed = sched.skipped_tasks == ["Long walk for Buddy"]
    return ScenarioResult(
        "Tasks that don't fit are reported via skipped_tasks",
        passed,
        f"skipped_tasks={sched.skipped_tasks}",
    )


def scenario_determinism() -> ScenarioResult:
    """Running the same input through the pipeline twice must give identical output."""
    def build():
        owner = make_owner(hours=3)
        dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
        dog.add_task(Task("Breakfast", 10, priority=1, type="feeding", scheduled_time="07:00"))
        dog.add_task(Task("Medication", 5, priority=1, type="medication", scheduled_time="07:05"))
        owner.add_pet(dog)
        sched = Scheduler(owner=owner)
        sched.generate_plan()
        return sched

    first, second = build(), build()
    first_shape = [(e["task"], e["scheduled_time"]) for e in first.generated_plan]
    second_shape = [(e["task"], e["scheduled_time"]) for e in second.generated_plan]

    passed = first_shape == second_shape
    return ScenarioResult(
        "Same input produces identical output (determinism)",
        passed,
        f"first={first_shape}, second={second_shape}",
    )


def scenario_generate_vs_refresh_diverge_after_edit() -> ScenarioResult:
    """Editing a task's priority should leave Refresh's plan untouched, but
    Generate must re-solve with the new priority and can flip the outcome."""
    owner = make_owner()
    buddy = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    luna = Pet(name="Luna", species="Cat", gender="Female", age=2)
    buddy.add_task(Task("Morning walk", 30, priority=2, type="walk", scheduled_time="08:00"))
    luna.add_task(Task("Brushing", 15, priority=3, type="grooming", scheduled_time="08:00"))
    owner.add_pet(buddy)
    owner.add_pet(luna)

    sched = Scheduler(owner=owner)
    sched.generate_plan()
    walk = next(t for t in buddy.get_tasks() if t.name == "Morning walk")
    brushing = next(t for t in luna.get_tasks() if t.name == "Brushing")

    walk.priority = 4  # edit: lower walk's priority below Brushing's
    walk.__post_init__()

    sched.generate_plan()  # Refresh: no reset
    refresh_walk_time = walk.scheduled_time
    refresh_brushing_time = brushing.scheduled_time

    sched.generate_plan(reset_to_original=True)  # Generate: reset + re-solve
    generate_walk_time = walk.scheduled_time
    generate_brushing_time = brushing.scheduled_time

    passed = (
        (refresh_walk_time, refresh_brushing_time) == ("08:00", "08:35")
        and (generate_walk_time, generate_brushing_time) == ("08:20", "08:00")
    )
    return ScenarioResult(
        "Generate vs Refresh diverge correctly after an in-place edit",
        passed,
        f"refresh=(walk={refresh_walk_time}, brushing={refresh_brushing_time}), "
        f"generate=(walk={generate_walk_time}, brushing={generate_brushing_time})",
    )


def scenario_known_limitation_dense_tie_pileup() -> ScenarioResult:
    """
    KNOWN LIMITATION (see model_card.md): 4+ fully identical tasks (same
    pet, priority, duration, and time) overwhelm the default attempt budget,
    since revise_plan() checks each shift against the original anchor task
    only, not against other already-shifted tasks. This scenario passes if
    the agent terminates cleanly and reports the EXPECTED unresolved count
    (4) rather than crashing or looping -- it documents the limitation
    rather than hiding it.
    """
    owner = make_owner(hours=8)
    dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
    for i in range(6):
        dog.add_task(Task(f"Walk {i}", 30, priority=1, type="walk", scheduled_time="08:00"))
    owner.add_pet(dog)

    sched = Scheduler(owner=owner)
    sched.generate_plan()  # default attempt budget
    remaining = len(sched.detect_conflicts())

    passed = remaining == 4  # documented, expected limitation -- not a crash, not silent
    return ScenarioResult(
        "Known limitation: dense identical-task pileup terminates cleanly (documented)",
        passed,
        f"unresolved conflicts={remaining} (expected: 4, see model_card.md)",
    )


SCENARIOS = [
    scenario_same_pet_conflict_auto_resolves,
    scenario_cross_pet_combinable_no_conflict,
    scenario_cross_pet_exclusive_resolves,
    scenario_extensible_type_via_task_rules,
    scenario_unknown_type_defaults_safely,
    scenario_skipped_task_reported,
    scenario_determinism,
    scenario_generate_vs_refresh_diverge_after_edit,
    scenario_known_limitation_dense_tie_pileup,
]


def main() -> None:
    print("=" * 72)
    print("PawPal+ Evaluation Harness")
    print("=" * 72)

    results = []
    for scenario_fn in SCENARIOS:
        try:
            result = scenario_fn()
        except Exception as exc:
            result = ScenarioResult(scenario_fn.__name__, False, f"CRASHED: {exc}")
        results.append(result)

        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}")
        print(f"       {result.detail}")

    passed_count = sum(1 for r in results if r.passed)
    total = len(results)
    score_pct = 100 * passed_count / total

    print("=" * 72)
    print(f"SUMMARY: {passed_count}/{total} scenarios passed ({score_pct:.0f}%)")
    print("=" * 72)

    if passed_count < total:
        failed = [r.name for r in results if not r.passed]
        print("Failed scenarios:")
        for name in failed:
            print(f"  - {name}")


if __name__ == "__main__":
    main()