import type { FspEventLevel, FspResultStatus, FspState } from '@/api/types';

export const FSP_RESULT_LABELS: Record<FspResultStatus, string> = {
  winner: 'Победитель',
  prize: 'Призёр',
  finalist: 'Финалист',
  participant: 'Участник',
};

export const FSP_RESULT_COLORS: Record<FspResultStatus, string> = {
  winner: 'signal',
  prize: 'fsp',
  finalist: 'lilac',
  participant: 'gray',
};

export const FSP_LEVEL_LABELS: Record<FspEventLevel, string> = {
  international: 'Международные',
  national: 'Всероссийские',
  interregional: 'Межрегиональные',
  regional: 'Региональные',
  local: 'Муниципальные',
};

export const FSP_STATE_LABELS: Record<FspState, string> = {
  not_linked: 'ФСП ID не привязан',
  linked_empty: 'Привязан, участий пока нет',
  linked: 'Подтверждено реестром ФСП',
  hidden: 'Скрыто кандидатом',
};

export function placeText(place: number | null | undefined, total: number | null | undefined) {
  // «3 место из 140» — по месту и числу участников видна сила результата
  // без ранжирования соревнований по уровню.
  if (!place) return null;
  return total ? `${place} место из ${total}` : `${place} место`;
}

export function placePercentile(
  place: number | null | undefined,
  total: number | null | undefined,
): number | null {
  // Доля участников, которых человек опередил: «выше 92 % участников».
  if (!place || !total || total < 2) return null;
  return Math.round(((total - place) / (total - 1)) * 100);
}

export function isSafeProtocolUrl(url: string | null | undefined): url is string {
  // Ссылка из внешнего реестра попадает в href: пропускаем только http(s),
  // чтобы запись вида javascript:… не превратилась в XSS. Бэкенд проверяет то же самое.
  return Boolean(url && /^https?:\/\//i.test(url));
}
