from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
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
]



