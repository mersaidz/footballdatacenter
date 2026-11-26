from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path

INDEX = settings.BASE_DIR / 'frontend' / 'dist' / 'index.html'


def web_app(request):
    """The React app: every non-API URL returns index.html and the app routes on the client."""
    if not INDEX.exists():
        return HttpResponse('The web app is not built yet: cd frontend && npm install && npm run build', status=503,
                            content_type='text/plain; charset=utf-8')
    return HttpResponse(INDEX.read_text(encoding='utf-8'), content_type='text/html; charset=utf-8')


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    re_path(r'^(?!api/|admin/|static/).*$', web_app, name='web_app'),
]
