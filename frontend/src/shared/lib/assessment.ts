import type { GradeCode } from './grades';

export const THETA_MIN = -3;
export const THETA_MAX = 3;
export const CONFIDENCE_Z = 1.64;

export type SessionOutcomeCode = 'passed_confident' | 'passed' | 'failed';

export const OUTCOME_COPY: Record<
  SessionOutcomeCode,
  { title: string; short: string; color: string; text: string }
> = {
  passed_confident: {
    title: 'Грейд подтверждён с запасом',
    short: 'С запасом',
    color: 'teal',
    text: 'Оценка уверенно выше порога следующего уровня, поэтому тест на него открыт сразу, без паузы.',
  },
  passed: {
    title: 'Грейд подтверждён',
    short: 'Подтверждён',
    color: 'fsp',
    text: 'Категория присвоена. Работодатели находят кандидатов по категориям в банке — после публикации профиля.',
  },
  failed: {
    title: 'Грейд пока не подтверждён',
    short: 'Не подтверждён',
    color: 'signal',
    text: 'Попытка не сгорела: тест на уровень ниже доступен сразу, повтор этого уровня — через сутки.',
  },
};

export const MODE_LABELS = { full: 'Полный тест', express: 'Экспресс' } as const;

export function thetaToPercent(theta: number): number {
  // Положение на шкале способностей в процентах ширины. Края шкалы — ±3σ:
  // за ними оказывается меньше 0,3 % кандидатов, дальше маркер прижимается к краю.
  const clamped = Math.min(THETA_MAX, Math.max(THETA_MIN, theta));
  return ((clamped - THETA_MIN) / (THETA_MAX - THETA_MIN)) * 100;
}

export function confidenceBand(theta: number, se: number): [number, number] {
  // 90-процентный интервал оценки — та же граница, по которой движок решает,
  // уверенно ли кандидат выше или ниже порога.
  return [theta - CONFIDENCE_Z * se, theta + CONFIDENCE_Z * se];
}

export function formatCountdown(totalSeconds: number): string {
  // «1:05» для таймера задания; отрицательное время показываем как ноль.
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

export type TimerTone = 'calm' | 'warning' | 'critical';

export function timerTone(secondsLeft: number, limit: number): TimerTone {
  // Таймер краснеет на последних 15 секундах и желтеет на последней четверти:
  // цвет предупреждает заранее, но не дёргает в начале задания.
  if (secondsLeft <= 15) return 'critical';
  if (secondsLeft <= limit / 4) return 'warning';
  return 'calm';
}

export function suggestGradeByExperience(years: number | null | undefined): GradeCode {
  // Подсказка соответствует описаниям грейдов в справочнике: без опыта — Intern,
  // до двух лет — Junior, 2–4 года — Middle, дальше — Senior. Это только подсказка:
  // уровень подтверждает тест.
  if (years == null || years < 0.5) return 'intern';
  if (years < 2) return 'junior';
  if (years < 4) return 'middle';
  return 'senior';
}

export interface TextSegment {
  text: string;
  code: boolean;
}

export function splitInlineCode(text: string): TextSegment[] {
  // В формулировках заданий фрагменты кода выделены обратными кавычками:
  // «Что вернёт `df.groupby('city')`?». Непарная кавычка остаётся обычным текстом.
  const segments: TextSegment[] = [];
  const pattern = /`([^`\n]+)`/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) segments.push({ text: text.slice(cursor, start), code: false });
    segments.push({ text: match[1] ?? '', code: true });
    cursor = start + match[0].length;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), code: false });
  return segments;
}

export interface DirectionGroup<T> {
  code: string;
  name: string;
  items: T[];
}

export function groupByDirection<T extends { direction_code: string; direction_name: string }>(
  items: readonly T[],
): DirectionGroup<T>[] {
  // Направления идут в порядке первой специализации из справочника, поэтому
  // порядок задаёт методист через sort_order, а не алфавит.
  const groups = new Map<string, DirectionGroup<T>>();
  for (const item of items) {
    const group = groups.get(item.direction_code);
    if (group) group.items.push(item);
    else
      groups.set(item.direction_code, {
        code: item.direction_code,
        name: item.direction_name,
        items: [item],
      });
  }
  return [...groups.values()];
}

export function competencyShare(correct: number, answered: number): number {
  // Доля верных ответов по компетенции в процентах; без заданий — ноль, а не NaN.
  return answered > 0 ? Math.round((correct / answered) * 100) : 0;
}
