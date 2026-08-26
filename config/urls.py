from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.public_site.urls")),
    path("app/", include("apps.accounts.urls")),
    path("app/workouts/", include("apps.workouts.urls")),
    path("app/nutrition/", include("apps.nutrition.urls")),
    path("app/packages/", include("apps.packages.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)