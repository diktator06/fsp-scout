export const GRADE_ORDER = ['intern', 'junior', 'middle', 'senior'] as const;

export type GradeCode = (typeof GRADE_ORDER)[number];

export const GRADE_LABELS: Record<GradeCode, string> = {
  intern: 'Intern',
  junior: 'Junior',
  middle: 'Middle',
  senior: 'Senior',
};

export function isGradeCode(value: string): value is GradeCode {
  return (GRADE_ORDER as readonly string[]).includes(value);
}

export function gradeRank(code: string): number {
  // Ранг от 1 до 4. Неизвестный код (новый грейд из справочника) получает 0:
  // у шкалы уровня тогда нет закрашенных делений, а не падение интерфейса.
  return isGradeCode(code) ? GRADE_ORDER.indexOf(code) + 1 : 0;
}
