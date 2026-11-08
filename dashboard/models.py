from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    total_xp = models.IntegerField(default=0)
    current_streak = models.IntegerField(default=0)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.CharField(max_length=255, blank=True, default="Focusing on daily growth 🚀")
    github_link = models.URLField(blank=True, null=True)
    telegram_link = models.URLField(blank=True, null=True)

    def add_xp(self, amount):
        self.total_xp += amount
        self.save()

    @property
    def level(self):
        return (self.total_xp // 100) + 1

    @property
    def xp_progress(self):
        return self.total_xp % 100

    def __str__(self):
        return f"{self.user.username} - Lvl {self.level}"


class Habit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    streak = models.IntegerField(default=0)
    last_completed = models.DateField(null=True, blank=True)
    daily_goal_minutes = models.IntegerField(default=30)

    def __str__(self):
        return self.title


class HabitLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name='logs')
    date = models.DateField(default=timezone.now)
    completed = models.BooleanField(default=False)


# Task Tracker
class Task(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=250)
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


# Time Balance Log
class TimeLog(models.Model):
    CATEGORY_CHOICES = [
        ('coding', 'Coding / Backend'),
        ('english', 'English'),
        ('trading', 'Trading'),
        ('fitness', 'Fitness / Workout'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    habit = models.ForeignKey(Habit, on_delete=models.SET_NULL, null=True, blank=True, related_name='time_logs')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, blank=True, null=True)
    duration_minutes = models.IntegerField()
    date = models.DateField(default=timezone.now)


class Challenge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    goal = models.CharField(max_length=300)          # asosiy maqsad
    days = models.PositiveIntegerField(default=30)
    habit = models.ForeignKey(Habit, on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# Yangi foydalanuvchi yaratilganda UserProfile avtomatik yaratiladi
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)