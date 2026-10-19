from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import id_token


class GoogleVerificationUnavailable(Exception):
    pass


def verify_google_id_token(token: str, allowed_client_ids: list[str]) -> dict:
    try:
        claims = id_token.verify_oauth2_token(token, Request(), audience=None)
    except GoogleAuthError as exc:
        raise GoogleVerificationUnavailable from exc

    audience = claims.get("aud")
    audiences = {audience} if isinstance(audience, str) else set(audience or [])
    if not audiences.intersection(allowed_client_ids):
        raise ValueError("Google ID token was issued for an unrecognized client.")

    authorized_party = claims.get("azp")
    if authorized_party is not None and authorized_party not in allowed_client_ids:
        raise ValueError("Google ID token was issued for an unrecognized client.")

    return claims
