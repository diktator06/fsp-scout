import type { AssignmentStatus, MicroTaskKind } from '@/api/types';

export const TASK_KIND_LABELS: Record<MicroTaskKind, string> = {
  solve: 'Решить',
  approach: 'Предложить подход',
};

export const ASSIGNMENT_STATUS_COPY: Record<AssignmentStatus, { label: string; color: string }> = {
  assigned: { label: 'Ждёт ответа', color: 'lilac' },
  submitted: { label: 'На оценке', color: 'fsp' },
  graded: { label: 'Оценено', color: 'teal' },
  expired: { label: 'Срок истёк', color: 'gray' },
  skipped: { label: 'Пропущено', color: 'gray' },
};

export function scoreOutOfFive(score: number | null | undefined): string | null {
  // Балл задачи 0..1 показываем привычной пятибалльной шкалой.
  if (score === null || score === undefined) return null;
  return `${Math.round(score * 5)}/5`;
}
