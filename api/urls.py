from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from wellness import api as wellness

from . import views, views_app

club_router = SimpleRouter()
club_router.register('teams', views.TeamViewSet, basename='team')
club_router.register('players', views.PlayerViewSet, basename='player')
club_router.register('matches', views.MatchViewSet, basename='match')
club_router.register('loads', views.PlayerLoadViewSet, basename='load')
club_router.register('availability', views.AvailabilityViewSet, basename='availability')
club_router.register('identities', views.ExternalIdentityViewSet, basename='identity')
club_router.register('periods', views.ActivityPeriodViewSet, basename='period')
club_router.register('metrics/definitions', views.MetricDefinitionViewSet, basename='metric-definition')
club_router.register('metrics/requests', views.MetricRequestViewSet, basename='metric-request')
club_router.register('sessions', views_app.SessionViewSet, basename='session')
club_router.register('metric-sets', views.MetricSetViewSet, basename='metric-set')

urlpatterns = [
    path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', views.MeView.as_view(), name='me'),
    path('clubs/', views.MyClubsView.as_view(), name='my_clubs'),
    path('clubs/<int:club_id>/metrics/catalogue/', views.MetricCatalogueView.as_view(), name='metric_catalogue'),
    path('clubs/<int:club_id>/squad-status/', views_app.SquadStatusView.as_view(), name='squad_status'),
    path('clubs/<int:club_id>/reports/daily.<str:fmt>', views_app.DailyReportView.as_view(), name='daily_report'),
    path('clubs/<int:club_id>/microcycle/', views_app.MicrocycleView.as_view(), name='microcycle'),
    path('clubs/<int:club_id>/players/<int:pk>/load-history/', views_app.PlayerHistoryView.as_view(), name='load_history'),
    path('clubs/<int:club_id>/wellness/', wellness.SquadWellnessView.as_view(), name='squad_wellness'),
    path('clubs/<int:club_id>/rpe/', wellness.StaffRpeView.as_view(), name='staff_rpe'),
    path('clubs/<int:club_id>/players/<int:pk>/wellness/', wellness.PlayerWellnessView.as_view(), name='player_wellness'),
    path('clubs/<int:club_id>/player-links/', wellness.PlayerLinksView.as_view(), name='player_links'),
    path('clubs/<int:club_id>/player-links/<int:pk>/revoke/', wellness.RevokePlayerLinkView.as_view(), name='revoke_player_link'),
    path('clubs/<int:club_id>/', include(club_router.urls)),
    path('p/<str:token>/', wellness.PlayerHomeView.as_view(), name='player_home'),
    path('p/<str:token>/manifest/', wellness.PlayerManifestView.as_view(), name='player_manifest'),
    path('p/<str:token>/checkin/', wellness.PlayerCheckinView.as_view(), name='player_checkin'),
    path('p/<str:token>/rpe/', wellness.PlayerRpeView.as_view(), name='player_rpe'),
]
