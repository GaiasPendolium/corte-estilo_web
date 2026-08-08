"""
URL configuration for peluqueria_backend project.
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.static import serve as static_serve


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
# persistente de Railway. OJO: static() de Django trae su propio chequeo
# interno de DEBUG y siempre devuelve [] si DEBUG=False (esta pensada
# solo para desarrollo) -- por eso aqui se registra la vista `serve`
# directamente en vez de usar static(), para que funcione tambien en
# produccion. Static solo se sirve aqui en DEBUG (en produccion no hay
# collectstatic configurado; el admin de Django no se usa como interfaz
# principal).
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
