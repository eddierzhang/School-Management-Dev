"""Sign-in through the school's identity provider (OpenID Connect).

Authorization code flow with PKCE, run entirely by the backend, so the browser
never handles a token:

1. /api/auth/oidc/login makes a state, a nonce and a PKCE verifier, keeps them in a
   short-lived signed cookie, and redirects to the provider.
2. The provider redirects back to /api/auth/oidc/callback with a code. The backend
   checks the state, exchanges the code (sending the verifier and client secret),
   and verifies the ID token's signature against the provider's published keys,
   its issuer, audience, expiry and nonce.
3. The token's email must belong to an active account here. Signing in through the
   provider never creates an account: an administrator, or the roster import, does.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt

from ..config import get_settings

settings = get_settings()
STATE_COOKIE = "hr_oidc"
STATE_TTL = 600
_discovery: dict | None = None


class OIDCError(RuntimeError):
    """Sign-in through the provider failed. The message is safe to log, not to show."""


def http_client() -> httpx.Client:
    return httpx.Client(timeout=10.0)


def discovery() -> dict:
    global _discovery
    if _discovery is None:
        url = settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
        with http_client() as c:
            r = c.get(url)
        if r.status_code != 200:
            raise OIDCError(f"Discovery document at {url} returned {r.status_code}.")
        _discovery = r.json()
    return _discovery


def _sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    mac = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def _unsign(value: str | None) -> dict:
    if not value or "." not in value:
        raise OIDCError("The sign-in state cookie is missing. Start sign-in again.")
    body, mac = value.rsplit(".", 1)
    good = hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, good):
        raise OIDCError("The sign-in state cookie was tampered with.")
    payload = json.loads(base64.urlsafe_b64decode(body))
    if payload.get("exp", 0) < time.time():
        raise OIDCError("Sign-in took too long. Start again.")
    return payload


def begin() -> tuple[str, str]:
    """The provider URL to redirect to, and the signed state cookie to set."""
    d = discovery()
    state, nonce, verifier = (secrets.token_urlsafe(24) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {"response_type": "code", "client_id": settings.oidc_client_id,
              "redirect_uri": settings.oidc_redirect_uri, "scope": settings.oidc_scopes,
              "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    cookie = _sign({"state": state, "nonce": nonce, "verifier": verifier, "exp": time.time() + STATE_TTL})
    return d["authorization_endpoint"] + "?" + urlencode(params), cookie


def finish(code: str | None, state: str | None, cookie: str | None) -> dict:
    """Verified ID token claims for the person who just signed in."""
    saved = _unsign(cookie)
    if not code or not state or not hmac.compare_digest(state, saved["state"]):
        raise OIDCError("The state returned by the provider does not match.")
    d = discovery()
    with http_client() as c:
        r = c.post(d["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id, "client_secret": settings.oidc_client_secret,
            "code_verifier": saved["verifier"]})
        if r.status_code != 200:
            raise OIDCError(f"The token endpoint returned {r.status_code}.")
        id_token = r.json().get("id_token")
        if not id_token:
            raise OIDCError("The provider returned no ID token.")
        jwks = c.get(d["jwks_uri"]).json()

    kid = jwt.get_unverified_header(id_token).get("kid")
    keys = [k for k in jwt.PyJWKSet.from_dict(jwks).keys if kid is None or k.key_id == kid]
    if not keys:
        raise OIDCError("The ID token is signed with a key the provider does not publish.")
    try:
        claims = jwt.decode(id_token, keys[0], algorithms=["RS256", "ES256", "PS256"],
                            audience=settings.oidc_client_id, issuer=d.get("issuer", settings.oidc_issuer),
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]}, leeway=60)
    except jwt.PyJWTError as e:
        raise OIDCError(f"The ID token did not verify: {e}") from e
    if not hmac.compare_digest(str(claims.get("nonce", "")), saved["nonce"]):
        raise OIDCError("The ID token's nonce does not match.")
    if not claims.get("email") or claims.get("email_verified") is False:
        raise OIDCError("The provider did not return a verified email address.")
    return claims
