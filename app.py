"""
app.py - PawPal+ Streamlit UI
Connects the frontend to the backend logic in pawpal_system.py.
"""

import streamlit as st
from pawpal_system import Owner, Pet, Task, Scheduler, normalize_time, TASK_RULES

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
st.title("🐾 PawPal+")
st.caption("A smart daily care planner for your pets.")
st.divider()

# ---------------------------------------------------------------------------
# Session state initialisation
# owner.pets is the single source of truth for which pets exist — no separate
# "pets" list is kept, so there's nothing that can drift out of sync with it.
# ---------------------------------------------------------------------------
if "owner" not in st.session_state:
    st.session_state.owner = None
if "schedule" not in st.session_state:
    st.session_state.schedule = None
if "last_action" not in st.session_state:
    st.session_state.last_action = None
if "editing_task_key" not in st.session_state:
    st.session_state.editing_task_key = None  # (pet_name, task_index) of the task being edited, or None


def _auto_regenerate() -> None:
    """
    Recompute the schedule immediately after any change to owner/pet/task
    data, so nothing requires a manual button click to stay current. Uses
    incremental ("Refresh") semantics — reset_to_original=False — so tasks
    that weren't touched keep whatever the agent already decided, and only
    what actually changed gets re-evaluated. This is intentionally NOT a
    full reset: that's what the explicit "Generate schedule" button is for,
    when you want to discard prior adjustments and start clean on purpose.

    If there's nothing schedulable yet (no owner, no pets, or no tasks),
    this just clears the schedule instead of erroring.
    """
    owner = st.session_state.owner
    if owner is not None and owner.pets and any(p.get_tasks() for p in owner.pets):
        scheduler = Scheduler(owner=owner)
        scheduler.generate_plan(reset_to_original=False)
        st.session_state.schedule = scheduler
        st.session_state.last_action = "auto"
    else:
        st.session_state.schedule = None
        st.session_state.last_action = None


# ---------------------------------------------------------------------------
# Section 1 — Owner setup
# ---------------------------------------------------------------------------
st.subheader("1. Owner info & availability")

with st.form("owner_form"):
    owner_name = st.text_input("Your name", placeholder="e.g. Alex")
    col1, col2 = st.columns(2)
    with col1:
        work_schedule = st.selectbox("Today's schedule", ["office", "remote", "off"])
        morning_start = st.text_input("Morning start time", value="07:00")
    with col2:
        available_hours = st.slider("Free hours today", min_value=1, max_value=16, value=3)
        evening_end = st.text_input("Evening end time", value="21:00")

    submitted_owner = st.form_submit_button("Save owner")

if submitted_owner:
    normalized_morning = normalize_time(morning_start)
    normalized_evening = normalize_time(evening_end)

    if not normalized_morning:
        st.warning(
            f"⚠️ '{morning_start}' is not a valid time for Morning start time. "
            "Please use HH:MM (e.g. 07:00 or 8:30). Owner info was not saved."
        )
    elif not normalized_evening:
        st.warning(
            f"⚠️ '{evening_end}' is not a valid time for Evening end time. "
            "Please use HH:MM (e.g. 07:00 or 8:30). Owner info was not saved."
        )
    else:
        if st.session_state.owner is None:
            st.session_state.owner = Owner(name=owner_name)
        else:
            # Update the EXISTING owner object in place, rather than discarding
            # it and rebuilding a new one. This is what actually fixes the bug:
            # previously, re-saving owner info created a brand-new Owner and
            # manually re-attached pets from a separate list — a second point of
            # truth that could (and did) drift out of sync. Mutating in place
            # means pets already attached to this owner are simply never touched.
            st.session_state.owner.name = owner_name
        st.session_state.owner.set_availability(
            work_schedule=work_schedule,
            available_hours=available_hours,
            preferred_morning_start=normalized_morning,
            preferred_evening_end=normalized_evening,
        )
        _auto_regenerate()
        st.success(f"Saved: {st.session_state.owner}")

if st.session_state.owner is not None:
    if st.button("🗑️ Remove owner (clears all pets and tasks)", key="remove_owner"):
        st.session_state.owner = None
        _auto_regenerate()
        st.rerun()


# ---------------------------------------------------------------------------
# Section 2 — Add a pet
# ---------------------------------------------------------------------------
st.divider()
st.subheader("2. Add a pet")

with st.form("pet_form"):
    col1, col2 = st.columns(2)
    with col1:
        pet_name    = st.text_input("Pet name", placeholder="e.g. Buddy")
        species     = st.selectbox("Species", ["Dog", "Cat", "Rabbit", "Bird", "Other"])
        gender      = st.selectbox("Gender", ["Male", "Female"])
    with col2:
        age             = st.number_input("Age (years)", min_value=0, max_value=30, value=0)
        health_history  = st.text_input("Health history (optional)", placeholder="e.g. Neutered, no known allergies")
        medical_needs   = st.text_input("Medical needs (optional)", placeholder="e.g. Heartworm medication daily")

    submitted_pet = st.form_submit_button("Add pet")

if submitted_pet:
    if st.session_state.owner is None:
        st.warning("Please save owner info first.")
    elif not pet_name.strip():
        st.warning("⚠️ Pet name can't be blank. Please enter a name and try again.")
    elif any(p.name == pet_name.strip() for p in st.session_state.owner.pets):
        st.warning(
            f"⚠️ You already have a pet named '{pet_name.strip()}'. "
            "Please use a different name — tasks are assigned by pet name, "
            "so duplicate names can cause tasks to go to the wrong pet."
        )
    else:
        pet = Pet(
            name=pet_name.strip(),
            species=species,
            gender=gender,
            age=age,
            health_history=health_history,
            medical_needs=medical_needs,
        )
        st.session_state.owner.add_pet(pet)
        _auto_regenerate()
        st.success(f"Added pet: {pet}")

# Show registered pets with remove buttons
if st.session_state.owner is not None and st.session_state.owner.pets:
    st.markdown("**Registered pets:**")
    for i, p in enumerate(st.session_state.owner.pets):
        col_pet, col_btn = st.columns([5, 1])
        with col_pet:
            st.markdown(f"- {p}")
        with col_btn:
            if st.button("🗑️", key=f"remove_pet_{i}", help=f"Remove {p.name}"):
                st.session_state.owner.pets.pop(i)
                _auto_regenerate()
                st.rerun()


# ---------------------------------------------------------------------------
# Section 3 — Add tasks
# ---------------------------------------------------------------------------
st.divider()
st.subheader("3. Add tasks")

# Task types and their attention classification (icon, reason) come from
# TASK_RULES, loaded from task_rules.json — adding a new type (e.g. a vet
# visit or training session) only requires editing that file; the dropdown
# below and its caption update automatically with no code changes here.


def _format_type_label(type_str: str) -> str:
    """Human-friendly display label for a task type identifier: replaces
    underscores with spaces for multi-word types (e.g. 'dog_park' -> 'dog
    park'). The underlying identifier stored on Task.type — and the key
    used to look it up in task_rules.json — is unchanged; this only affects
    what's shown on screen."""
    return type_str.replace("_", " ")


if st.session_state.owner is None or not st.session_state.owner.pets:
    st.info("Add at least one pet above before adding tasks.")
else:
    # Type lives outside the form so its caption updates immediately on
    # selection — widgets inside st.form() don't trigger a rerun until submit.
    task_type = st.selectbox(
        "Type", list(TASK_RULES.keys()), key="task_type_selector",
        format_func=_format_type_label,
    )
    rule = TASK_RULES.get(task_type, {})
    icon = rule.get("icon", "❔")
    reason = rule.get("reason", "No classification info available for this type — treated as needing no active attention.")
    st.caption(f"{icon} {reason}")

    with st.form("task_form"):
        col1, col2 = st.columns(2)
        with col1:
            assign_to   = st.selectbox("Assign to pet", [p.name for p in st.session_state.owner.pets])
            task_name   = st.text_input("Task name", placeholder="e.g. Morning walk")
        with col2:
            duration        = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=15)
            priority        = st.selectbox("Priority", ["1 — high", "2 — high", "3 — medium", "4 — low", "5 — low"])
            scheduled_time  = st.text_input("Scheduled time (optional)", placeholder="e.g. 07:00")
            frequency       = st.selectbox("Frequency", ["once", "daily", "weekly"])

        submitted_task = st.form_submit_button("Add task")

    if submitted_task:
        priority_int = int(priority[0])
        normalized_time = normalize_time(scheduled_time)

        if not task_name.strip():
            st.warning("⚠️ Task name can't be blank. Please enter a name and try again.")
        elif scheduled_time.strip() and not normalized_time:
            # Warn if user entered something but it couldn't be parsed
            st.warning(
                f"⚠️ '{scheduled_time}' is not a valid time format. "
                "Please use HH:MM (e.g. 07:00 or 8:30). Task was not added."
            )
        else:
            task = Task(
                name=task_name.strip(),
                duration=int(duration),
                priority=priority_int,
                type=task_type,
                scheduled_time=scheduled_time,  # __post_init__ normalizes automatically
                frequency=frequency,
            )
            for pet in st.session_state.owner.pets:
                if pet.name == assign_to:
                    pet.add_task(task)
                    _auto_regenerate()
                    time_display = f" at {task.scheduled_time}" if task.scheduled_time else ""
                    st.success(f"Added task '{task.name}'{time_display} to {assign_to}.")
                    break

    # Show current tasks per pet, with edit and remove controls.
    # Editing mutates the SAME Task object (preserving its identity) rather
    # than deleting and re-adding, so "Refresh" has something meaningful to
    # preserve for tasks you didn't touch. Editing the scheduled time treats
    # the new value as a fresh baseline (re-running __post_init__ resets
    # original_scheduled_time to it), since a manual edit is a deliberate
    # new intent, not something the agent should later "undo" back to an
    # older original.
    type_options = list(TASK_RULES.keys())
    priority_labels = ["1 — high", "2 — high", "3 — medium", "4 — low", "5 — low"]
    frequency_options = ["once", "daily", "weekly"]

    for pet in st.session_state.owner.pets:
        if pet.get_tasks():
            st.markdown(f"**{pet.name}'s tasks:**")
            for i, t in enumerate(pet.get_tasks()):
                task_key = f"{pet.name}_{i}"

                if st.session_state.editing_task_key == task_key:
                    # --- Inline edit form, pre-filled with current values ---
                    try:
                        type_index = type_options.index(t.type)
                    except ValueError:
                        type_index = 0
                    try:
                        freq_index = frequency_options.index(t.frequency)
                    except ValueError:
                        freq_index = 0
                    priority_index = min(max(t.priority - 1, 0), 4)

                    with st.form(f"edit_form_{task_key}"):
                        ecol1, ecol2 = st.columns(2)
                        with ecol1:
                            edit_name = st.text_input("Task name", value=t.name)
                            edit_type = st.selectbox(
                                "Type", type_options, index=type_index,
                                format_func=_format_type_label,
                            )
                        with ecol2:
                            edit_duration = st.number_input(
                                "Duration (minutes)", min_value=1, max_value=240, value=t.duration
                            )
                            edit_priority = st.selectbox("Priority", priority_labels, index=priority_index)
                            edit_time = st.text_input(
                                "Scheduled time (optional)", value=t.original_scheduled_time
                            )
                            edit_frequency = st.selectbox("Frequency", frequency_options, index=freq_index)

                        save_col, cancel_col = st.columns(2)
                        with save_col:
                            save_clicked = st.form_submit_button("💾 Save changes")
                        with cancel_col:
                            cancel_clicked = st.form_submit_button("Cancel")

                    if save_clicked:
                        normalized_edit_time = normalize_time(edit_time)
                        if not edit_name.strip():
                            st.warning("⚠️ Task name can't be blank.")
                        elif edit_time.strip() and not normalized_edit_time:
                            st.warning(
                                f"⚠️ '{edit_time}' is not a valid time format. "
                                "Please use HH:MM (e.g. 07:00 or 8:30). Changes were not saved."
                            )
                        else:
                            t.name = edit_name.strip()
                            t.type = edit_type
                            t.duration = int(edit_duration)
                            t.priority = int(edit_priority[0])
                            t.scheduled_time = edit_time
                            t.frequency = edit_frequency
                            t.__post_init__()  # re-derive attention flags; resets original_scheduled_time to edit_time
                            _auto_regenerate()
                            st.session_state.editing_task_key = None
                            st.success(f"Updated '{t.name}'.")
                            st.rerun()
                    elif cancel_clicked:
                        st.session_state.editing_task_key = None
                        st.rerun()

                else:
                    # --- Static display row ---
                    col_task, col_edit, col_del = st.columns([5, 1, 1])
                    with col_task:
                        st.markdown(f"- {t}")
                    with col_edit:
                        if st.button("✏️", key=f"edit_task_{task_key}", help=f"Edit {t.name}"):
                            st.session_state.editing_task_key = task_key
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"remove_task_{task_key}", help=f"Remove {t.name}"):
                            pet.tasks.pop(i)
                            _auto_regenerate()
                            if st.session_state.editing_task_key == task_key:
                                st.session_state.editing_task_key = None
                            st.rerun()


# ---------------------------------------------------------------------------
# Section 4 — Generate schedule
# ---------------------------------------------------------------------------
st.divider()
st.subheader("4. Generate today's plan")


def _attention_label(entry: dict) -> str:
    """Short display label for a plan entry's attention requirement, matching
    the icons introduced in Section 3 so the same rule reads consistently
    at input time and at plan-review time."""
    if entry.get("exclusive_attention"):
        return "🔒 Exclusive"
    if entry.get("attention_required"):
        return "👀 Combinable"
    return "—"


st.caption("The plan below updates automatically as you add, edit, or delete pets and tasks.")
generate_clicked = st.button(
    "Generate schedule", type="primary",
    help="Reset every task to the time you originally entered, then build a fresh plan. "
         "Use this when you want to discard any adjustments the assistant has already made "
         "and start clean — everything else updates automatically without needing this button.",
)

if generate_clicked:
    if st.session_state.owner is None:
        st.warning("Please save owner info first.")
    elif not st.session_state.owner.pets:
        st.warning("Please add at least one pet.")
    elif not any(p.get_tasks() for p in st.session_state.owner.pets):
        st.warning("Please add at least one task.")
    else:
        scheduler = Scheduler(owner=st.session_state.owner)
        scheduler.generate_plan(reset_to_original=True)
        st.session_state.schedule = scheduler
        st.session_state.last_action = "generate"

if st.session_state.schedule:
    sched = st.session_state.schedule
    plan  = sched.generated_plan
    owner = st.session_state.owner

    if plan:
        total        = sum(e["duration"] for e in plan)
        total_avail  = owner.available_hours * 60
        remaining    = total_avail - total

        mode_note = (
            " (built fresh from your originally entered times)"
            if st.session_state.last_action == "generate"
            else " (auto-updated after your last change)"
            if st.session_state.last_action == "auto"
            else ""
        )
        st.success(
            f"Plan generated{mode_note}: {len(plan)} task(s) scheduled, "
            f"{total} min used, {remaining} min remaining."
        )

        # --- Conflict summary (concise pointer, not the full detail) ---
        conflicts = sched.detect_conflicts()
        if conflicts:
            st.warning(
                f"⚠️ {len(conflicts)} conflict(s) could not be resolved automatically. "
                "See \"Why this plan?\" below for what the assistant tried and the specific overlaps."
            )

        # --- Skipped task warning ---
        if sched.skipped_tasks:
            st.warning(
                f"⚠️ {len(sched.skipped_tasks)} task(s) didn't fit in your available time and were skipped: "
                f"{', '.join(sched.skipped_tasks)}. Consider increasing your free hours or reducing task durations."
            )

        # --- Combined timeline as table ---
        st.markdown("#### Combined timeline")
        timeline_rows = [
            {
                "Time":      entry["scheduled_time"] if entry["scheduled_time"] else "--:--",
                "Pet":       entry["pet"],
                "Task":      entry["task"],
                "Type":      _format_type_label(entry["type"]),
                "Attention": _attention_label(entry),
                "Duration":  f"{entry['duration']} min",
                "Priority":  Scheduler._priority_label(entry["priority"]),
                "Frequency": entry.get("frequency", "once"),
            }
            for entry in plan
        ]
        st.table(timeline_rows)
        st.caption("🔒 Exclusive = needs your full presence, can't overlap another pet's task. 👀 Combinable = needs attention, but can be shared across pets. ➖ = no active attention needed.")
        st.markdown(f"**Total time:** {total} min ({total // 60}h {total % 60}m) of {total_avail} min available.")

        # --- Reasoning expander — single source of truth for the full story ---
        with st.expander("Why this plan?"):
            st.info(sched.reasoning)

            if sched.attempt_log:
                st.markdown("**🤖 Agentic conflict resolution:**")
                for entry in sched.attempt_log:
                    if entry.get("status") == "shifted":
                        st.write(
                            f"Attempt {entry['attempt']}: shifted **{entry['shifted_pet']}**'s "
                            f"'{entry['shifted_task']}' from {entry['old_time']} → {entry['new_time']} "
                            f"to resolve a conflict."
                        )
                    elif entry.get("attempt") is None:
                        st.warning(entry["status"].capitalize() + ".")
                    else:
                        st.write(f"Attempt {entry['attempt']}: {entry['status']}.")
            else:
                st.caption("No conflicts required resolution — the plan was clean on the first pass.")

            if conflicts:
                st.markdown("**⚠️ Unresolved conflicts (specific overlaps):**")
                for warning in conflicts:
                    st.write(warning)

        # --- Per-pet breakdown as tables ---
        st.markdown("#### Breakdown by pet")
        for pet in owner.pets:
            pet_entries = [e for e in plan if e["pet"] == pet.name]
            if not pet_entries:
                continue
            st.markdown(f"**{pet.name}** ({pet.species}, {pet.age} yr old {pet.gender})")
            pet_rows = [
                {
                    "Time":      e["scheduled_time"] if e["scheduled_time"] else "--:--",
                    "Task":      e["task"],
                    "Type":      _format_type_label(e["type"]),
                    "Attention": _attention_label(e),
                    "Duration":  f"{e['duration']} min",
                    "Priority":  Scheduler._priority_label(e["priority"]),
                    "Frequency": e.get("frequency", "once"),
                }
                for e in pet_entries
            ]
            st.table(pet_rows)

    else:
        st.warning("⚠️ No tasks could be scheduled. Try increasing your available hours or shortening task durations.")