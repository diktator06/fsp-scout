import type { ApplicationStatus, RejectReason, VacancyStatus } from '@/api/types';
import type { TimelineStep } from './invitationStatus';

export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  submitted: 'Отправлен',
  viewed: 'Просмотрен',
  interview: 'Собеседование',
  rejected: 'Отказ',
  withdrawn: 'Отозван',
};

export const APPLICATION_STATUS_COLORS: Record<ApplicationStatus, string> = {
  submitted: 'lilac',
  viewed: 'fsp',
  interview: 'teal',
  rejected: 'signal',
  withdrawn: 'gray',
};

export const REJECT_REASON_LABELS: Record<RejectReason, string> = {
  skills: 'Не хватает навыков',
  grade: 'Нужен другой уровень',
  salary: 'Ожидания не совпали с вилкой',
  position_filled: 'Позиция уже закрыта',
  other: 'Другая причина',
};

export interface ApplicationMoments {
  createdAt?: string | null;
  viewedAt?: string | null;
  respondedAt?: string | null;
}

export function buildApplicationTimeline(
  status: ApplicationStatus,
  moments: ApplicationMoments = {},
): TimelineStep[] {
  // Тот же трёхшаговый таймлайн, что у приглашения, но инициатор — кандидат:
  // отправлен → просмотрен компанией → ответ компании.
  const viewed = status !== 'submitted' && (status !== 'withdrawn' || Boolean(moments.viewedAt));
  const steps: TimelineStep[] = [
    { key: 'sent', label: 'Отправлен', state: 'done', timestamp: moments.createdAt ?? null },
    {
      key: 'viewed',
      label: 'Просмотрен',
      state: viewed ? 'done' : status === 'submitted' ? 'current' : 'upcoming',
      timestamp: moments.viewedAt ?? null,
    },
  ];
  const finalStep: Record<ApplicationStatus, TimelineStep> = {
    submitted: { key: 'answer', label: 'Ответ компании', state: 'upcoming' },
    viewed: { key: 'answer', label: 'Ответ компании', state: 'current' },
    interview: {
      key: 'answer',
      label: 'Собеседование',
      state: 'success',
      description: 'Контакты компании открыты',
    },
    rejected: { key: 'answer', label: 'Отказ', state: 'negative' },
    withdrawn: { key: 'answer', label: 'Отозван вами', state: 'negative' },
  };
  steps.push({ ...finalStep[status], timestamp: moments.respondedAt ?? null });
  return steps;
}

export const VACANCY_STATUS_COPY: Record<VacancyStatus, { label: string; color: string }> = {
  draft: { label: 'Черновик', color: 'gray' },
  published: { label: 'Опубликована', color: 'teal' },
  closed: { label: 'Закрыта', color: 'gray' },
};
