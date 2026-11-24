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
