from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import (
    AuthServiceDep,
    ClientContextDep,
    CurrentUser,
    FspLoginServiceDep,
    SettingsDep,
)
from app.api.errors import error_responses
from app.api.rate_limit import RateLimiter
from app.core.config import Settings
from app.core.exceptions import InvalidTokenError
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.schemas.common import MessageResponse
from app.schemas.fsp import FspAuthorizationRead, FspCallback
from app.schemas.user import UserRead
from app.services.auth.auth_service import AuthenticatedSession

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH = "/api/v1/auth"

register_limiter = RateLimiter(limit=10, window_seconds=3600)
login_limiter = RateLimiter(limit=20, window_seconds=300)
resend_limiter = RateLimiter(limit=3, window_seconds=600)
verify_limiter = RateLimiter(limit=30, window_seconds=300)


def _set_refresh_cookie(response: Response, auth: AuthenticatedSession, settings: Settings) -> None:
    """Кладёт refresh-токен в httpOnly-cookie.

    JavaScript токен не видит, поэтому XSS не может его похитить. `SameSite=Strict`
    и путь `/api/v1/auth` означают, что cookie уходит только на эндпоинты
    аутентификации и только с нашего же сайта.
    """
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=auth.tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        expires=auth.tokens.refresh_expires_at,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    """Удаляет refresh-cookie при выходе или недействительной сессии."""
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="strict",
    )


def _token_response(auth: AuthenticatedSession) -> TokenResponse:
    """Ответ с access-токеном и данными пользователя."""
    return TokenResponse(
        access_token=auth.tokens.access_token,
        expires_in=auth.tokens.access_expires_in,
        user=UserRead.model_validate(auth.user),
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
    responses=error_responses(409, 422, 429),
    dependencies=[Depends(register_limiter)],
    summary="Регистрация кандидата или работодателя",
)
async def register(
    payload: RegisterRequest, service: AuthServiceDep, client: ClientContextDep
) -> RegisterResponse:
    """Создаёт аккаунт и отправляет письмо со ссылкой подтверждения.

    Войти можно только после подтверждения email. Согласие на обработку
    персональных данных обязательно и сохраняется в журнале согласий.
    """
    result = await service.register(payload, client)
    return RegisterResponse(
        user_id=result.user.id,
        email=result.user.email,
        verification_email_sent=result.verification_email_sent,
    )


@router.post(
    "/verify-email",
    response_model=TokenResponse,
    responses=error_responses(400, 403, 422, 429),
    dependencies=[Depends(verify_limiter)],
    summary="Подтверждение email по ссылке из письма",
)
async def verify_email(
    payload: VerifyEmailRequest,
    response: Response,
    service: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Подтверждает адрес и сразу открывает сессию: повторно вводить пароль не нужно."""
    auth = await service.verify_email(payload.token, client)
    _set_refresh_cookie(response, auth, settings)
    return _token_response(auth)


@router.post(
    "/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MessageResponse,
    responses=error_responses(422, 429),
    dependencies=[Depends(resend_limiter)],
    summary="Повторная отправка письма подтверждения",
)
async def resend_verification(
    payload: ResendVerificationRequest, service: AuthServiceDep
) -> MessageResponse:
    """Отправляет новое письмо, если аккаунт существует и ещё не подтверждён.

    Ответ одинаковый в любом случае, чтобы по нему нельзя было узнать,
    зарегистрирован ли адрес.
    """
    await service.resend_verification(payload.email)
    return MessageResponse(
        message="Если аккаунт с таким email ждёт подтверждения, мы отправили новое письмо"
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=error_responses(401, 403, 422, 429),
    dependencies=[Depends(login_limiter)],
    summary="Вход по email и паролю",
)
async def login(
    payload: LoginRequest,
    response: Response,
    service: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Возвращает access-токен в теле и ставит refresh-токен в httpOnly-cookie."""
    auth = await service.login(payload, client)
    _set_refresh_cookie(response, auth, settings)
    return _token_response(auth)


@router.post(
    "/fsp/start",
    response_model=FspAuthorizationRead,
    responses=error_responses(404, 429, 503),
    dependencies=[Depends(login_limiter)],
    summary="Вход через ФСП ID: начало",
)
async def fsp_login_start(service: FspLoginServiceDep) -> FspAuthorizationRead:
    """Адрес страницы входа ФСП ID. Работает для аккаунтов, к которым ФСП ID уже привязан."""
    return await service.start()


@router.post(
    "/fsp/callback",
    response_model=TokenResponse,
    responses=error_responses(400, 403, 409, 422, 429, 503),
    dependencies=[Depends(login_limiter)],
    summary="Вход через ФСП ID: завершение",
)
async def fsp_login_callback(
    payload: FspCallback,
    response: Response,
    service: FspLoginServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Проверяет ответ ФСП ID и открывает сессию так же, как вход по паролю."""
    auth = await service.complete(payload, client)
    _set_refresh_cookie(response, auth, settings)
    return _token_response(auth)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=error_responses(401),
    summary="Обновление сессии по refresh-cookie",
)
async def refresh(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    client: ClientContextDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Выдаёт новую пару токенов. Старый refresh-токен после этого недействителен.

    Фронтенд вызывает метод при загрузке страницы (восстановление сессии) и при
    истечении access-токена.
    """
    raw_token = request.cookies.get(settings.refresh_cookie_name)
    if not raw_token:
        raise InvalidTokenError("Сессия не найдена, войдите в аккаунт")
    auth = await service.refresh(raw_token, client)
    _set_refresh_cookie(response, auth, settings)
    return _token_response(auth)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Выход из аккаунта",
)
async def logout(request: Request, service: AuthServiceDep, settings: SettingsDep) -> Response:
    """Отзывает текущую refresh-сессию и удаляет cookie."""
    await service.logout(request.cookies.get(settings.refresh_cookie_name))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@router.get(
    "/me",
    response_model=UserRead,
    responses=error_responses(401, 403),
    summary="Текущий пользователь",
)
async def read_me(user: CurrentUser) -> UserRead:
    """Сведения о владельце access-токена."""
    return UserRead.model_validate(user)
