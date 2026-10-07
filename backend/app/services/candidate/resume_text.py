from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.exceptions import DomainValidationError

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
MIN_TEXT_LENGTH = 30


def extract_pdf_text(data: bytes) -> str:
    """Текст резюме из PDF.

    Файл разбирается в памяти и нигде не сохраняется: платформе нужен только
    черновик полей, а не копия документа (минимизация ПДн). Сканы без текстового
    слоя не распознаются — тогда кандидат заполняет профиль вручную.
    """
    if len(data) > MAX_PDF_BYTES:
        raise DomainValidationError("Файл больше 5 МБ — сохраните резюме компактнее")
    if not data.startswith(b"%PDF"):
        raise DomainValidationError("Нужен файл в формате PDF")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DomainValidationError("PDF защищён паролем — снимите защиту и загрузите снова")
        pages = reader.pages[:MAX_PAGES]
        text = "\n".join(page.extract_text() or "" for page in pages)
    except PdfReadError as error:
        raise DomainValidationError("Не удалось прочитать PDF — файл повреждён") from error
    if len(text.strip()) < MIN_TEXT_LENGTH:
        raise DomainValidationError(
            "В PDF нет текстового слоя — похоже, это скан. Заполните профиль вручную"
        )
    return text
