import uuid
from datetime import datetime

from app.models.user import UserRole
from app.schemas.common import ORMModel


class UserRead(ORMModel):
    """Публичные сведения о текущем пользователе."""

    id: uuid.UUID
    email: str
    role: UserRole
    is_email_verified: bool
    created_at: datetime
