from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
path('start/', views.welcome_view, name='welcome'),
path('onboarding/', views.onboarding_view, name='onboarding'),
path('onboarding/save/', views.onboarding_save, name='onboarding_save'),
path('onboarding/plan/', views.onboarding_plan_view, name='onboarding_plan'),
    path('habits/', views.habits_view, name='habits'),
    path('tasks/', views.tasks_view, name='tasks'),
    path('timer/', views.timer_view, name='timer'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    
    # Actions
    path('add-habit/', views.add_habit, name='add_habit'),
    path('toggle-habit/<int:habit_id>/', views.toggle_habit, name='toggle_habit'),
    path('add-task/', views.add_task, name='add_task'),
    path('complete-task/<int:task_id>/', views.complete_task, name='complete_task'),
    path('add-time-log/', views.add_time_log, name='add_time_log'),

    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('account/', views.account_view, name='account'),
    path('habits/<int:habit_id>/delete/', views.delete_habit, name='delete_habit'),
    path('habits/<int:habit_id>/edit/', views.edit_habit, name='edit_habit'),
    path('challenges/', views.challenges_view, name='challenges'),
    path('challenges/add/', views.add_challenge, name='add_challenge'),
    path('challenges/<int:challenge_id>/delete/', views.delete_challenge, name='delete_challenge'), 
    path('challenges/new/', views.new_challenge_view, name='new_challenge'),    
    path('stats/', views.stats_view, name='stats'),
    path('sw.js', views.service_worker, name='sw'),
    path('today/', views.today_view, name='today'),

    path('routine/', views.routine_view, name='routine'),
    path('routine/add/', views.add_routine, name='add_routine'),
    path('routine/<int:item_id>/edit/', views.edit_routine, name='edit_routine'),
    path('routine/<int:item_id>/delete/', views.delete_routine, name='delete_routine'),
]



