from django.urls import path
from . import views

app_name = "workouts"

urlpatterns = [
    path("", views.WorkoutPlanListView.as_view(), name="plan_list"),
    path("<int:pk>/", views.WorkoutPlanDetailView.as_view(), name="plan_detail"),
    path("day/<int:pk>/", views.WorkoutDayDetailView.as_view(), name="day_detail"),
    path("day/<int:pk>/start/", views.StartWorkoutView.as_view(), name="start_workout"),
    path("session/<int:pk>/", views.WorkoutSessionView.as_view(), name="session"),
    path("session/<int:pk>/finish/", views.FinishWorkoutView.as_view(), name="finish_workout"),
    path("session/save-set/", views.SaveSetLogView.as_view(), name="save_set"),
    path("log/<int:pk>/", views.WorkoutLogDetailView.as_view(), name="log_detail"),
    # path("exercise/<int:pk>/", views.ExerciseDetailView.as_view(), name="exercise_detail"),
    path("history/", views.WorkoutHistoryView.as_view(), name="history"),
]