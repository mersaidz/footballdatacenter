from __future__ import annotations

from typing import Any, Optional

from core.models import AuditLog
from core.sanitize import DEFAULT_SENSITIVE_KEYS, _is_forbidden


def log_event(
    *,
    action: str,
    user=None,
    club=None,
    request=None,
    provider: str = '',
    extra_info: Optional[dict] = None,
) -> AuditLog:
    """Single entry point for audit writes. Strips sensitive keys before saving."""
    ip_address = None
    user_agent = ''
    if request is not None:
        ip_address = _client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:512]
        if user is None and getattr(request, 'user', None) is not None and request.user.is_authenticated:
            user = request.user

    return AuditLog.objects.create(
        user=user,
        club=club,
        action=action,
        provider=provider,
        ip_address=ip_address,
        user_agent=user_agent,
        extra_info=_strip_forbidden_keys(extra_info) if extra_info else {},
    )


def _client_ip(request) -> Optional[str]:
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _strip_forbidden_keys(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: _strip_forbidden_keys(v)
            for k, v in data.items()
            if not _is_forbidden(k, DEFAULT_SENSITIVE_KEYS)
        }
    if isinstance(data, list):
        return [_strip_forbidden_keys(item) for item in data]
    return data
