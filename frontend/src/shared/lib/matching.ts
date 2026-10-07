import { toGross } from './salary';

export const SKILL_STATUS_COPY = {
  verified: { label: 'подтверждён тестом', short: '✓', color: 'teal' },
  declared: { label: 'заявлен', short: '•', color: 'fsp' },
  related: { label: 'есть родственный', short: '≈', color: 'lilac' },
  missing: { label: 'нет в профиле', short: '✗', color: 'signal' },
} as const;

export type SkillStatus = keyof typeof SKILL_STATUS_COPY;

export const RELATION_LABELS: Record<string, string> = {
  target: 'Ваша категория',
  adjacent_grade: 'Соседний грейд',
  adjacent_specialization: 'Смежная специализация',
};

export const PENALTY_LABELS: Record<string, string> = {
  unconfirmed_grade: 'грейд не подтверждён тестом',
  adjacent_grade: 'соседний грейд',
};

export const DECLINE_REASON_LABELS = {
  salary: 'Не устраивает зарплата',
  stack: 'Не мой стек',
  work_format: 'Не подходит формат работы',
  not_looking: 'Сейчас не ищу работу',
  company: 'Не интересна компания',
  other: 'Другое',
} as const;

export const COMPANY_SIZE_LABELS = {
  tiny: 'до 10 человек',
  small: '10–50 человек',
  medium: '50–250 человек',
  large: '250–1000 человек',
  enterprise: 'больше 1000 человек',
} as const;

export const TRUST_LEVEL_COPY = {
  new: { label: 'Новая компания', color: 'gray' },
  basic: { label: 'Проверенная', color: 'lilac' },
  verified: { label: 'Подтверждённая', color: 'teal' },
} as const;

export function scoreTone(score: number): 'strong' | 'medium' | 'weak' {
  // Балл соответствия 0–100: от 60 — сильное совпадение (тот же порог, что в
  // рыночном срезе на бэкенде), от 40 — среднее.
  if (score >= 60) return 'strong';
  if (score >= 40) return 'medium';
  return 'weak';
}

export function salaryWarning(
  expectation: number | null | undefined,
  expectationGross: boolean,
  offerTo: number | null,
  offerGross: boolean,
): string | null {
  // Предупреждение до отправки приглашения: если ожидания кандидата выше верхней
  // границы вилки, отказ почти гарантирован. Сравнение — в одной базе (до НДФЛ).
  if (expectation == null || offerTo == null) return null;
  const wanted = toGross(expectation, expectationGross);
  const ceiling = toGross(offerTo, offerGross);
  if (wanted <= ceiling) return null;
  const gap = Math.round((wanted / ceiling - 1) * 100);
  return `Ожидания кандидата выше верхней границы вилки примерно на ${gap} %`;
}

export function aliasHue(alias: string): number {
  // Цвет аватара выводится из псевдонима: один и тот же кандидат всегда одного цвета,
  // а соседние карточки различимы без фотографий.
  let hash = 0;
  for (const char of alias) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return 260 + (hash % 80);
}
