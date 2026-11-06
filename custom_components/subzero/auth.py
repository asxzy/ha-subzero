"""Azure AD B2C sign-in for the Sub-Zero Group cloud.

The app registration only permits the custom-scheme callback
``com.szg.szgdigitalproductexperience://oauth/redirect/``, which Home Assistant
cannot serve. The flow is therefore completed entirely in-process:

1. ``GET`` the authorize endpoint to obtain the B2C page settings (transaction
   id, CSRF token, tenant path).
2. ``POST`` credentials to ``SelfAsserted``; B2C authenticates the user.
3. ``GET`` the confirmation endpoint with redirects disabled and read ``code``
   out of the ``Location`` header.
4. Exchange the code at the token endpoint using the PKCE verifier.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import aiohttp

from .const import (
    B2C_CLIENT_ID,
    B2C_ORIGIN,
    B2C_POLICY,
    B2C_REDIRECT_URI,
    B2C_SCOPE,
    B2C_TENANT,
)

_LOGGER = logging.getLogger(__name__)

LOGIN_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_SETTINGS_RE = re.compile(r"var SETTINGS = (\{.*?\});\s*\n", re.S)


class AuthError(Exception):
    """Base sign-in failure."""


class InvalidCredentials(AuthError):
    """The account rejected the supplied email or password."""


class AuthFlowChanged(AuthError):
    """B2C returned a page this client does not understand."""


class MfaRequired(AuthError):
    """The account requires an interactive verification step."""


@dataclass(slots=True)
class Tokens:
    """Persisted token bundle for a config entry."""

    access_token: str
    id_token: str
    refresh_token: str
    expires_at: datetime
    user_id: str

    @property
    def expired(self) -> bool:
        """Return True when the access token should be refreshed."""
        return datetime.now(UTC) >= self.expires_at - timedelta(minutes=5)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "access_token": self.access_token,
            "id_token": self.id_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Tokens:
        """Rebuild tokens stored in a config entry."""
        return cls(
            access_token=data["access_token"],
            id_token=data["id_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            user_id=data["user_id"],
        )


def _jwt_claims(token: str) -> dict[str, Any]:
    """Decode the payload of a JWT without verifying its signature."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError) as err:
        raise AuthError("Sub-Zero returned a malformed token.") from err
    if not isinstance(claims, dict):
        raise AuthError("Sub-Zero returned a malformed token.")
    return claims


def _account_id(id_token: str) -> str:
    """Return the account identifier used by the appliance API."""
    claims = _jwt_claims(id_token)
    account = claims.get("mergedId") or claims.get("sub")
    if not isinstance(account, str) or not account:
        raise AuthError("Sub-Zero did not include an account id in its token.")
    return account


def _tokens_from_response(payload: dict[str, Any]) -> Tokens:
    """Build a token bundle from a B2C token response."""
    try:
        access = payload["access_token"]
        identity = payload["id_token"]
        refresh = payload["refresh_token"]
        expires_in = int(payload.get("expires_in", 3600))
    except (KeyError, TypeError, ValueError) as err:
        raise AuthError("Sub-Zero returned an incomplete token response.") from err
    if not all(isinstance(value, str) and value for value in (access, identity, refresh)):
        raise AuthError("Sub-Zero returned an incomplete token response.")
    claims = _jwt_claims(access)
    try:
        expiry = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    except (KeyError, TypeError, ValueError) as err:
        raise AuthError("Sub-Zero returned a token without an expiry.") from err
    return Tokens(
        access_token=access,
        id_token=identity,
        refresh_token=refresh,
        expires_at=expiry,
        user_id=_account_id(identity),
    )


def _settings(page: str) -> dict[str, Any]:
    """Extract the B2C page settings blob."""
    match = _SETTINGS_RE.search(page)
    if not match:
        raise AuthFlowChanged("Sub-Zero's sign-in page format changed.")
    try:
        settings = json.loads(match.group(1))
    except ValueError as err:
        raise AuthFlowChanged("Sub-Zero's sign-in page format changed.") from err
    if not isinstance(settings, dict) or "hosts" not in settings or "csrf" not in settings:
        raise AuthFlowChanged("Sub-Zero's sign-in page format changed.")
    return settings


async def async_create_login_session() -> tuple[aiohttp.ClientSession, "SubZeroAuth"]:
    """Create an isolated session for sign-in.

    B2C rejects the quoted cookie encoding that aiohttp applies by default, so the
    jar must be created with ``quote_cookie=False``. Sign-in also needs its own
    cookie space, separate from the appliance API session.
    """
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(quote_cookie=False))
    return session, SubZeroAuth(session)


class SubZeroAuth:
    """Drive the Sub-Zero B2C sign-in flow."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the sign-in client."""
        self._session = session

    async def login(self, username: str, password: str) -> Tokens:
        """Authenticate with an email and password."""
        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        tenant = f"{B2C_TENANT}/{B2C_POLICY}"
        authorize = (
            f"{B2C_ORIGIN}/{tenant}/oauth2/v2.0/authorize?"
            + urlencode(
                {
                    "client_id": B2C_CLIENT_ID,
                    "scope": B2C_SCOPE,
                    "redirect_uri": B2C_REDIRECT_URI,
                    "response_type": "code",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "nonce": secrets.token_urlsafe(24),
                }
            )
        )

        async with self._session.get(
            authorize, headers=LOGIN_HEADERS, allow_redirects=False
        ) as response:
            page = await response.text()
            if response.status != 200:
                raise AuthError(
                    f"Sub-Zero's sign-in page returned HTTP {response.status}."
                )
            settings = _settings(page)
            url = str(response.url)

        if settings.get("api") not in ("CombinedSigninAndSignup", "SelfAsserted"):
            # Social sign-in, phone factor, or a captcha gate.
            if settings.get("api") == "Phonefactor":
                raise MfaRequired(
                    "This Sub-Zero account requires a verification code."
                )
            raise AuthFlowChanged(
                "Sub-Zero's sign-in requires a step this integration cannot perform."
            )

        await self._submit_credentials(settings, url, username, password)
        code = await self._confirmation_code(settings, url)
        return await self._exchange(code, verifier)

    async def _submit_credentials(
        self,
        settings: dict[str, Any],
        referer: str,
        username: str,
        password: str,
    ) -> None:
        """Post the account credentials to the B2C self-asserted endpoint."""
        endpoint = (
            f"{B2C_ORIGIN}{settings['hosts']['tenant']}/SelfAsserted?"
            + urlencode({"tx": settings["transId"], "p": settings["hosts"]["policy"]})
        )
        headers = {
            **LOGIN_HEADERS,
            "X-CSRF-TOKEN": settings["csrf"],
            "X-Requested-With": "XMLHttpRequest",
            "Origin": B2C_ORIGIN,
            "Referer": referer,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        data = {
            "request_type": "RESPONSE",
            "signInName": username,
            "password": password,
        }
        async with self._session.post(
            endpoint, headers=headers, data=data, allow_redirects=False
        ) as response:
            if response.status != 200:
                raise AuthError(
                    f"Sub-Zero's sign-in form returned HTTP {response.status}."
                )
            try:
                result = await response.json(content_type=None)
            except ValueError as err:
                raise AuthFlowChanged(
                    "Sub-Zero's sign-in form returned an unexpected response."
                ) from err

        status = str(result.get("status", ""))
        if status == "200":
            return
        code = str(result.get("errorCode", ""))
        # 90054/90056 are a bad password; 90053 flags a blocked or unknown account.
        if code in ("AADB2C90054", "AADB2C90056", "AADB2C90053"):
            raise InvalidCredentials("Sub-Zero rejected the email or password.")
        raise AuthError(
            f"Sub-Zero's sign-in failed ({code or 'unknown error'})."
        )

    async def _confirmation_code(
        self, settings: dict[str, Any], referer: str
    ) -> str:
        """Complete the policy and read the authorization code from the redirect."""
        endpoint = (
            f"{B2C_ORIGIN}{settings['hosts']['tenant']}/api/CombinedSigninAndSignup/confirmed?"
            + urlencode(
                {
                    "rememberMe": "false",
                    "csrf_token": settings["csrf"],
                    "tx": settings["transId"],
                    "p": settings["hosts"]["policy"],
                    "diags": '{"pageViewId":"","pageId":"","trace":[]}',
                }
            )
        )
        headers = {**LOGIN_HEADERS, "Referer": referer}
        async with self._session.get(
            endpoint, headers=headers, allow_redirects=False
        ) as response:
            location = response.headers.get("Location", "")
            if response.status not in (301, 302, 303, 307):
                # B2C rendered another form: MFA, captcha, or a forced reset.
                body = await response.text()
                if "Phonefactor" in body or "verification" in body.lower():
                    raise MfaRequired(
                        "This Sub-Zero account requires a verification code."
                    )
                raise AuthFlowChanged(
                    "Sub-Zero's sign-in needs another step this integration "
                    "cannot perform."
                )

        params = parse_qs(urlsplit(location).query)
        if "error" in params:
            error = params["error"][0]
            description = params.get("error_description", [error])[0]
            raise AuthError(f"Sub-Zero's sign-in failed: {description}")
        code = params.get("code", [""])[0]
        if not code:
            raise AuthFlowChanged("Sub-Zero did not return an authorization code.")
        return code

    async def _exchange(self, code: str, verifier: str) -> Tokens:
        """Swap an authorization code for tokens."""
        tenant = f"{B2C_TENANT}/{B2C_POLICY}"
        endpoint = f"{B2C_ORIGIN}/{tenant}/oauth2/v2.0/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": B2C_CLIENT_ID,
            "code": code,
            "redirect_uri": B2C_REDIRECT_URI,
            "code_verifier": verifier,
            "scope": B2C_SCOPE,
        }
        async with self._session.post(
            endpoint,
            headers={**LOGIN_HEADERS, "Accept": "application/json"},
            data=data,
            allow_redirects=False,
        ) as response:
            try:
                payload = await response.json(content_type=None)
            except ValueError as err:
                raise AuthFlowChanged(
                    "Sub-Zero's token endpoint returned an unexpected response."
                ) from err
        if "error" in payload:
            raise AuthError(
                "Sub-Zero could not issue tokens: "
                + str(payload.get("error_description", payload["error"]))
            )
        return _tokens_from_response(payload)

    async def refresh(self, refresh_token: str) -> Tokens:
        """Renew tokens using a stored refresh token."""
        tenant = f"{B2C_TENANT}/{B2C_POLICY}"
        endpoint = f"{B2C_ORIGIN}/{tenant}/oauth2/v2.0/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": B2C_CLIENT_ID,
            "refresh_token": refresh_token,
            "redirect_uri": B2C_REDIRECT_URI,
            "scope": B2C_SCOPE,
        }
        async with self._session.post(
            endpoint,
            headers={**LOGIN_HEADERS, "Accept": "application/json"},
            data=data,
            allow_redirects=False,
        ) as response:
            try:
                payload = await response.json(content_type=None)
            except ValueError as err:
                raise AuthError("Sub-Zero's token renewal failed.") from err
        if "error" in payload:
            raise AuthError(
                "Sub-Zero's token renewal failed: "
                + str(payload.get("error_description", payload["error"]))
            )
        if "refresh_token" not in payload:
            payload["refresh_token"] = refresh_token
        return _tokens_from_response(payload)
