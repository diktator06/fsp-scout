import base64
import hashlib
import hmac
import secrets
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.keys import SigningKey, get_signing_key
from app.store import AuthorizationCode, CodeStore, Registry, get_code_store, get_registry

REGISTRY_AUDIENCE = "fsp-registry"
USER_SCOPE = "openid profile achievements"
SERVICE_SCOPE = "registry:read"

router = APIRouter(tags=["oidc"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

SettingsDep = Annotated[Settings, Depends(get_settings)]
KeyDep = Annotated[SigningKey, Depends(get_signing_key)]
RegistryDep = Annotated[Registry, Depends(get_registry)]
CodesDep = Annotated[CodeStore, Depends(get_code_store)]


def _oauth_error(error: str, description: str, code: int = 400) -> JSONResponse:
    """Ошибка в формате OAuth 2.0 (RFC 6749, §5.2)."""
    return JSONResponse({"error": error, "error_description": description}, status_code=code)


def _pkce_matches(verifier: str, challenge: str) -> bool:
    """Проверка PKCE S256: BASE64URL(SHA256(verifier)) должно совпасть с challenge."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, challenge)


def _client_credentials(
    settings: Settings, authorization: str | None, client_id: str | None, client_secret: str | None
) -> bool:
    """Аутентификация клиента: client_secret_basic или client_secret_post."""
    if authorization and authorization.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(authorization[6:]).decode()
        except ValueError:
            return False
        client_id, _, client_secret = decoded.partition(":")
    return bool(
        client_id == settings.client_id
        and client_secret is not None
        and hmac.compare_digest(client_secret, settings.client_secret)
    )


def _featured(registry: Registry) -> list[dict[str, Any]]:
    """Демо-персоны для быстрого входа: их не занимает демо-сид бэкенда."""
    personas = [item for item in registry.participants if item.get("persona")]
    return [
        {**item, "hint": item["persona"]["hint"]}
        for item in sorted(personas, key=lambda item: item["persona"]["rank"])
    ]


@router.get("/.well-known/openid-configuration")
def discovery(settings: SettingsDep) -> dict[str, Any]:
    """Метаданные провайдера (OpenID Connect Discovery 1.0)."""
    issuer = settings.issuer
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "userinfo_endpoint": f"{issuer}/userinfo",
        "jwks_uri": f"{issuer}/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "profile", "achievements", SERVICE_SCOPE],
        "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "claims_supported": ["sub", "preferred_username", "region", "sport_rank"],
    }


@router.get("/jwks.json")
def jwks(key: KeyDep) -> dict[str, Any]:
    """Публичные ключи для проверки подписи токенов."""
    return {"keys": [key.jwk()]}


def _validate_authorize(settings: Settings, params: dict[str, str]) -> str | None:
    """Проверяет запрос авторизации; возвращает текст ошибки или None."""
    if params.get("client_id") != settings.client_id:
        return "Неизвестное приложение"
    if params.get("redirect_uri") not in settings.redirect_uris:
        return "Адрес возврата не зарегистрирован для приложения"
    if params.get("response_type") != "code":
        return "Поддерживается только response_type=code"
    if params.get("code_challenge_method") != "S256" or not params.get("code_challenge"):
        return "Требуется PKCE с методом S256"
    return None


@router.get("/authorize", response_class=HTMLResponse)
def authorize_page(request: Request, settings: SettingsDep, registry: RegistryDep) -> Response:
    """Страница входа участника ФСП. Ошибки клиента показываются здесь, без редиректа."""
    params = dict(request.query_params)
    error = _validate_authorize(settings, params)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"params": params, "error": error, "fatal": bool(error), "featured": _featured(registry)},
        status_code=400 if error else 200,
    )


@router.post("/authorize", response_model=None)
def authorize_submit(
    request: Request,
    settings: SettingsDep,
    registry: RegistryDep,
    codes: CodesDep,
    login: Annotated[str, Form()],
    password: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    response_type: Annotated[str, Form()],
    code_challenge: Annotated[str, Form()],
    code_challenge_method: Annotated[str, Form()],
    state: Annotated[str, Form()] = "",
    nonce: Annotated[str, Form()] = "",
    scope: Annotated[str, Form()] = USER_SCOPE,
    action: Annotated[str, Form()] = "login",
) -> Response:
    """Проверяет логин участника и возвращает код авторизации на адрес приложения."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": response_type,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "state": state,
        "nonce": nonce,
        "scope": scope,
    }
    error = _validate_authorize(settings, params)
    if error:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"params": params, "error": error, "fatal": True, "featured": []},
            400,
        )
    if action == "cancel":
        query = urlencode({"error": "access_denied", "state": state})
        return RedirectResponse(f"{redirect_uri}?{query}", status_code=status.HTTP_303_SEE_OTHER)
    participant = registry.by_login(login)
    if participant is None or not hmac.compare_digest(password, settings.demo_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "params": params,
                "error": "Неверный логин или пароль участника",
                "fatal": False,
                "featured": _featured(registry),
                "login": login,
            },
            401,
        )
    code = codes.issue(
        AuthorizationCode(
            participant_id=participant["id"],
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            nonce=nonce or None,
            scope=scope,
            expires_at=time.time() + settings.code_ttl_seconds,
        )
    )
    query = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri}?{query}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/token", response_model=None)
def token(
    settings: SettingsDep,
    key: KeyDep,
    registry: RegistryDep,
    codes: CodesDep,
    grant_type: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Выдаёт токены: по коду авторизации (вход участника) или сервису по client credentials."""
    if not _client_credentials(settings, authorization, client_id, client_secret):
        return _oauth_error("invalid_client", "Клиент не прошёл аутентификацию", 401)
    now = int(time.time())
    expires = now + settings.token_ttl_seconds
    if grant_type == "client_credentials":
        access = key.sign(
            {
                "iss": settings.issuer,
                "sub": settings.client_id,
                "aud": REGISTRY_AUDIENCE,
                "scope": SERVICE_SCOPE,
                "client_id": settings.client_id,
                "iat": now,
                "exp": expires,
                "jti": secrets.token_hex(8),
            }
        )
        return JSONResponse(
            {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": settings.token_ttl_seconds,
                "scope": SERVICE_SCOPE,
            }
        )
    if grant_type != "authorization_code":
        return _oauth_error("unsupported_grant_type", "Тип гранта не поддерживается")
    issued = codes.consume(code or "")
    if (
        issued is None
        or issued.redirect_uri != redirect_uri
        or issued.client_id != settings.client_id
    ):
        return _oauth_error("invalid_grant", "Код недействителен, просрочен или уже использован")
    if not code_verifier or not _pkce_matches(code_verifier, issued.code_challenge):
        return _oauth_error("invalid_grant", "PKCE: code_verifier не соответствует code_challenge")
    participant = registry.by_id(issued.participant_id)
    if participant is None:
        return _oauth_error("invalid_grant", "Участник не найден")
    base = {"iss": settings.issuer, "sub": participant["id"], "iat": now, "exp": expires}
    id_token = key.sign(
        {
            **base,
            "aud": settings.client_id,
            "auth_time": now,
            "nonce": issued.nonce,
            "preferred_username": participant["login"],
            "region": participant["region"],
        }
    )
    access = key.sign(
        {**base, "aud": REGISTRY_AUDIENCE, "scope": issued.scope, "client_id": settings.client_id}
    )
    return JSONResponse(
        {
            "access_token": access,
            "id_token": id_token,
            "token_type": "Bearer",
            "expires_in": settings.token_ttl_seconds,
            "scope": issued.scope,
        },
        headers={"Cache-Control": "no-store"},
    )


def bearer_claims(
    settings: SettingsDep, key: KeyDep, authorization: Annotated[str | None, Header()] = None
) -> dict[str, Any]:
    """Claims access-токена из заголовка Authorization или 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужен Bearer-токен")
    try:
        return key.verify(authorization[7:], REGISTRY_AUDIENCE, settings.issuer)
    except Exception as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Токен недействителен") from error


ClaimsDep = Annotated[dict[str, Any], Depends(bearer_claims)]


@router.get("/userinfo")
def userinfo(claims: ClaimsDep, registry: RegistryDep) -> dict[str, Any]:
    """Сведения об участнике по его access-токену.

    Имя в ответ не входит, как и в id_token: платформе достаточно идентификатора,
    региона и разряда (минимизация персональных данных).
    """
    participant = registry.by_id(str(claims.get("sub")))
    if participant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    return {
        "sub": participant["id"],
        "preferred_username": participant["login"],
        "region": participant["region"],
        "sport_rank": participant["sport_rank"],
    }
