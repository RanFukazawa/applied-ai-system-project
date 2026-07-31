"""
pawpal_system.py - PawPal+ logic layer
Full implementation of all four core classes.
"""
 
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date, timedelta
import json
from pathlib import Path


def normalize_time(time_str: str) -> str:
    """
    Normalize a user-entered time string to HH:MM format.
    Accepts: "8:00", "8:5", "08:00", "18:00". Returns "" for empty or invalid input.
    Examples: "8:00" -> "08:00", "9:5" -> "09:05", "" -> ""
    """
    if not time_str or not time_str.strip():
        return ""
    try:
        parts = time_str.strip().split(":")
        if len(parts) != 2:
            return ""
        hours, minutes = int(parts[0]), int(parts[1])
        if not (0 <= hours <= 23 and 0 <= minutes <= 59):
            return ""
        return f"{hours:02d}:{minutes:02d}"
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# Task type classification rules
#
# Which task types need the owner's active attention, and which of those need
# FULL, undivided attention (can't be split across pets) vs. are combinable
# (e.g. walking two dogs together). This used to be two hardcoded Python sets
# on the Task class; it now lives in task_rules.json so new types can be
# added by editing that file, with no code changes required anywhere.
# ---------------------------------------------------------------------------
_TASK_RULES_FILENAME = "task_rules.json"

# In-code fallback, used only if task_rules.json is missing or malformed, so
# the app degrades gracefully instead of crashing on a bad/absent config file.
_DEFAULT_TASK_RULES = {
    "walk":       {"attention_required": True,  "exclusive_attention": False,
                   "icon": "👀", "reason": "Needs your attention, but can be combined across pets."},
    "grooming":   {"attention_required": True,  "exclusive_attention": True,
                   "icon": "🔒", "reason": "Needs your full, undivided attention."},
    "enrichment": {"attention_required": True,  "exclusive_attention": True,
                   "icon": "🔒", "reason": "Needs your full, undivided attention."},
    "feeding":    {"attention_required": False, "exclusive_attention": False,
                   "icon": "🍽️", "reason": "Brief enough to happen for two pets in parallel."},
    "medication": {"attention_required": False, "exclusive_attention": False,
                   "icon": "💊", "reason": "Brief enough to happen for two pets in parallel."},
    "other":      {"attention_required": True,  "exclusive_attention": True,
                   "icon": "⭐️", "reason": "Not a recognized task type — assumed to need full attention as a safe default."},
}


def load_task_rules(path: Optional[str] = None) -> dict:
    """
    Load task-type classification rules from task_rules.json (next to this
    file by default). Falls back to a small built-in default set if the file
    is missing, unreadable, or malformed.
    """
    rules_path = Path(path) if path else Path(__file__).parent / _TASK_RULES_FILENAME
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
        if not isinstance(rules, dict) or not rules:
            raise ValueError("task_rules.json must contain a non-empty JSON object")
        return rules
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return dict(_DEFAULT_TASK_RULES)


# Loaded once at import time; every Task looks up its classification here.
TASK_RULES = load_task_rules()


@dataclass
class Owner:
    """Represents a pet owner and their scheduling availability."""
    name: str
    work_schedule: str = "off"        # "office", "remote", "off"
    available_hours: int = 8          # total free hours in the day
    preferred_morning_start: str = "07:00"
    preferred_evening_end: str = "21:00"
    pets: List[Pet] = field(default_factory=list)
 
    def get_name(self) -> str:
        """Return the owner's name."""
        return self.name
 
    def get_availability(self) -> dict:
        """Return a dict summarising the owner's availability and preferences."""
        return {
            "work_schedule": self.work_schedule,
            "available_hours": self.available_hours,
            "preferred_morning_start": self.preferred_morning_start,
            "preferred_evening_end": self.preferred_evening_end,
        }
 
    def set_availability(
        self,
        work_schedule: str,
        available_hours: int,
        preferred_morning_start: str,
        preferred_evening_end: str,
    ) -> None:
        """Update the owner's availability and scheduling preferences."""
        valid_schedules = {"office", "remote", "off"}
        if work_schedule not in valid_schedules:
            raise ValueError(f"work_schedule must be one of {valid_schedules}.")
        if not 0 <= available_hours <= 24:
            raise ValueError("available_hours must be between 0 and 24.")
        self.work_schedule = work_schedule
        self.available_hours = available_hours
        self.preferred_morning_start = preferred_morning_start
        self.preferred_evening_end = preferred_evening_end
 
    def add_pet(self, pet: Pet) -> None:
        """Register a pet under this owner."""
        pet.owner = self
        self.pets.append(pet)
 
    def get_all_tasks(self) -> List[Task]:
        """Return every task across all pets owned."""
        all_tasks = []
        for pet in self.pets:
            all_tasks.extend(pet.get_tasks())
        return all_tasks
 
    def __str__(self) -> str:
        return (
            f"{self.name} | {self.work_schedule} day | "
            f"{self.available_hours}h available | "
            f"{len(self.pets)} pet(s)"
        )
 
 
@dataclass
class Pet:
    """Represents a pet and its associated care tasks."""
    name: str
    species: str
    gender: str
    age: int
    owner: Optional[Owner] = field(default=None)
    health_history: str = ""
    medical_needs: str = ""
    tasks: List[Task] = field(default_factory=list)
 
    def get_name(self) -> str:
        """Return the pet's name."""
        return self.name
 
    def get_species(self) -> str:
        """Return the pet's species."""
        return self.species
 
    def get_age(self) -> int:
        """Return the pet's age."""
        return self.age
 
    def get_medical_needs(self) -> str:
        """Return the pet's medical needs."""
        return self.medical_needs
 
    def add_task(self, task: Task) -> None:
        """Add a care task to this pet's task list."""
        self.tasks.append(task)
 
    def get_tasks(self) -> List[Task]:
        """Return all tasks associated with this pet."""
        return self.tasks
 
    def get_pending_tasks(self) -> List[Task]:
        """Return only tasks that have not been completed."""
        return [t for t in self.tasks if not t.is_completed]

    def mark_task_complete(self, task: Task) -> Optional[Task]:
        """Mark a task complete and auto-create the next occurrence for recurring tasks."""
        task.mark_complete()
        if task.frequency == "daily":
            next_due = task.due_date + timedelta(days=1)
        elif task.frequency == "weekly":
            next_due = task.due_date + timedelta(weeks=1)
        else:
            return None
        next_task = Task(
            name=task.name,
            duration=task.duration,
            priority=task.priority,
            type=task.type,
            scheduled_time=task.scheduled_time,
            frequency=task.frequency,
            due_date=next_due,
        )
        self.add_task(next_task)
        return next_task
 
    def __str__(self) -> str:
        return (
            f"{self.name} ({self.species}, {self.age} yr old {self.gender}) — "
            f"{len(self.tasks)} task(s)"
        )
 
 
@dataclass
class Task:
    """Represents a single pet care activity."""

    name: str
    duration: int                     # in minutes
    priority: int                     # 1 (highest) to 5 (lowest)
    type: str                         # looked up in TASK_RULES (task_rules.json); unrecognized
                                       # types default to no attention required
    scheduled_time: str = ""          # e.g. "08:00"
    is_completed: bool = False
    frequency: str = "once"           # "once", "daily", "weekly"
    due_date: date = field(default_factory=date.today)
    attention_required: bool = field(init=False, default=False)
    exclusive_attention: bool = field(init=False, default=False)
    attention_reason: str = field(init=False, default="")
    original_scheduled_time: str = field(init=False, default="")

    def __post_init__(self):
        """Normalize scheduled_time and derive attention flags from a
        TASK_RULES lookup (task_rules.json). Unrecognized/custom types
        default to attention_required=False rather than erroring, so a typo
        or a brand-new type degrades safely instead of crashing.

        original_scheduled_time is captured once here and is NEVER touched
        again by anything else (in particular, revise_plan() only ever
        mutates scheduled_time). This is what lets Scheduler.generate_plan()
        offer a true "reset to what I actually entered" baseline, separate
        from wherever the agent's shifts have left scheduled_time."""
        self.scheduled_time = normalize_time(self.scheduled_time)
        self.original_scheduled_time = self.scheduled_time
        rule = TASK_RULES.get(self.type, {})
        self.attention_required = bool(rule.get("attention_required", False))
        self.exclusive_attention = bool(rule.get("exclusive_attention", False))
        self.attention_reason = rule.get("reason", "")

    def get_name(self) -> str:
        """Return the task name."""
        return self.name
 
    def get_duration(self) -> int:
        """Return the task duration in minutes."""
        return self.duration
 
    def get_priority(self) -> int:
        """Return the task priority level."""
        return self.priority
 
    def get_type(self) -> str:
        """Return the task type."""
        return self.type

    def get_attention_required(self) -> bool:
        """Return whether this task requires the owner's active attention."""
        return self.attention_required

    def get_exclusive_attention(self) -> bool:
        """Return whether this task requires the owner's full, undivided
        presence and cannot be combined with a task for another pet."""
        return self.exclusive_attention

    def get_attention_reason(self) -> str:
        """Return the human-readable reason for this task type's attention
        classification, as retrieved from task_rules.json."""
        return self.attention_reason

    def get_original_scheduled_time(self) -> str:
        """Return the task's originally entered scheduled time, unaffected
        by any agent-driven shifts made since."""
        return self.original_scheduled_time
 
    def set_priority(self, priority: int) -> None:
        """Update the task's priority level. Must be between 1 and 5."""
        if not 1 <= priority <= 5:
            raise ValueError("Priority must be between 1 (highest) and 5 (lowest).")
        self.priority = priority
 
    def mark_complete(self) -> None:
        """Mark the task as completed."""
        self.is_completed = True
 
    def __str__(self) -> str:
        time_label = f" at {self.scheduled_time}" if self.scheduled_time else ""
        status = "✓" if self.is_completed else "○"
        return (
            f"[{status}] {self.name}{time_label} "
            f"({self.duration} min, priority {self.priority}, {self.frequency}, due {self.due_date})"
        )
 
 
@dataclass
class Scheduler:
    """
    Sorts and fits all pet tasks within the owner's available hours to produce
    a daily plan, then runs an agentic self-correction loop: detect conflicts,
    shift the losing task, and re-check, up to a bounded number of attempts.
    """
    owner: Owner
    pets: List[Pet] = field(default_factory=list)
    tasks: List[Task] = field(default_factory=list)
    generated_plan: List[dict] = field(default_factory=list)
    reasoning: str = ""
    attempt_log: List[dict] = field(default_factory=list)
    unresolved_conflicts: List[str] = field(default_factory=list)
    skipped_tasks: List[str] = field(default_factory=list)

    DEFAULT_MAX_REVISION_ATTEMPTS = 5

    # Minutes of breathing room added after the winning task ends when the
    # agent shifts a losing task. Without this, a shifted task starts the
    # instant the other one finishes (e.g. grooming starting the same minute
    # a walk ends), which is technically non-overlapping but unrealistic —
    # real transitions (coming back inside, settling one pet before turning
    # to the next) take a few minutes even if nothing is formally scheduled.
    SHIFT_BUFFER_MINUTES = 5
 
    def _collect_tasks(self) -> List[Task]:
        """Gather all pending tasks from all pets."""
        all_tasks = []
        for pet in self.owner.pets:
            for task in pet.get_pending_tasks():
                all_tasks.append((pet, task))
        return all_tasks

    @staticmethod
    def _make_entry(pet: Pet, task:Task) -> dict:
        """
        Build a plan-row dict for a (pet, task) pair. Keeps a hidden Task reference (`_task`) so the 
        agentic loop can mutate the real object when it revises a schedule, not just the display dict. 
        """
        return {
            "pet": pet.name,
            "task": task.name,
            "type": task.type,
            "duration": task.duration,
            "priority": task.priority,
            "scheduled_time": task.scheduled_time,
            "is_completed": task.is_completed,
            "frequency": task.frequency,
            "attention_required": task.attention_required,
            "exclusive_attention": task.exclusive_attention,
            "attention_reason": task.attention_reason,
            "_task": task,
        }
    
    def generate_plan(
        self,
        max_revision_attempts: int = DEFAULT_MAX_REVISION_ATTEMPTS,
        reset_to_original: bool = False,
    ) -> List[dict]:
        """
        Sort all pending tasks by priority and duration, fit them into available hours,
        sort chronologically, then run the agentic conflict-resolution loop before returning
        the finalized plan.

        If reset_to_original is True, every pending task's scheduled_time is
        first restored to its original_scheduled_time (what was actually
        entered, before any prior agent shifts). This makes repeated calls
        idempotent — the same current inputs always produce the same output,
        rather than building on top of wherever a previous run's shifts left
        things. If False (the default), any prior agent-driven shifts are
        left as-is, and this run only reacts to what's changed since then
        (e.g. newly added or removed tasks) — this is the "Refresh" behavior
        in app.py, as opposed to "Generate", which resets.
        """
        available_minutes = self.owner.available_hours * 60
        pet_task_pairs = self._collect_tasks()

        if reset_to_original:
            for _, task in pet_task_pairs:
                task.scheduled_time = task.original_scheduled_time

        # Sort: priority ascending (1 first), then duration ascending
        pet_task_pairs.sort(key=lambda pt: (pt[1].priority, pt[1].duration))
 
        plan = []
        scheduled_minutes = 0
        skipped = []
 
        for pet, task in pet_task_pairs:
            if scheduled_minutes + task.duration <= available_minutes:
                plan.append(self._make_entry(pet, task))
                scheduled_minutes += task.duration
            else:
                skipped.append(f"{task.name} for {pet.name}")


        self.tasks = [pt[1] for pt in pet_task_pairs]
        self.skipped_tasks = skipped
        
        # Sort the plan chronologically by scheduled_time
        self.generated_plan = self.sort_by_time(plan)

        # Agentic self-correction loop
        self._run_agentic_loop(max_revision_attempts)
 
        # Build reasoning string (static summary of the initial fit/sort pass)
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        for entry in plan:
            label = self._priority_label(entry["priority"])
            priority_counts[label] += 1

        reasons = [
            f"Tasks were sorted by priority (high → medium → low), then by duration (shorter first).",
            f"Owner '{self.owner.name}' has {self.owner.available_hours}h "
            f"({available_minutes} min) available on a {self.owner.work_schedule} day.",
            f"{len(plan)} task(s) scheduled ({priority_counts['high']} high, "
            f"{priority_counts['medium']} medium, {priority_counts['low']} low), "
            f"using {scheduled_minutes} min.",
        ]
        if skipped:
            reasons.append(
                f"{len(skipped)} task(s) could not fit and were skipped: {', '.join(skipped)}."
            )
        self.reasoning = " ".join(reasons)
 
        return self.generated_plan

    def _run_agentic_loop(self, max_attempts: int) -> None:
        """
        Agentic loop: check for conflicts, revise (shift) one at a time, and re-check,
        up to max_attempts. Never loops indefinitely; if conflicts remain after the
        attempt budget is exhausted, logs a clear final 'unresolved' entry instead of
        silently dropping or crashing.
        """
        self.attempt_log = []
        attempts_used = 0
        loop_active = True

        while attempts_used < max_attempts and loop_active:
            conflicts = self.detect_conflicts()

            if not conflicts:
                loop_active = False
            else:
                attempts_used += 1
                result = self.revise_plan()

                if not result.get("resolved"):
                    # Defensive: detect_conflicts() found something but revise_plan()
                    # could not identify a fix. Stop rather than loop
                    self.attempt_log.append({
                        "attempt": attempts_used,
                        "status": "no valid shift found; stopping",
                    })
                    loop_active = False
                else:
                    self.attempt_log.append({
                        "attempt": attempts_used,
                        "status": "shifted",
                        "conflict": result["conflict"],
                        "shifted_task": result["shifted_task"],
                        "shifted_pet": result["shifted_pet"],
                        "old_time": result["old_time"],
                        "new_time": result["new_time"],
                    })

        self.unresolved_conflicts = self.detect_conflicts()
        if self.unresolved_conflicts:
            self.attempt_log.append({
                "attempt":  None,
                "status": (
                    f"stopped after {attempts_used} attempt(s); "
                    f"{len(self.unresolved_conflicts)} conflict(s) remain unresolved"
                ),
            })

    @staticmethod
    def _is_real_conflict(prev: dict, curr: dict) -> bool:
        """
        Determine whether an overlapping pair of plan entries is a REAL
        scheduling conflict:
          - Same pet, any task types -> conflict (a pet can't do two things
            at once, regardless of attention level).
          - Different pets -> conflict only if BOTH tasks require the owner's
            active attention AND at least one of them demands the owner's
            full, undivided presence (grooming, enrichment). Two combinable
            attention-required tasks for different pets (e.g. walking two
            dogs together) are NOT a conflict.
        """
        if prev["pet"] == curr["pet"]:
            return True

        both_attention = prev.get("attention_required", False) and curr.get("attention_required", False)
        either_exclusive = prev.get("exclusive_attention", False) or curr.get("exclusive_attention", False)
        return both_attention and either_exclusive

    def revise_plan(self) -> dict:
        """
        Find the first real conflict in the current plan and shift the losing
        task to start SHIFT_BUFFER_MINUTES after the winning task ends.

        Tie-break rules:
          - Lower-priority task shifts.
          - If priorities are equal, the shorter-duration task shifts.
          - If both are equal, the later task in the current sort order shifts
            (deterministic fallback so repeated runs behave identically).

        A zero-gap back-to-back shift is technically non-overlapping but
        unrealistic -- real transitions between tasks (and between pets) take
        a few minutes even if nothing is formally scheduled in between, so a
        small buffer is added on top of the overlap when the agent shifts a
        task. This buffer only applies to agent-driven shifts; it does not
        change how the original human-entered schedule is treated.

        Returns a dict describing what was done, or {"resolved": False} if no
        real conflict was found to revise.
        """
        timed = [e for e in self.generated_plan if e["scheduled_time"]]
 
        for i in range(1, len(timed)):
            prev = timed[i - 1]
            curr = timed[i]
 
            prev_start = self._time_to_minutes(prev["scheduled_time"])
            prev_end = prev_start + prev["duration"]
            curr_start = self._time_to_minutes(curr["scheduled_time"])
 
            if curr_start >= prev_end:
                continue  # no overlap between this adjacent pair
 
            if not self._is_real_conflict(prev, curr):
                continue  # overlap exists but isn't a *real* conflict under the attention-aware rule
 
            # Capture original times before anything is mutated, for an accurate log message
            prev_time_display = prev["scheduled_time"]
            curr_time_display = curr["scheduled_time"]
 
            # Decide which task shifts
            if prev["priority"] != curr["priority"]:
                loser, winner = (prev, curr) if prev["priority"] > curr["priority"] else (curr, prev)
            elif prev["duration"] != curr["duration"]:
                loser, winner = (prev, curr) if prev["duration"] < curr["duration"] else (curr, prev)
            else:
                loser, winner = curr, prev  # deterministic fallback
 
            old_time = loser["scheduled_time"]
            new_start_minutes = (
                self._time_to_minutes(winner["scheduled_time"])
                + winner["duration"]
                + self.SHIFT_BUFFER_MINUTES
            )
            new_time = self._minutes_to_time(new_start_minutes)
 
            # Apply the shift to both the real Task object and the display dict
            loser["_task"].scheduled_time = new_time
            loser["scheduled_time"] = new_time
 
            self.generated_plan = self.sort_by_time(self.generated_plan)
 
            return {
                "resolved": True,
                "conflict": (
                    f"[{curr['pet']}] '{curr['task']}' at {curr_time_display} "
                    f"vs [{prev['pet']}] '{prev['task']}' at {prev_time_display}"
                ),
                "shifted_task": loser["task"],
                "shifted_pet": loser["pet"],
                "old_time": old_time,
                "new_time": new_time,
            }
 
        return {"resolved": False}
    
    def detect_conflicts(self) -> List[str]:
        """
        Scan the sorted plan for overlapping tasks, using the attention-aware rule:
        a real conflict is either (a) two tasks for the 'same' pet overlapping,
        regardless of type, or (b) two tasks for 'different' pets overlapping where
        both require the owner's active attention AND at least one of them demands
        the owner's full, undivided presence (grooming, enrichment). Two combinable
        attention-required tasks for different pets (e.g. walking two dogs together)
        are NOT flagged, nor are cross-pet overlaps of low-attention tasks (e.g. two
        breakfasts at the same time).
        A conflict occurs when a task's start time falls before the previous task finishes.
        Returns a list of warning strings (empty list = no conflicts).
        """
        warnings = []
        timed = [e for e in self.generated_plan if e["scheduled_time"]]

        for i in range(1, len(timed)):
            prev = timed[i - 1]
            curr = timed[i]

            prev_start = self._time_to_minutes(prev["scheduled_time"])
            prev_end   = prev_start + prev["duration"]
            curr_start = self._time_to_minutes(curr["scheduled_time"])

            if curr_start < prev_end:
                if not self._is_real_conflict(prev, curr):
                    continue

                overlap = prev_end - curr_start
                warnings.append(
                    f"⚠️  Conflict: [{curr['pet']}] '{curr['task']}' at {curr['scheduled_time']} "
                    f"overlaps with [{prev['pet']}] '{prev['task']}' at {prev['scheduled_time']} "
                    f"by {overlap} min."
                )

        return warnings

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        """Convert a 'HH:MM' string to total minutes since midnight."""
        hours, minutes = map(int, time_str.split(":"))
        return hours * 60 + minutes

    @staticmethod
    def _minutes_to_time(total_minutes: int) -> str:
        """Convert total minutes since midnight back to a 'H:MM' string."""
        total_minutes = total_minutes % (24 * 60)
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours:02d}:{minutes:02d}"
    
    @staticmethod
    def sort_by_time(plan: List[dict]) -> List[dict]:
        """Sort a plan list chronologically; tasks with no scheduled_time go to the end."""
        return sorted(
            plan,
            # "99:99" sentinel sorts after any real HH:MM, pushing timeless tasks to the end
            key=lambda entry: entry["scheduled_time"] if entry["scheduled_time"] else "99:99"
        )

    def filter_plan(
        self,
        pet_name: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> List[dict]:
        """Return a filtered subset of the generated plan by pet name and/or completion status."""
        result = self.generated_plan
        if pet_name is not None:
            result = [e for e in result if e["pet"].lower() == pet_name.lower()]
        if completed is not None:
            result = [e for e in result if e.get("is_completed", False) == completed]
        return result

    def explain_reasoning(self) -> str:
        """
        Return a human-readable explanation of how the plan was generated, including a summary of 
        the agent's conflict-resolution attempts (not just the final state).
        """
        if not self.reasoning:
            return "No plan has been generated yet. Call generate_plan() first."

        parts = [self.reasoning]

        if self.attempt_log:
            parts.append("Agentic conflict resolution:")
            for entry in self.attempt_log:
                if entry.get("status") == "shifted":
                    parts.append(
                        f"Attempt {entry['attempt']}: shifted {entry['shifted_pet']}'s "
                        f"'{entry['shifted_task']}' from {entry['old_time']} to {entry['new_time']} "
                        f"to resolve a conflict with {entry['conflict']}."
                    )
                elif entry.get("attempt") is None:
                    parts.append(entry["status"].capitalize() + ".")
                else:
                    parts.append(f"Attempt {entry['attempt']}: {entry['status']}.")
                        
        return " ".join(parts)
 
    @staticmethod
    def _priority_label(priority: int) -> str:
        """Convert numeric priority to a human-readable label."""
        return {1: "high", 2: "high", 3: "medium", 4: "low", 5: "low"}.get(priority, str(priority))
 
    def display_plan(self) -> None:
        """Print the daily plan to the console in a readable format."""
        if not self.generated_plan:
            print("No plan generated yet. Call generate_plan() first.")
            return
 
        total = sum(e["duration"] for e in self.generated_plan)
 
        # --- Combined timeline ---
        print(f"\n{'='*52}")
        print(f"  PawPal+ Daily Plan for {self.owner.name} (Owner)")
        print(f"{'='*52}")
        for entry in self.generated_plan:
            time_label = entry["scheduled_time"] if entry["scheduled_time"] else "--:--"
            priority_label = self._priority_label(entry["priority"])
            print(
                f"  {time_label} — [{entry['pet']}] {entry['task']} "
                f"({entry['duration']} min) [priority: {priority_label}]"
            )
        print(f"\n  Total time: {total} min ({total // 60}h {total % 60}m)")
        print(f"  Reasoning: {self.reasoning}")

        # --- Conflict warnings ---
        conflicts = self.detect_conflicts()
        if conflicts:
            print()
            for warning in conflicts:
                print(f"  {warning}")

        # --- Per-pet breakdown ---
        print(f"\n{'─'*52}")
        print("  Breakdown by pet")
        print(f"{'─'*52}")
        for pet in self.owner.pets:
            pet_entries = [e for e in self.generated_plan if e["pet"] == pet.name]
            if not pet_entries:
                continue
            print(f"\n  {pet.name} ({pet.species}, {pet.age} yr old {pet.gender})")
            for entry in pet_entries:
                time_label = entry["scheduled_time"] if entry["scheduled_time"] else "--:--"
                priority_label = self._priority_label(entry["priority"])
                print(
                    f"    {time_label} — {entry['task']} "
                    f"({entry['duration']} min) [priority: {priority_label}]"
                )
        print(f"\n{'='*52}\n")