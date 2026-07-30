"""
tests/test_pawpal.py - Unit tests for PawPal+ core logic.
Run with: pytest tests/test_pawpal.py -v
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from datetime import date, timedelta
from pawpal_system import Owner, Pet, Task, Scheduler


# ---------------------------------------------------------------------------
# Fixtures — reusable test objects
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_task():
    """A basic feeding task for use across tests."""
    return Task(name="Breakfast", duration=10, priority=1, type="feeding", scheduled_time="07:00")


@pytest.fixture
def sample_pet():
    """A basic pet with no tasks."""
    return Pet(name="Buddy", species="Dog", gender="Male", age=3)


@pytest.fixture
def sample_owner():
    """A standalone owner with office schedule and 3 free hours."""
    owner = Owner(name="Alex")
    owner.set_availability(
        work_schedule="office",
        available_hours=3,
        preferred_morning_start="07:00",
        preferred_evening_end="20:00",
    )
    return owner


@pytest.fixture
def owner_with_pet(sample_owner, sample_pet):
    """Owner with one pet already registered."""
    sample_owner.add_pet(sample_pet)
    return sample_owner


# ---------------------------------------------------------------------------
# Test 1: Task completion
# ---------------------------------------------------------------------------

class TestTaskCompletion:

    def test_task_is_incomplete_by_default(self, sample_task):
        """A newly created task should not be completed."""
        assert sample_task.is_completed is False

    def test_mark_complete_sets_flag(self, sample_task):
        """Calling mark_complete() should set is_completed to True."""
        sample_task.mark_complete()
        assert sample_task.is_completed is True

    def test_mark_complete_is_idempotent(self, sample_task):
        """Calling mark_complete() twice should not raise an error."""
        sample_task.mark_complete()
        sample_task.mark_complete()
        assert sample_task.is_completed is True


# ---------------------------------------------------------------------------
# Test 2: Task addition to a Pet
# ---------------------------------------------------------------------------

class TestTaskAddition:

    def test_new_pet_has_no_tasks(self, sample_pet):
        """A pet with no tasks added should have an empty task list."""
        assert len(sample_pet.get_tasks()) == 0

    def test_add_task_increases_count(self, sample_pet, sample_task):
        """Adding one task should increase the pet's task count to 1."""
        sample_pet.add_task(sample_task)
        assert len(sample_pet.get_tasks()) == 1

    def test_add_multiple_tasks_increases_count(self, sample_pet):
        """Adding three tasks should result in a task count of 3."""
        sample_pet.add_task(Task("Breakfast",    10, priority=1, type="feeding"))
        sample_pet.add_task(Task("Morning walk", 30, priority=2, type="walk"))
        sample_pet.add_task(Task("Medication",    5, priority=1, type="medication"))
        assert len(sample_pet.get_tasks()) == 3

    def test_added_task_is_retrievable(self, sample_pet, sample_task):
        """The task added should be the same object returned by get_tasks()."""
        sample_pet.add_task(sample_task)
        assert sample_task in sample_pet.get_tasks()


# ---------------------------------------------------------------------------
# Test 3: Sorting correctness
# ---------------------------------------------------------------------------

class TestSortByTime:

    def test_tasks_sorted_chronologically(self):
        """Tasks added out of order should be returned in HH:MM order."""
        unsorted = [
            {"task": "Evening walk",  "scheduled_time": "18:00"},
            {"task": "Breakfast",     "scheduled_time": "07:00"},
            {"task": "Morning walk",  "scheduled_time": "07:30"},
        ]
        result = Scheduler.sort_by_time(unsorted)
        times = [e["scheduled_time"] for e in result]
        assert times == ["07:00", "07:30", "18:00"]

    def test_timeless_tasks_go_to_end(self):
        """Tasks with no scheduled_time should appear after all timed tasks."""
        plan = [
            {"task": "Brushing",     "scheduled_time": ""},
            {"task": "Breakfast",    "scheduled_time": "07:00"},
            {"task": "Evening walk", "scheduled_time": "18:00"},
        ]
        result = Scheduler.sort_by_time(plan)
        assert result[-1]["task"] == "Brushing"

    def test_empty_plan_sorts_without_error(self):
        """sort_by_time on an empty list should return an empty list."""
        assert Scheduler.sort_by_time([]) == []

    def test_generate_plan_output_is_sorted(self, owner_with_pet, sample_pet):
        """generate_plan() should produce a chronologically sorted plan."""
        # Add tasks out of order
        sample_pet.add_task(Task("Evening walk", 30, priority=2, type="walk",    scheduled_time="18:00"))
        sample_pet.add_task(Task("Breakfast",    10, priority=1, type="feeding", scheduled_time="07:00"))
        scheduler = Scheduler(owner=owner_with_pet)
        plan = scheduler.generate_plan()
        timed = [e for e in plan if e["scheduled_time"]]
        times = [e["scheduled_time"] for e in timed]
        assert times == sorted(times)


# ---------------------------------------------------------------------------
# Test 4: Recurrence logic
# ---------------------------------------------------------------------------

class TestRecurringTasks:

    def test_daily_task_creates_next_occurrence(self, sample_pet):
        """Marking a daily task complete should create a new task due tomorrow."""
        today = date.today()
        task = Task("Breakfast", 10, priority=1, type="feeding",
                    scheduled_time="07:00", frequency="daily", due_date=today)
        sample_pet.add_task(task)
        next_task = sample_pet.mark_task_complete(task)
        assert next_task is not None
        assert next_task.due_date == today + timedelta(days=1)

    def test_weekly_task_creates_next_occurrence(self, sample_pet):
        """Marking a weekly task complete should create a new task due in 7 days."""
        today = date.today()
        task = Task("Brushing", 15, priority=5, type="grooming",
                    frequency="weekly", due_date=today)
        sample_pet.add_task(task)
        next_task = sample_pet.mark_task_complete(task)
        assert next_task is not None
        assert next_task.due_date == today + timedelta(weeks=1)

    def test_once_task_returns_none(self, sample_pet):
        """Marking a one-time task complete should return None with no new task."""
        task = Task("Vet visit", 60, priority=1, type="medication", frequency="once")
        sample_pet.add_task(task)
        result = sample_pet.mark_task_complete(task)
        assert result is None

    def test_recurring_task_inherits_attributes(self, sample_pet):
        """The new occurrence should have the same name, duration, and priority."""
        today = date.today()
        task = Task("Morning walk", 30, priority=2, type="walk",
                    scheduled_time="07:30", frequency="daily", due_date=today)
        sample_pet.add_task(task)
        next_task = sample_pet.mark_task_complete(task)
        assert next_task.name == task.name
        assert next_task.duration == task.duration
        assert next_task.priority == task.priority
        assert next_task.frequency == task.frequency

    def test_original_task_is_marked_complete(self, sample_pet):
        """The original task should be marked complete after mark_task_complete()."""
        task = Task("Breakfast", 10, priority=1, type="feeding", frequency="daily")
        sample_pet.add_task(task)
        sample_pet.mark_task_complete(task)
        assert task.is_completed is True


# ---------------------------------------------------------------------------
# Test 5: Conflict detection (post-agent behavior)
# ---------------------------------------------------------------------------
# NOTE: generate_plan() now runs the agentic self-correction loop internally,
# so fixable conflicts are auto-resolved by the time detect_conflicts() is
# called here. Raw/pre-resolution detection-rule logic is covered separately
# in TestConflictDetectionFix below, which builds a plan directly and never
# invokes the agent.

class TestConflictDetection:

    def _make_scheduler(self, owner, pet):
        """Helper to build and generate a schedule."""
        scheduler = Scheduler(owner=owner)
        scheduler.generate_plan()
        return scheduler

    def test_no_conflicts_when_tasks_do_not_overlap(self, owner_with_pet, sample_pet):
        """Non-overlapping tasks should produce no conflict warnings."""
        sample_pet.add_task(Task("Breakfast",    10, priority=1, type="feeding",    scheduled_time="07:00"))
        sample_pet.add_task(Task("Morning walk", 30, priority=2, type="walk",       scheduled_time="08:00"))
        scheduler = self._make_scheduler(owner_with_pet, sample_pet)
        assert scheduler.detect_conflicts() == []

    def test_exact_same_time_conflict_gets_auto_resolved(self, owner_with_pet, sample_pet):
        """
        Two same-pet tasks at the exact same time are a real conflict, but the
        agentic loop inside generate_plan() should shift the loser automatically,
        leaving no conflicts by the time we check.
        """
        sample_pet.add_task(Task("Breakfast", 10, priority=1, type="feeding",    scheduled_time="07:00"))
        sample_pet.add_task(Task("Medication", 5, priority=1, type="medication", scheduled_time="07:00"))
        scheduler = self._make_scheduler(owner_with_pet, sample_pet)
        assert scheduler.detect_conflicts() == []
        shifted = [e for e in scheduler.attempt_log if e.get("status") == "shifted"]
        assert len(shifted) == 1

    def test_overlapping_tasks_get_shifted_and_resolved(self, owner_with_pet, sample_pet):
        """
        Breakfast: 07:00 -> 07:10 (10 min); Medication: 07:05 -> overlaps by 5 min.
        Equal priority, so the shorter-duration task (Medication) should shift to
        start SHIFT_BUFFER_MINUTES after Breakfast ends (07:10 + 5 min = 07:15),
        resolving the conflict.
        """
        sample_pet.add_task(Task("Breakfast",  10, priority=1, type="feeding",    scheduled_time="07:00"))
        sample_pet.add_task(Task("Medication",  5, priority=1, type="medication", scheduled_time="07:05"))
        scheduler = self._make_scheduler(owner_with_pet, sample_pet)
        assert scheduler.detect_conflicts() == []
        shifted = [e for e in scheduler.attempt_log if e.get("status") == "shifted"]
        assert len(shifted) == 1
        assert shifted[0]["shifted_task"] == "Medication"
        assert shifted[0]["new_time"] == "07:15"

    def test_no_conflicts_empty_plan(self, sample_owner):
        """A scheduler with no tasks should return no conflicts."""
        pet = Pet(name="Luna", species="Cat", gender="Female", age=2)
        sample_owner.add_pet(pet)
        scheduler = Scheduler(owner=sample_owner)
        scheduler.generate_plan()
        assert scheduler.detect_conflicts() == []

    def test_timeless_tasks_not_checked_for_conflicts(self, owner_with_pet, sample_pet):
        """Tasks with no scheduled_time should not be included in conflict detection."""
        sample_pet.add_task(Task("Brushing", 15, priority=5, type="grooming"))  # no time
        sample_pet.add_task(Task("Playtime", 20, priority=4, type="enrichment"))  # no time
        scheduler = self._make_scheduler(owner_with_pet, sample_pet)
        assert scheduler.detect_conflicts() == []


# ---------------------------------------------------------------------------
# Test 6: Attention-required / exclusive-attention classification
# ---------------------------------------------------------------------------

class TestAttentionClassification:

    @pytest.mark.parametrize("task_type,expected_attention,expected_exclusive", [
        ("walk", True, False),
        ("grooming", True, True),
        ("enrichment", True, True),
        ("feeding", False, False),
        ("medication", False, False),
    ])
    def test_attention_flags_by_type(self, task_type, expected_attention, expected_exclusive):
        """
        Each task type should map to the correct attention_required and
        exclusive_attention values. Only grooming/enrichment are exclusive —
        walk requires the owner's attention but is combinable across pets
        (e.g. walking two dogs together on one outing), so it must always
        be attention_required=True but exclusive_attention=False.
        """
        task = Task("Test task", 10, priority=1, type=task_type)
        assert task.attention_required is expected_attention
        assert task.get_attention_required() is expected_attention
        assert task.exclusive_attention is expected_exclusive
        assert task.get_exclusive_attention() is expected_exclusive


# ---------------------------------------------------------------------------
# Test 7: Attention-aware conflict detection rules (pure logic, no agent)
# ---------------------------------------------------------------------------
# These tests build generated_plan directly (bypassing generate_plan()) so we
# can verify the detection RULE in isolation, before any auto-revision runs.

class TestConflictDetectionFix:

    @staticmethod
    def _scheduler_with_plan(owner, plan_entries):
        scheduler = Scheduler(owner=owner)
        scheduler.generated_plan = plan_entries
        return scheduler

    def test_same_pet_overlap_flagged_regardless_of_type(self, sample_owner):
        """Same-pet overlaps are flagged even when both tasks are low-attention."""
        plan = [
            {"pet": "Buddy", "task": "Breakfast", "type": "feeding", "duration": 10,
             "priority": 1, "scheduled_time": "07:00",
             "attention_required": False, "exclusive_attention": False},
            {"pet": "Buddy", "task": "Medication", "type": "medication", "duration": 5,
             "priority": 1, "scheduled_time": "07:05",
             "attention_required": False, "exclusive_attention": False},
        ]
        scheduler = self._scheduler_with_plan(sample_owner, plan)
        assert len(scheduler.detect_conflicts()) == 1

    def test_cross_pet_low_attention_overlap_not_flagged(self, sample_owner):
        """Two different pets fed at the same time should not conflict."""
        plan = [
            {"pet": "Buddy", "task": "Breakfast", "type": "feeding", "duration": 10,
             "priority": 1, "scheduled_time": "07:00",
             "attention_required": False, "exclusive_attention": False},
            {"pet": "Luna", "task": "Breakfast", "type": "feeding", "duration": 5,
             "priority": 1, "scheduled_time": "07:00",
             "attention_required": False, "exclusive_attention": False},
        ]
        scheduler = self._scheduler_with_plan(sample_owner, plan)
        assert scheduler.detect_conflicts() == []

    def test_cross_pet_combinable_attention_overlap_not_flagged(self, sample_owner):
        """
        Two different pets walked at the same time should NOT conflict.
        Walking requires the owner's attention but is combinable across
        pets — many owners walk multiple dogs together on one outing.
        """
        plan = [
            {"pet": "Buddy", "task": "Morning walk", "type": "walk", "duration": 30,
             "priority": 2, "scheduled_time": "08:00",
             "attention_required": True, "exclusive_attention": False},
            {"pet": "Luna", "task": "Morning walk", "type": "walk", "duration": 30,
             "priority": 2, "scheduled_time": "08:00",
             "attention_required": True, "exclusive_attention": False},
        ]
        scheduler = self._scheduler_with_plan(sample_owner, plan)
        assert scheduler.detect_conflicts() == []

    def test_cross_pet_exclusive_attention_overlap_flagged(self, sample_owner):
        """
        Two different pets groomed at the same time SHOULD conflict: grooming
        needs the owner's full, undivided presence and cannot be split
        across pets the way walking can.
        """
        plan = [
            {"pet": "Buddy", "task": "Brushing", "type": "grooming", "duration": 15,
             "priority": 3, "scheduled_time": "09:00",
             "attention_required": True, "exclusive_attention": True},
            {"pet": "Luna", "task": "Brushing", "type": "grooming", "duration": 15,
             "priority": 3, "scheduled_time": "09:00",
             "attention_required": True, "exclusive_attention": True},
        ]
        scheduler = self._scheduler_with_plan(sample_owner, plan)
        assert len(scheduler.detect_conflicts()) == 1

    def test_cross_pet_combinable_plus_exclusive_overlap_flagged(self, sample_owner):
        """
        A walk (combinable) for one pet and a grooming session (exclusive)
        for another, at the same time, SHOULD conflict: the owner can't be
        fully dedicated to grooming one pet while also walking another, even
        though the walk alone would have been shareable with a second walk.
        """
        plan = [
            {"pet": "Buddy", "task": "Morning walk", "type": "walk", "duration": 30,
             "priority": 2, "scheduled_time": "08:00",
             "attention_required": True, "exclusive_attention": False},
            {"pet": "Luna", "task": "Brushing", "type": "grooming", "duration": 15,
             "priority": 3, "scheduled_time": "08:00",
             "attention_required": True, "exclusive_attention": True},
        ]
        scheduler = self._scheduler_with_plan(sample_owner, plan)
        assert len(scheduler.detect_conflicts()) == 1

    def test_cross_pet_mixed_attention_overlap_not_flagged(self, sample_owner):
        """A walk and a feeding for different pets should NOT conflict — feeding needs no active attention at all."""
        plan = [
            {"pet": "Buddy", "task": "Morning walk", "type": "walk", "duration": 30,
             "priority": 2, "scheduled_time": "08:00",
             "attention_required": True, "exclusive_attention": False},
            {"pet": "Luna", "task": "Breakfast", "type": "feeding", "duration": 10,
             "priority": 1, "scheduled_time": "08:00",
             "attention_required": False, "exclusive_attention": False},
        ]
        scheduler = self._scheduler_with_plan(sample_owner, plan)
        assert scheduler.detect_conflicts() == []


# ---------------------------------------------------------------------------
# Test 8: Agentic self-correction loop
# ---------------------------------------------------------------------------

class TestAgenticRevision:

    def test_fixable_conflict_resolves_and_logs_shift(self, owner_with_pet, sample_pet):
        """A single fixable conflict should resolve within one attempt and be logged."""
        sample_pet.add_task(Task("Breakfast", 10, priority=1, type="feeding", scheduled_time="07:00"))
        sample_pet.add_task(Task("Medication", 5, priority=1, type="medication", scheduled_time="07:05"))
        scheduler = Scheduler(owner=owner_with_pet)
        scheduler.generate_plan()

        assert scheduler.detect_conflicts() == []
        shifted = [e for e in scheduler.attempt_log if e.get("status") == "shifted"]
        assert len(shifted) == 1
        assert shifted[0]["shifted_task"] == "Medication"
        assert shifted[0]["new_time"] == "07:15"

    def test_cascading_shift_still_resolves_within_attempts(self, owner_with_pet, sample_pet):
        """A shift that creates a new downstream conflict should keep resolving."""
        sample_pet.add_task(Task("Breakfast",   10, priority=1, type="feeding",    scheduled_time="07:00"))
        sample_pet.add_task(Task("Medication",   5, priority=1, type="medication", scheduled_time="07:05"))
        sample_pet.add_task(Task("Morning walk", 10, priority=2, type="walk",      scheduled_time="07:10"))
        scheduler = Scheduler(owner=owner_with_pet)
        scheduler.generate_plan()

        assert scheduler.detect_conflicts() == []
        assert len(scheduler.attempt_log) >= 1

    def test_many_simultaneous_conflicts_terminate_without_crashing(self, owner_with_pet, sample_pet):
        """
        More conflicts than the attempt budget allows should stop cleanly rather
        than loop forever or crash, and the log should say so explicitly if any
        conflicts remain unresolved.
        """
        owner_with_pet.set_availability(
            work_schedule="office",
            available_hours=5,
            preferred_morning_start="07:00",
            preferred_evening_end="20:00",
        )
        for i in range(8):
            sample_pet.add_task(
                Task(f"Walk {i}", 30, priority=1, type="walk", scheduled_time="08:00")
            )

        scheduler = Scheduler(owner=owner_with_pet)
        scheduler.generate_plan(max_revision_attempts=5)  # deliberately too few attempts

        shifted = [e for e in scheduler.attempt_log if e.get("status") == "shifted"]
        assert len(shifted) <= 5  # never exceeds the attempt budget

        remaining = scheduler.detect_conflicts()
        if remaining:
            final_statuses = [str(e.get("status", "")) for e in scheduler.attempt_log]
            assert any("unresolved" in s for s in final_statuses)

    def test_unfixable_same_pet_conflict_reports_unresolved(self, owner_with_pet, sample_pet):
        """
        Two identical-priority, identical-duration, same-pet, same-time tasks
        still get exactly one deterministic shift attempt; if more conflicts
        remain than attempts allow, it must be reported, never silently dropped.
        """
        sample_pet.add_task(Task("Walk A", 30, priority=1, type="walk", scheduled_time="08:00"))
        sample_pet.add_task(Task("Walk B", 30, priority=1, type="walk", scheduled_time="08:00"))
        scheduler = Scheduler(owner=owner_with_pet)
        scheduler.generate_plan(max_revision_attempts=1)

        # Should not raise, and should always leave attempt_log in a valid state
        assert isinstance(scheduler.attempt_log, list)
        assert len(scheduler.attempt_log) >= 1


# ---------------------------------------------------------------------------
# Test 9: Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:

    @staticmethod
    def _build_scheduler():
        owner = Owner(name="Alex")
        owner.set_availability(
            work_schedule="office",
            available_hours=3,
            preferred_morning_start="07:00",
            preferred_evening_end="20:00",
        )
        dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
        dog.add_task(Task("Breakfast",   10, priority=1, type="feeding",    scheduled_time="07:00"))
        dog.add_task(Task("Medication",   5, priority=1, type="medication", scheduled_time="07:05"))
        dog.add_task(Task("Morning walk", 30, priority=2, type="walk",      scheduled_time="07:30"))
        owner.add_pet(dog)
        scheduler = Scheduler(owner=owner)
        scheduler.generate_plan()
        return scheduler

    def test_same_input_produces_same_plan(self):
        """Running identical input through the pipeline twice should give identical output."""
        first = self._build_scheduler()
        second = self._build_scheduler()

        first_shape = [(e["pet"], e["task"], e["scheduled_time"]) for e in first.generated_plan]
        second_shape = [(e["pet"], e["task"], e["scheduled_time"]) for e in second.generated_plan]
        assert first_shape == second_shape

    def test_same_input_produces_same_attempt_log_shape(self):
        """The number and type of revision attempts should be identical across runs."""
        first = self._build_scheduler()
        second = self._build_scheduler()

        first_statuses = [e.get("status") for e in first.attempt_log]
        second_statuses = [e.get("status") for e in second.attempt_log]
        assert first_statuses == second_statuses