"""
Streakly: habit completion, XP and streak logic.

A habit counts as completed on a day only when the TimeLog minutes for that
habit on that day reach habit.daily_goal_minutes. Nothing here is marked by hand.
"""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import HabitLog, TimeLog, UserProfile

XP_PER_HABIT = 10


def get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def minutes_today(user, habit, today=None):
    today = today or timezone.localdate()
    total = (TimeLog.objects
             .filter(user=user, habit=habit, date=today)
             .aggregate(t=Sum('duration_minutes'))['t'])
    return total or 0


def streak_from_dates(dates, today=None):
    """Consecutive days ending today (or yesterday, if today is not done yet)."""
    today = today or timezone.localdate()
    d = today if today in dates else today - timedelta(days=1)
    n = 0
    while d in dates:
        n += 1
        d -= timedelta(days=1)
    return n


def refresh_streaks(user, habit):
    """Recalculate and save the habit streak and the overall (profile) streak."""
    today = timezone.localdate()

    habit_dates = set(HabitLog.objects
                      .filter(user=user, habit=habit, completed=True)
                      .values_list('date', flat=True))
    habit.streak = streak_from_dates(habit_dates, today)
    habit.last_completed = max(habit_dates) if habit_dates else None
    habit.save(update_fields=['streak', 'last_completed'])

    all_dates = set(HabitLog.objects
                    .filter(user=user, completed=True)
                    .values_list('date', flat=True))
    profile = get_profile(user)
    profile.current_streak = streak_from_dates(all_dates, today)
    profile.save(update_fields=['current_streak'])


def award_if_goal_reached(user, habit):
    """
    Call right after a TimeLog is saved.
    Gives XP only once per habit per day, the first time the goal is reached.
    Returns {'reached': bool, 'awarded': bool, 'xp': int, 'minutes': int}.
    """
    if habit is None:
        return {'reached': False, 'awarded': False, 'xp': 0, 'minutes': 0}

    today = timezone.localdate()
    minutes = minutes_today(user, habit, today)
    goal = habit.daily_goal_minutes or 1

    if minutes < goal:
        return {'reached': False, 'awarded': False, 'xp': 0, 'minutes': minutes}

    log = HabitLog.objects.filter(user=user, habit=habit, date=today).first()
    newly = False
    if log is None:
        HabitLog.objects.create(user=user, habit=habit, date=today, completed=True)
        newly = True
    elif not log.completed:
        log.completed = True
        log.save(update_fields=['completed'])
        newly = True

    if newly:
        get_profile(user).add_xp(XP_PER_HABIT)
        refresh_streaks(user, habit)

    return {'reached': True, 'awarded': newly,
            'xp': XP_PER_HABIT if newly else 0, 'minutes': minutes}


def apply_live_streaks(user, habits):
    """
    For display: sets habit.streak on each habit object from real logs
    (one query), so a broken streak shows 0 even before the next completion.
    Does not write to the database.
    """
    today = timezone.localdate()
    by_habit = {}
    for habit_id, d in (HabitLog.objects
                        .filter(user=user, completed=True)
                        .values_list('habit_id', 'date')):
        by_habit.setdefault(habit_id, set()).add(d)
    for h in habits:
        h.streak = streak_from_dates(by_habit.get(h.id, set()), today)
    return habits