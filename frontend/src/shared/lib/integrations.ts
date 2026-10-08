import type { DeliveryStatus } from '@/api/types';

export const DELIVERY_STATUS_COPY: Record<DeliveryStatus, { label: string; color: string }> = {
  pending: { label: 'В очереди', color: 'lilac' },
  delivered: { label: 'Доставлено', color: 'teal' },
  failed: { label: 'Не доставлено', color: 'signal' },
};

export const PING_LABEL = 'Проверка связи';

export function responseSummary(body: string, error: string): string {
  // Песочница и многие ATS отвечают JSON с полем message — показываем его, а не
  // сырой ответ; остальное выводим как есть.
  if (!body) return error;
  try {
    const parsed: unknown = JSON.parse(body);
    if (parsed && typeof parsed === 'object' && 'message' in parsed) {
      const { message } = parsed as { message: unknown };
      if (typeof message === 'string' && message) return message;
    }
  } catch {
    return body;
  }
  return body;
}
