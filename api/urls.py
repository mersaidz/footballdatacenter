from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

club_router = SimpleRouter()
club_router.register('teams', views.TeamViewSet, basename='team')
club_router.register('players', views.PlayerViewSet, basename='player')
club_router.register('matches', views.MatchViewSet, basename='match')
club_router.register('loads', views.PlayerLoadViewSet, basename='load')
club_router.register('availability', views.AvailabilityViewSet, basename='availability')
club_router.register('identities', views.ExternalIdentityViewSet, basename='identity')
club_router.register('periods', views.ActivityPeriodViewSet, basename='period')
club_router.register('metrics/definitions', views.MetricDefinitionViewSet, basename='metric-definition')
club_router.register('metric-sets', views.MetricSetViewSet, basename='metric-set')

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('clubs/', views.MyClubsView.as_view(), name='my_clubs'),
    path('clubs/<int:club_id>/metrics/catalogue/', views.MetricCatalogueView.as_view(), name='metric_catalogue'),
    path('clubs/<int:club_id>/', include(club_router.urls)),
]
