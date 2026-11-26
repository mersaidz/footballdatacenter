"""
Club-scoped access for every endpoint under /api/clubs/<club_id>/.

- Not a member of the club          → 404 (not 403: don't reveal the club exists).
- Member without the capability     → 403 (they know the club; the data is just not theirs).
"""
from django.utils.translation import gettext_lazy as _
from django.http import Http404
from rest_framework.permissions import BasePermission

from clubs.permissions import Cap, get_membership, has_cap


class ClubScopedMixin:
    """
    Resolves `self.membership` once per request and filters querysets by club.
    Subclasses set `required_cap` (read) and optionally `write_cap`.
    """

    required_cap: Cap = Cap.VIEW_FOOTBALL_DATA
    write_cap: Cap | None = None

    membership = None

    def check_permissions(self, request):
        # Runs after authentication, before any permission class reads `view.membership`.
        if request.user and request.user.is_authenticated:
            self.membership = get_membership(request.user, self.kwargs.get('club_id'))
            if self.membership is None:
                raise Http404
        super().check_permissions(request)

    @property
    def club(self):
        return self.membership.club

    def has_cap(self, cap: Cap) -> bool:
        return has_cap(self.membership, cap)


class HasClubCapability(BasePermission):
    message = _('Your role in this club does not grant access to this data.')

    def has_permission(self, request, view):
        membership = getattr(view, 'membership', None)
        if membership is None:
            return False
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return has_cap(membership, view.required_cap)
        cap = view.write_cap
        return cap is not None and has_cap(membership, cap)
