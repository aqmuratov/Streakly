import calendar
import json
from datetime import date, datetime, time as dtime, timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Challenge, Habit, HabitLog, RoutineItem, Task, TimeLog, UserProfile
from .onboarding import QUESTIONS, apply_onboarding, build_plan, lesson_of_the_day, validate_answers
from .services import apply_live_streaks, award_if_goal_reached, streak_from_dates


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def register_view(request):
    if request.user.is_authenticated:
        return redirect('today')

    # Ro'yxatdan o'tishdan oldin savolnoma to'ldirilgan bo'lishi kerak
    answers = request.session.get('onboarding')
    if not answers:
        return redirect('onboarding')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.first_name = request.POST.get('first_name', '').strip()[:30]
            user.save(update_fields=['first_name'])
            UserProfile.objects.get_or_create(user=user)
            apply_onboarding(user, answers)
            request.session.pop('onboarding', None)
            login(request, user)
            messages.success(request, "Твой план готов. Начинаем!")
            return redirect('today')
    else:
        form = UserCreationForm()

    return render(request, 'dashboard/register.html', {
        'form': form,
        'first_name': request.POST.get('first_name', ''),
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect('today')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('today')
    else:
        form = AuthenticationForm()

    return render(request, 'dashboard/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


# ---------------------------------------------------------------------------
# Welcome + onboarding (before register / login)
# ---------------------------------------------------------------------------

def welcome_view(request):
    if request.user.is_authenticated:
        return redirect('today')
    return render(request, 'dashboard/welcome.html')


def onboarding_view(request):
    if request.user.is_authenticated:
        return redirect('today')
    return render(request, 'dashboard/onboarding.html', {'questions': QUESTIONS})


@require_POST
def onboarding_save(request):
    try:
        raw = json.loads(request.POST.get('answers', ''))
    except ValueError:
        raw = None
    answers = validate_answers(raw)
    if answers is None:
        messages.error(request, "Ответы не сохранились. Попробуй ещё раз.")
        return redirect('onboarding')
    request.session['onboarding'] = answers
    return redirect('onboarding_plan')


def onboarding_plan_view(request):
    if request.user.is_authenticated:
        return redirect('today')
    answers = request.session.get('onboarding')
    if not answers:
        return redirect('onboarding')
    return render(request, 'dashboard/onboarding_plan.html', {'plan': build_plan(answers)})


# ---------------------------------------------------------------------------
# Account / profile
# ---------------------------------------------------------------------------

@login_required
def account_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    total_habits = Habit.objects.filter(user=request.user).count()
    completed_tasks = Task.objects.filter(user=request.user, is_completed=True).count()

    if request.method == 'POST':
        # 1. Parol o'zgartirish
        if 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Пароль успешно изменен!")
                return redirect('account')
            else:
                messages.error(request, "Ошибка при изменении пароля.")

        # 2. Profil ma'lumotlarini yangilash (Bio, links, ism, avatar)
        else:
            user = request.user
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.email = request.POST.get('email', '').strip()
            user.save()

            if 'avatar' in request.FILES:
                profile.avatar = request.FILES['avatar']

            profile.bio = request.POST.get('bio', '').strip()

            # Telegram linkini to'g'rilash (@username -> https://t.me/username)
            tg_input = request.POST.get('telegram_link', '').strip()
            if tg_input:
                if tg_input.startswith('@'):
                    tg_input = f"https://t.me/{tg_input[1:]}"
                elif not tg_input.startswith('http://') and not tg_input.startswith('https://'):
                    tg_input = f"https://{tg_input}"
            profile.telegram_link = tg_input

            # GitHub linkini to'g'rilash
            gh_input = request.POST.get('github_link', '').strip()
            if gh_input and not gh_input.startswith('http://') and not gh_input.startswith('https://'):
                gh_input = f"https://{gh_input}"
            profile.github_link = gh_input

            profile.save()

            messages.success(request, "Профиль успешно обновлен!")
            return redirect('account')

    password_form = PasswordChangeForm(request.user)

    context = {
        'profile': profile,
        'total_habits': total_habits,
        'completed_tasks': completed_tasks,
        'password_form': password_form,
    }
    return render(request, 'dashboard/account.html', context)


def index(request):
    if request.user.is_authenticated:
        return redirect('today')
    return redirect('welcome')


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

@login_required
def habits_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.localdate()
    habits = list(Habit.objects.filter(user=request.user).order_by('id'))

    # Bugungi vaqt: habit bajarilganligi faqat timer vaqtidan aniqlanadi
    sums = (TimeLog.objects
            .filter(user=request.user, date=today)
            .values('habit_id')
            .annotate(total=Sum('duration_minutes')))
    minutes = {r['habit_id']: r['total'] for r in sums}

    today_completed_habits = []
    for h in habits:
        h.today_minutes = minutes.get(h.id, 0)
        goal = h.daily_goal_minutes or 1
        h.progress_pct = min(100, int(h.today_minutes * 100 / goal))
        if h.today_minutes >= goal:
            today_completed_habits.append(h.id)

    # Haqiqiy streak (uzilgan bo'lsa 0 ko'rinadi), bazaga yozmaydi
    apply_live_streaks(request.user, habits)

    return render(request, 'dashboard/habits.html', {
        'profile': profile,
        'habits': habits,
        'today_completed_habits': today_completed_habits,
    })


@login_required
def add_habit(request):
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        goal_raw = request.POST.get('daily_goal_minutes')
        try:
            goal = int(goal_raw)
            if goal <= 0:
                goal = 30
            goal = min(goal, 1440)
        except (TypeError, ValueError):
            goal = 30
        if title:
            Habit.objects.create(user=request.user, title=title[:100], daily_goal_minutes=goal)
    return redirect('habits')


@login_required
@require_POST
def edit_habit(request, habit_id):
    habit = get_object_or_404(Habit, id=habit_id, user=request.user)
    title = request.POST.get('title', '').strip()
    try:
        goal = int(request.POST.get('daily_goal_minutes', ''))
    except ValueError:
        goal = 0
    if title and 1 <= goal <= 1440:
        habit.title = title[:100]
        habit.daily_goal_minutes = goal
        habit.save()
        messages.success(request, "Изменения сохранены")
    else:
        messages.error(request, "Проверьте название и цель")
    return redirect('habits')


@login_required
@require_POST
def delete_habit(request, habit_id):
    habit = get_object_or_404(Habit, id=habit_id, user=request.user)
    title = habit.title
    habit.delete()
    messages.success(request, f"Привычка «{title}» удалена")
    return redirect('habits')


@login_required
def toggle_habit(request, habit_id):
    # Qo'lda belgilash o'chirilgan: habit faqat timer orqali bajariladi
    messages.error(request, "Привычка засчитывается только через таймер")
    return redirect('habits')


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@login_required
def tasks_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    tasks = Task.objects.filter(user=request.user, is_completed=False)

    return render(request, 'dashboard/tasks.html', {
        'profile': profile,
        'tasks': tasks,
    })


@login_required
def add_task(request):
    if request.method == 'POST':
        title = (request.POST.get('title') or '').strip()
        if title:
            Task.objects.create(user=request.user, title=title[:250])
    return redirect('tasks')


@login_required
def complete_task(request, task_id):
    task = get_object_or_404(Task, id=task_id, user=request.user)
    # XP faqat birinchi marta beriladi (havolani qayta ochib XP yig'ib bo'lmaydi)
    if not task.is_completed:
        task.is_completed = True
        task.save()
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        profile.add_xp(15)
    return redirect('tasks')


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------

@login_required
def timer_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    today = timezone.localdate()

    habits = Habit.objects.filter(user=request.user)
    time_logs = TimeLog.objects.filter(user=request.user, date=today)
    total_time = sum(log.duration_minutes for log in time_logs)

    # Har bir habit uchun bugungi bajarilgan vaqtni hisoblaymiz
    habits_data = []
    for habit in habits:
        done = sum(
            log.duration_minutes for log in time_logs if log.habit_id == habit.id
        )
        habits_data.append({
            'id': habit.id,
            'title': habit.title,
            'goal': habit.daily_goal_minutes,
            'done': done,
        })

    return render(request, 'dashboard/timer.html', {
        'profile': profile,
        'time_logs': time_logs,
        'total_time': total_time,
        'habits_data': habits_data,
    })


@login_required
def add_time_log(request):
    if request.method == 'POST':
        habit_id = request.POST.get('habit_id')
        duration = request.POST.get('duration')
        if habit_id and duration:
            habit = Habit.objects.filter(id=habit_id, user=request.user).first()
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                duration = 0
            duration = min(duration, 1440)  # bir sessiya 24 soatdan oshmasin

            if habit and duration > 0:
                TimeLog.objects.create(
                    user=request.user,
                    habit=habit,
                    duration_minutes=duration,
                    date=timezone.localdate(),
                )
                # XP faqat kunlik maqsadga yetganda, kuniga bir marta beriladi
                result = award_if_goal_reached(request.user, habit)
                if result['awarded']:
                    messages.success(
                        request,
                        f"Цель «{habit.title}» выполнена · +{result['xp']} XP"
                    )
    return redirect('timer')


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@login_required
def leaderboard_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    leaderboard = UserProfile.objects.order_by('-total_xp')[:10]

    return render(request, 'dashboard/leaderboard.html', {
        'profile': profile,
        'leaderboard': leaderboard,
    })


# ---------------------------------------------------------------------------
# Challenges
# ---------------------------------------------------------------------------

def _challenge_state(c, user, today):
    """Fills a Challenge object with progress info (calendar cells, counters, status)."""
    goal = c.habit.daily_goal_minutes or 1
    end = c.start_date + timedelta(days=c.days - 1)

    rows = (TimeLog.objects
            .filter(user=user, habit=c.habit, date__range=(c.start_date, end))
            .values('date')
            .annotate(total=Sum('duration_minutes')))
    done_dates = {r['date'] for r in rows if r['total'] >= goal}

    cells, missed = [], 0
    for i in range(c.days):
        d = c.start_date + timedelta(days=i)
        if d in done_dates:
            state = 'done'
        elif d > today:
            state = 'future'
        elif d == today:
            state = 'today'
        else:
            state = 'missed'
            missed += 1
        cells.append({'state': state, 'day': i + 1})

    c.cells = cells
    c.done_days = len(done_dates)
    c.missed_days = missed
    c.pct = int(c.done_days * 100 / c.days)
    c.days_left = max(0, (end - today).days)
    c.day_number = min(max((today - c.start_date).days + 1, 1), c.days)
    c.today_done = today in done_dates
    if c.done_days == c.days:
        c.status = 'success'
    elif today > end:
        c.status = 'finished'
    else:
        c.status = 'active'
    return c


@login_required
def challenges_view(request):
    today = timezone.localdate()
    challenges = list(
        Challenge.objects.filter(user=request.user).select_related('habit')
    )
    for c in challenges:
        _challenge_state(c, request.user, today)

    return render(request, 'dashboard/challenges.html', {
        'challenges': challenges,
    })


@login_required
def new_challenge_view(request):
    return render(request, 'dashboard/challenge_new.html', {
        'habits': Habit.objects.filter(user=request.user),
    })


@login_required
@require_POST
def add_challenge(request):
    title = request.POST.get('title', '').strip()
    goal = request.POST.get('goal', '').strip()
    try:
        days = int(request.POST.get('days', ''))
    except ValueError:
        days = 0
    habit = Habit.objects.filter(
        id=request.POST.get('habit_id') or 0, user=request.user
    ).first()

    if title and goal and 1 <= days <= 365 and habit:
        Challenge.objects.create(
            user=request.user, title=title[:100], goal=goal[:300],
            days=days, habit=habit,
        )
        messages.success(request, "Челлендж создан. Вперёд!")
        return redirect('challenges')

    messages.error(request, "Проверьте название, цель и длительность")
    return redirect('new_challenge')


@login_required
@require_POST
def delete_challenge(request, challenge_id):
    c = get_object_or_404(Challenge, id=challenge_id, user=request.user)
    c.delete()
    messages.success(request, "Челлендж удалён")
    return redirect('challenges')


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

MONTHS_RU = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
             'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']


def fmt_minutes(m):
    m = int(m or 0)
    h, mm = divmod(m, 60)
    if h and mm:
        return f"{h} ч {mm} мин"
    return f"{h} ч" if h else f"{mm} мин"


@login_required
def stats_view(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get('y', today.year))
        month = int(request.GET.get('m', today.month))
        if not 1 <= month <= 12:
            raise ValueError
        date(year, month, 1)  # yil noto'g'ri bo'lsa xato beradi
    except ValueError:
        year, month = today.year, today.month

    n_days = calendar.monthrange(year, month)[1]
    first, last = date(year, month, 1), date(year, month, n_days)

    logs = TimeLog.objects.filter(user=request.user, date__range=(first, last))

    by_day = {r['date']: r['total']
              for r in logs.values('date').annotate(total=Sum('duration_minutes'))}
    values = [by_day.get(date(year, month, d), 0) for d in range(1, n_days + 1)]

    total = sum(values)
    active_days = sum(1 for v in values if v > 0)
    avg = total // active_days if active_days else 0
    best = max(values) if values else 0
    best_day = values.index(best) + 1 if best else None

    habit_rows = []
    for r in logs.values('habit__title').annotate(total=Sum('duration_minutes')).order_by('-total'):
        habit_rows.append({
            'title': r['habit__title'] or 'Другое',
            'text': fmt_minutes(r['total']),
            'pct': int(r['total'] * 100 / total) if total else 0,
        })

    # Heatmap: oxirgi 12 hafta, dushanbadan boshlanadi
    start = today - timedelta(days=83)
    start -= timedelta(days=start.weekday())
    end = start + timedelta(days=7 * 13 - 1)
    hm_by_day = {r['date']: r['total']
                 for r in TimeLog.objects.filter(user=request.user, date__range=(start, end))
                 .values('date').annotate(total=Sum('duration_minutes'))}

    def level(m):
        return 0 if m <= 0 else 1 if m < 30 else 2 if m < 60 else 3 if m < 120 else 4

    heatmap = []
    d = start
    while d <= end:
        m = hm_by_day.get(d, 0)
        heatmap.append({'minutes': m, 'level': level(m), 'future': d > today,
                        'label': d.strftime('%d.%m.%Y')})
        d += timedelta(days=1)

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    has_next = (next_y, next_m) <= (today.year, today.month)

    return render(request, 'dashboard/stats.html', {
        'year': year, 'month_label': MONTHS_RU[month],
        'total_minutes': total, 'total_text': fmt_minutes(total),
        'active_days': active_days, 'avg_text': fmt_minutes(avg),
        'best_text': fmt_minutes(best), 'best_day': best_day,
        'habit_rows': habit_rows, 'heatmap': heatmap,
        'chart_data': {'labels': list(range(1, n_days + 1)), 'values': values},
        'prev_y': prev_y, 'prev_m': prev_m,
        'next_y': next_y, 'next_m': next_m, 'has_next': has_next,
    })


# ---------------------------------------------------------------------------
# Daily routine (plan dnya)
# ---------------------------------------------------------------------------

def _routine_items(user, today=None):
    """Routine items with status: past / current / upcoming, and whether the linked habit is done today."""
    today = today or timezone.localdate()
    now_t = timezone.localtime().time()
    items = list(RoutineItem.objects.filter(user=user).select_related('habit'))

    minutes = {r['habit_id']: r['total']
               for r in (TimeLog.objects.filter(user=user, date=today)
                         .values('habit_id').annotate(total=Sum('duration_minutes')))}

    for i, it in enumerate(items):
        if it.end_time:
            eff_end = it.end_time
        elif i + 1 < len(items):
            eff_end = items[i + 1].start_time
        else:
            eff_end = dtime(23, 59, 59)

        if now_t >= eff_end:
            it.status = 'past'
        elif now_t >= it.start_time:
            it.status = 'current'
        else:
            it.status = 'upcoming'

        it.habit_done = bool(it.habit and minutes.get(it.habit_id, 0) >= (it.habit.daily_goal_minutes or 1))
    return items


def _parse_hhmm(value):
    try:
        return datetime.strptime((value or '').strip(), '%H:%M').time()
    except ValueError:
        return None


def _routine_from_post(request):
    """Returns (data, error). data = dict(title, start, end, habit)."""
    title = request.POST.get('title', '').strip()[:120]
    start = _parse_hhmm(request.POST.get('start'))
    end_raw = request.POST.get('end', '').strip()
    end = _parse_hhmm(end_raw) if end_raw else None
    habit = Habit.objects.filter(id=request.POST.get('habit_id') or 0, user=request.user).first()

    if not title or not start:
        return None, "Укажите название и время начала"
    if end_raw and end is None:
        return None, "Неверное время окончания"
    if end and end <= start:
        return None, "Время окончания должно быть позже начала"
    return {'title': title, 'start_time': start, 'end_time': end, 'habit': habit}, None


@login_required
def routine_view(request):
    today = timezone.localdate()
    items = _routine_items(request.user, today)
    current = next((it for it in items if it.status == 'current'), None)
    return render(request, 'dashboard/routine.html', {
        'items': items,
        'current': current,
        'habits': Habit.objects.filter(user=request.user).order_by('id'),
        'weekday': WEEKDAYS_FULL[today.weekday()],
        'date_text': f"{today.day} {MONTHS_GEN[today.month]}",
    })


@login_required
@require_POST
def add_routine(request):
    data, error = _routine_from_post(request)
    if error:
        messages.error(request, error)
    else:
        RoutineItem.objects.create(user=request.user, **data)
        messages.success(request, "Пункт добавлен в план дня")
    return redirect('routine')


@login_required
@require_POST
def edit_routine(request, item_id):
    item = get_object_or_404(RoutineItem, id=item_id, user=request.user)
    data, error = _routine_from_post(request)
    if error:
        messages.error(request, error)
    else:
        for k, val in data.items():
            setattr(item, k, val)
        item.save()
        messages.success(request, "Изменения сохранены")
    return redirect('routine')


@login_required
@require_POST
def delete_routine(request, item_id):
    item = get_object_or_404(RoutineItem, id=item_id, user=request.user)
    item.delete()
    messages.success(request, "Пункт удалён")
    return redirect('routine')


# ---------------------------------------------------------------------------
# Today (home screen)
# ---------------------------------------------------------------------------

WEEKDAYS_FULL = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
WEEKDAYS_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
MONTHS_GEN = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
              'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


@login_required
def today_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    now = timezone.localtime()
    today = now.date()

    hour = now.hour
    if hour < 5:
        greeting = 'Доброй ночи'
    elif hour < 12:
        greeting = 'Доброе утро'
    elif hour < 18:
        greeting = 'Добрый день'
    else:
        greeting = 'Добрый вечер'
    name = request.user.first_name or request.user.username

    # Bugungi vaqt (faqat timer loglaridan)
    habits = list(Habit.objects.filter(user=request.user).order_by('id'))
    minutes = {r['habit_id']: r['total']
               for r in (TimeLog.objects.filter(user=request.user, date=today)
                         .values('habit_id').annotate(total=Sum('duration_minutes')))}
    total_today = sum(minutes.values())

    goal_sum = capped_sum = done_count = 0
    for h in habits:
        h.today_minutes = minutes.get(h.id, 0)
        goal = h.daily_goal_minutes or 1
        h.pct = min(100, int(h.today_minutes * 100 / goal))
        h.done = h.today_minutes >= goal
        goal_sum += goal
        capped_sum += min(h.today_minutes, goal)
        done_count += 1 if h.done else 0
    overall_pct = int(capped_sum * 100 / goal_sum) if goal_sum else 0

    # Streak va haftalik chiziq: kun "bajarilgan" = kamida bitta habit maqsadga yetgan
    completed_dates = set(HabitLog.objects.filter(user=request.user, completed=True)
                          .values_list('date', flat=True))
    if done_count:
        completed_dates.add(today)
    streak = streak_from_dates(completed_dates, today)
    apply_live_streaks(request.user, habits)

    week = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        week.append({'label': WEEKDAYS_SHORT[d.weekday()], 'day': d.day,
                     'done': d in completed_dates, 'today': d == today})

    # Faol challenge'lar (eng ko'pi bilan 3 ta)
    active = []
    for c in Challenge.objects.filter(user=request.user).select_related('habit'):
        _challenge_state(c, request.user, today)
        if c.status == 'active':
            active.append(c)

    ob = getattr(request.user, 'onboarding', None)
    lesson = lesson_of_the_day(ob.focus if ob else 'discipline', today)

    routine_all = _routine_items(request.user, today)
    routine_next = [it for it in routine_all if it.status != 'past'][:3]

    return render(request, 'dashboard/today.html', {
        'profile': profile,
        'lesson': lesson,
        'routine': routine_next,
        'has_routine': bool(routine_all),
        'greeting': greeting,
        'name': name,
        'weekday': WEEKDAYS_FULL[today.weekday()],
        'date_text': f"{today.day} {MONTHS_GEN[today.month]}",
        'habits': habits,
        'total_habits': len(habits),
        'done_count': done_count,
        'overall_pct': overall_pct,
        'all_done': bool(habits) and done_count == len(habits),
        'streak': streak,
        'time_text': fmt_minutes(total_today),
        'week': week,
        'challenges': active[:3],
    })


# ---------------------------------------------------------------------------
# PWA: service worker (served from the site root so it controls the whole app)
# ---------------------------------------------------------------------------

def service_worker(request):
    js = """
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {});
"""
    resp = HttpResponse(js, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    resp['Cache-Control'] = 'no-cache'
    return resp