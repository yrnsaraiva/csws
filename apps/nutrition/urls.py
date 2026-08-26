from django.urls import path
from . import views

app_name = "nutrition"

urlpatterns = [
    path("", views.NutritionPlanListView.as_view(), name="plan_list"),
    path("<int:pk>/", views.NutritionPlanDetailView.as_view(), name="plan_detail"),
    path("meal/<int:pk>/", views.MealDetailView.as_view(), name="meal_detail"),
    path("meal/<int:pk>/toggle/", views.ToggleMealLogView.as_view(), name="toggle_meal"),
    path("log/", views.NutritionLogView.as_view(), name="log"),
]

