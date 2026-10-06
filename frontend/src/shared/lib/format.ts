const rubFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });
const decimalFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

export const RUB_SIGN = '₽';
export const NBSP = '\u00a0';
export const RANGE_DASH = '–';

export function formatRub(amount: number): string {
  // Группы разрядов в ru-RU разделяются неразрывным пробелом:
  // «220 000» не разорвётся переносом строки посередине суммы.
  return rubFormatter.format(Math.round(amount));
}

function compactAmount(amount: number): { value: string; unit: 'тыс.' | 'млн' } {
  // Миллионы показываем с одной десятичной («1,2 млн»), тысячи — целыми («220 тыс.»).
  if (amount >= 1_000_000) {
    return { value: decimalFormatter.format(amount / 1_000_000), unit: 'млн' };
  }
  return { value: rubFormatter.format(Math.round(amount / 1000)), unit: 'тыс.' };
}

export interface SalaryFormatOptions {
  compact?: boolean;
  withCurrency?: boolean;
}

export function formatSalaryRange(
  from: number,
  to: number,
  { compact = false, withCurrency = true }: SalaryFormatOptions = {},
): string {
  // Вилка «от–до» — обязательное поле приглашения и вакансии. Одинаковые границы
  // схлопываем в одну сумму, а в компактном виде единицу пишем один раз:
  // «220–300 тыс. ₽», а не «220 тыс. – 300 тыс.».
  const currency = withCurrency ? `${NBSP}${RUB_SIGN}` : '';
  const low = Math.min(from, to);
  const high = Math.max(from, to);

  if (!compact) {
    if (low === high) return `${formatRub(low)}${currency}`;
    return `${formatRub(low)} ${RANGE_DASH} ${formatRub(high)}${currency}`;
  }

  const left = compactAmount(low);
  const right = compactAmount(high);
  if (low === high) return `${right.value}${NBSP}${right.unit}${currency}`;
  if (left.unit === right.unit) {
    return `${left.value}${RANGE_DASH}${right.value}${NBSP}${right.unit}${currency}`;
  }
  return `${left.value}${NBSP}${left.unit} ${RANGE_DASH} ${right.value}${NBSP}${right.unit}${currency}`;
}

export function pluralizeRu(count: number, forms: readonly [string, string, string]): string {
  // Русские формы множественного числа: 1 кандидат, 2 кандидата, 5 кандидатов.
  // Исключение — 11–14: «11 кандидатов», хотя число оканчивается на 1–4.
  const absolute = Math.abs(count) % 100;
  const lastDigit = absolute % 10;
  if (absolute > 10 && absolute < 20) return forms[2];
  if (lastDigit === 1) return forms[0];
  if (lastDigit >= 2 && lastDigit <= 4) return forms[1];
  return forms[2];
}

export function formatDateTime(value: string | Date): string {
  // Короткий формат для таймлайнов: «6 окт., 14:20».
  const date = typeof value === 'string' ? new Date(value) : value;
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function formatDate(value: string | Date, now: Date = new Date()): string {
  // Дата без времени: «4 янв.», а если год не текущий — «4 янв. 2027 г.».
  // Для сроков вроде «откроется через 90 дней» время суток только мешает.
  const date = typeof value === 'string' ? new Date(value) : value;
  const sameYear = date.getFullYear() === now.getFullYear();
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
  }).format(date);
}

export function joinSentences(...parts: Array<string | null | undefined | false>): string {
  // Склеивает фразы с сервера и интерфейса: у каждой фразы будет точка в конце,
  // даже если сервер прислал текст без неё.
  return parts
    .filter((part): part is string => Boolean(part && part.trim()))
    .map((part) => {
      const text = part.trim();
      return /[.!?…]$/.test(text) ? text : `${text}.`;
    })
    .join(' ');
}
