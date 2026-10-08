import type { ItemFamilyStatus, ItemInstance } from '@/api/types';
import { NBSP } from './format';

export const MIN_CUT_GAP = 0.3;
export const EXPOSURE_WARNING = 0.35;
export const EXPOSURE_HIGH = 0.6;

export const FAMILY_STATUS_COPY: Record<
  ItemFamilyStatus,
  { label: string; color: string; hint: string }
> = {
  active: {
    label: 'В оценке',
    color: 'teal',
    hint: 'Участвует в оценке и влияет на результат',
  },
  pilot: {
    label: 'Пилот',
    color: 'lilac',
    hint: 'Показывается без влияния на результат и копит ответы для калибровки',
  },
  draft: { label: 'Черновик', color: 'gray', hint: 'Готовится, кандидатам не показывается' },
  compromised: {
    label: 'Скомпрометировано',
    color: 'signal',
    hint: 'Отключено из-за утечки шаблона',
  },
  retired: { label: 'Выведено', color: 'gray', hint: 'Больше не показывается' },
};

export const EDITABLE_STATUSES: ItemFamilyStatus[] = ['active', 'pilot', 'retired', 'compromised'];

export function formatDecimal(value: number, digits = 2): string {
  // Десятичная запятая и типографский минус: «−0,70», как в документации.
  return value.toFixed(digits).replace('.', ',').replace('-', '−');
}

export function formatShare(value: number | null | undefined): string {
  // Доля целыми процентами; отсутствие данных — тире, а не «0 %».
  if (value === null || value === undefined) return '—';
  return `${Math.round(value * 100)}${NBSP}%`;
}

export type ExposureTone = 'ok' | 'warn' | 'high';

export function exposureTone(rate: number | null | undefined): ExposureTone {
  // Порог предупреждения совпадает с целевым ограничением экспозиции движка (35 %):
  // выше него семейство видит слишком большая доля кандидатов, шаблон легче слить.
  if (rate === null || rate === undefined || rate < EXPOSURE_WARNING) return 'ok';
  return rate < EXPOSURE_HIGH ? 'warn' : 'high';
}

export function formatAnswer(answer: ItemInstance['answer'], unit?: string | null): string {
  // Ключ ответа для методиста: буква и текст варианта или число с допуском.
  if (answer.kind === 'choice') {
    return `${(answer.correct ?? '').toUpperCase()}) ${answer.text ?? ''}`.trim();
  }
  const value = answer.value === null || answer.value === undefined ? '—' : String(answer.value);
  const tolerance = answer.tolerance ? ` ± ${String(answer.tolerance).replace('.', ',')}` : '';
  return `${value.replace('.', ',')}${tolerance}${unit ? ` ${unit}` : ''}`;
}

export function cutError(
  value: number,
  lower: number | null,
  higher: number | null,
  gap = MIN_CUT_GAP,
): string | null {
  // Та же проверка, что на сервере: порядок грейдов сохраняется с зазором, иначе два
  // соседних грейда станут неразличимы при типичной ошибке измерения.
  const epsilon = 1e-9;
  if (lower !== null && value < lower + gap - epsilon) {
    return `Не ниже ${formatDecimal(lower + gap)}: порог младшего грейда + ${formatDecimal(gap, 1)}`;
  }
  if (higher !== null && value > higher - gap + epsilon) {
    return `Не выше ${formatDecimal(higher - gap)}: порог старшего грейда − ${formatDecimal(gap, 1)}`;
  }
  return null;
}

export function formatParams(params: Record<string, unknown>): string[] {
  // Параметры экземпляра коротко: «n = 7», «таблица = orders». Вложенные структуры
  // сворачиваются в JSON, чтобы методист видел, что именно варьирует генератор.
  return Object.entries(params).map(([key, value]) => {
    const text =
      typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value);
    return `${key} = ${text.length > 40 ? `${text.slice(0, 39)}…` : text}`;
  });
}
