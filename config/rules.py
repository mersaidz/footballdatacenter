from django.conf import settings
from django.utils import translation
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


def universal_user_authentication_rule(user) -> bool:
    """Reject missing, inactive or soft-deleted users (ported from Aurora)."""
    if user is None:
        return False
    if not user.is_active:
        return False
    if getattr(user, 'deleted_at', None) is not None:
        return False
    return True


class FDCJWTAuthentication(JWTAuthentication):
    """
    Enforce the soft-delete rule on every request, not only at token issue.
    A user offboarded from the club loses access immediately instead of
    waiting for the access token to expire.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not universal_user_authentication_rule(user):
            raise AuthenticationFailed('User is inactive or deleted', code='user_not_found')
        return user

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            activate_language(request, result[0])
        return result


SUPPORTED = {code for code, _ in settings.LANGUAGES}


def activate_language(request, user=None) -> str:
    """?lang= wins (handy for links and demos), then the person's saved language, then the browser's."""
    lang = request.GET.get('lang') if hasattr(request, 'GET') else None
    if lang not in SUPPORTED:
        lang = getattr(user, 'language', None)
    if lang in SUPPORTED:
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
    return translation.get_language()
