"""
main.py - PawPal+ demo script
Testing ground for verifying backend logic in the terminal.
Run with: python main.py
"""

from pawpal_system import Owner, Pet, Task, Scheduler, TASK_RULES
from datetime import date


# --- 1. Create owner and set availability ---
owner = Owner(name="Alex")
owner.set_availability(
    work_schedule="office",
    available_hours=3,
    preferred_morning_start="07:00",
    preferred_evening_end="20:00",
)

# --- 2. Create pets ---
dog = Pet(name="Buddy", species="Dog", gender="Male", age=3)
cat = Pet(name="Luna",  species="Cat", gender="Female", age=2)

# --- 3. Add tasks to Buddy (dog) ---
# Note: Breakfast starts at 07:00 and takes 10 min (ends 07:10)
#       Heartworm pill starts at 07:05 → same-pet conflict; the agentic loop
#       inside generate_plan() will auto-shift Heartworm pill to 07:10.
dog.add_task(Task("Breakfast",      10, priority=1, type="feeding",    scheduled_time="07:00", frequency="daily"))
dog.add_task(Task("Heartworm pill",  5, priority=1, type="medication", scheduled_time="07:05", frequency="once"))
dog.add_task(Task("Morning walk",   30, priority=2, type="walk",       scheduled_time="07:30", frequency="daily"))
dog.add_task(Task("Evening walk",   30, priority=2, type="walk",       scheduled_time="18:00", frequency="daily"))

# --- 4. Add tasks to Luna (cat) ---
# Note: Luna's Breakfast is also at 07:00, but cross-pet feeding overlaps are
#       NOT conflicts (feeding needs no active attention, so it can happen
#       for two pets in parallel) — no warning, no shift.
#       Brushing at 07:45 overlaps with Buddy's Morning walk (07:30–08:00):
#       grooming requires the owner's full, undivided presence, so the owner
#       can't be fully dedicated to brushing Luna while also walking Buddy.
#       This IS a real cross-pet conflict, and the agent will shift the
#       lower-priority task (Brushing) to start once the walk ends (plus a
#       short buffer).
#       Playtime at 19:00 doesn't overlap with anything, so it's unaffected —
#       but note enrichment also requires the owner's full presence, same as
#       grooming.
cat.add_task(Task("Breakfast",  5, priority=1, type="feeding",    scheduled_time="07:00", frequency="daily"))
cat.add_task(Task("Playtime",  20, priority=4, type="enrichment", scheduled_time="19:00", frequency="daily"))
cat.add_task(Task("Brushing",  15, priority=3, type="grooming",   scheduled_time="07:45", frequency="weekly"))

# --- 5. Register pets under owner ---
owner.add_pet(dog)
owner.add_pet(cat)

# --- 6. Generate and display schedule (conflict warnings appear automatically) ---
scheduler = Scheduler(owner=owner)
scheduler.generate_plan()
scheduler.display_plan()

# --- 7. Demo: inspect the agent's work directly ---
print("=== Agentic conflict resolution (direct call) ===")
conflicts = scheduler.detect_conflicts()
if conflicts:
    print(f"  {len(conflicts)} conflict(s) still unresolved:")
    for w in conflicts:
        print(f"  {w}")
else:
    print("  No conflicts remain — any fixable overlaps were auto-resolved.")

print(f"\n  {len(scheduler.attempt_log)} revision attempt(s) logged:")
for entry in scheduler.attempt_log:
    print(f"    {entry}")

print("\n  Full reasoning (static summary + agent narrative):")
print(f"  {scheduler.explain_reasoning()}")

# --- 7b. Demo: cross-pet attention rules — combinable vs. exclusive ---
print("\n=== Cross-pet attention rules: walking two dogs together vs. grooming two pets ===")

combinable_owner = Owner(name="Sam")
combinable_owner.set_availability(
    work_schedule="remote", available_hours=4,
    preferred_morning_start="07:00", preferred_evening_end="20:00",
)
rex  = Pet(name="Rex",  species="Dog", gender="Male",   age=4)
mochi = Pet(name="Mochi", species="Dog", gender="Female", age=2)
rex.add_task(Task("Morning walk", 30, priority=2, type="walk", scheduled_time="08:00"))
mochi.add_task(Task("Morning walk", 30, priority=2, type="walk", scheduled_time="08:00"))
combinable_owner.add_pet(rex)
combinable_owner.add_pet(mochi)
combinable_scheduler = Scheduler(owner=combinable_owner)
combinable_scheduler.generate_plan()
print("  Two dogs walked at the same time (combinable):")
print(f"    conflicts: {combinable_scheduler.detect_conflicts()}")
print(f"    attempt_log: {combinable_scheduler.attempt_log}  (empty = no action needed)")

exclusive_owner = Owner(name="Sam")
exclusive_owner.set_availability(
    work_schedule="remote", available_hours=4,
    preferred_morning_start="07:00", preferred_evening_end="20:00",
)
rex2  = Pet(name="Rex",  species="Dog", gender="Male",   age=4)
mochi2 = Pet(name="Mochi", species="Dog", gender="Female", age=2)
rex2.add_task(Task("Grooming", 20, priority=2, type="grooming", scheduled_time="08:00"))
mochi2.add_task(Task("Grooming", 20, priority=2, type="grooming", scheduled_time="08:00"))
exclusive_owner.add_pet(rex2)
exclusive_owner.add_pet(mochi2)
exclusive_scheduler = Scheduler(owner=exclusive_owner)
exclusive_scheduler.generate_plan()
print("\n  Two dogs groomed at the same time (exclusive):")
print(f"    conflicts: {exclusive_scheduler.detect_conflicts()}")
print(f"    attempt_log: {exclusive_scheduler.attempt_log}")

# --- 7c. Demo: task types come from task_rules.json, not hardcoded Python ---
print("\n=== Task types are loaded from task_rules.json ===")
print(f"  Available types: {list(TASK_RULES.keys())}")
print("  New types (dog_park, vet_visit, training) work with zero code changes —")
print("  they were added by editing task_rules.json, not pawpal_system.py.\n")

rules_owner = Owner(name="Sam")
rules_owner.set_availability(
    work_schedule="remote", available_hours=4,
    preferred_morning_start="07:00", preferred_evening_end="20:00",
)
buddy2 = Pet(name="Buddy", species="Dog", gender="Male", age=3)
luna2 = Pet(name="Luna", species="Cat", gender="Female", age=2)
buddy2.add_task(Task("Trip to the dog park", 45, priority=2, type="dog_park", scheduled_time="09:00"))
luna2.add_task(Task("Annual checkup", 30, priority=1, type="vet_visit", scheduled_time="09:00"))
rules_owner.add_pet(buddy2)
rules_owner.add_pet(luna2)
rules_scheduler = Scheduler(owner=rules_owner)
rules_scheduler.generate_plan()
print("  dog_park (combinable) vs. vet_visit (exclusive), different pets, same time:")
print(f"    conflicts: {rules_scheduler.detect_conflicts()}")
print(f"    attempt_log: {rules_scheduler.attempt_log}")

# --- 8. Demo: recurring tasks ---
print("\n=== Recurring task demo ===")
print(f"Today: {date.today()}\n")

breakfast = next(t for t in dog.get_tasks() if t.name == "Breakfast" and not t.is_completed)
next_task = dog.mark_task_complete(breakfast)
print(f"Marked '{breakfast.name}' complete (frequency: {breakfast.frequency})")
if next_task:
    print(f"Auto-created next occurrence: due {next_task.due_date}")

pill = next(t for t in dog.get_tasks() if t.name == "Heartworm pill")
result = dog.mark_task_complete(pill)
print(f"\nMarked 'Heartworm pill' complete (frequency: {pill.frequency})")
print(f"New task created: {result is not None}  ← expected False for 'once'")