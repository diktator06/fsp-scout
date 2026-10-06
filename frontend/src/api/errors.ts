interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: unknown };
}

interface FieldIssue {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function toApiError(body: unknown, response: Response): ApiError {
  // Бэкенд всегда отвечает ошибкой в формате {"error": {code, message, details}}.
  // Если пришло что-то другое (упал прокси, отдал HTML), показываем нейтральный текст.
  const envelope = (body ?? {}) as ErrorEnvelope;
  return new ApiError(
    response.status,
    envelope.error?.code ?? 'http_error',
    envelope.error?.message ?? 'Сервис временно недоступен, попробуйте ещё раз',
    envelope.error?.details ?? {},
  );
}

export async function unwrap<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  // Превращает ответ openapi-fetch в обычный промис: данные или исключение ApiError.
  // С этим удобно работать в TanStack Query и обработчиках форм.
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await request;
  } catch {
    throw new ApiError(0, 'network_error', 'Нет связи с сервером. Проверьте подключение');
  }
  if (result.error !== undefined || !result.response.ok) {
    throw toApiError(result.error, result.response);
  }
  return result.data as T;
}

export function fieldErrors(error: unknown): Record<string, string> {
  // Ошибки валидации бэкенда приходят списком {field, message}: раскладываем их по полям формы.
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return {};
  return Object.fromEntries(
    (error.details as FieldIssue[])
      .filter((issue) => typeof issue?.field === 'string' && typeof issue?.message === 'string')
      .map((issue) => [issue.field, issue.message]),
  );
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Что-то пошло не так. Попробуйте ещё раз';
}
