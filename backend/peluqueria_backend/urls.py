"""
URL configuration for peluqueria_backend project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse


def home(request):
    return JsonResponse(
        {
            "message": "Backend de Peluqueria API activo",
            "admin": "/admin/",
            "api": "/api/",
            "health": "/health/",
        }
    )


def health(request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path('', home, name='home'),
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
