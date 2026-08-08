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

# Media (QR de pago de empleados, etc.) se sirve siempre, tambien en
# produccion -- no hay S3/CDN externo, MEDIA_ROOT apunta al volumen
# persistente de Railway. Static solo se sirve aqui en DEBUG (en
# produccion no hay collectstatic configurado; el admin de Django no se
# usa como interfaz principal).
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
