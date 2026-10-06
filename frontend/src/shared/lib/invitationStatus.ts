export const INVITATION_STATUSES = [
  'sent',
  'viewed',
  'accepted',
  'declined',
  'withdrawn',
  'expired',
] as const;

export type InvitationStatus = (typeof INVITATION_STATUSES)[number];

export const INVITATION_STATUS_LABELS: Record<InvitationStatus, string> = {
  sent: 'Отправлено',
  viewed: 'Просмотрено',
  accepted: 'Принято',
  declined: 'Отклонено',
  withdrawn: 'Отозвано',
  expired: 'Срок истёк',
};

export const INVITATION_STATUS_COLORS: Record<InvitationStatus, string> = {
  sent: 'lilac',
  viewed: 'fsp',
  accepted: 'teal',
  declined: 'signal',
  withdrawn: 'gray',
  expired: 'gray',
};

export type TimelineStepState = 'done' | 'current' | 'upcoming' | 'success' | 'negative';

export interface TimelineStep {
  key: string;
  label: string;
  state: TimelineStepState;
  timestamp?: string | Date | null;
  description?: string;
}

export interface InvitationMoments {
  sentAt?: string | Date | null;
  viewedAt?: string | Date | null;
  respondedAt?: string | Date | null;
}

export function buildInvitationTimeline(
  status: InvitationStatus,
  moments: InvitationMoments = {},
): TimelineStep[] {
  // Таймлайн всегда из трёх шагов, чтобы обе стороны видели, где сейчас приглашение:
  // отправлено → просмотрено → ответ. Отзыв и истечение срока — не ответ кандидата,
  // поэтому третий шаг подписывается по-разному, а «просмотрено» может остаться
  // непройденным (приглашение истекло, так и не открытое).
  const viewed = status !== 'sent' && (status !== 'expired' || Boolean(moments.viewedAt));
  const withdrawnBeforeView = status === 'withdrawn' && !moments.viewedAt;

  const steps: TimelineStep[] = [
    { key: 'sent', label: 'Отправлено', state: 'done', timestamp: moments.sentAt ?? null },
    {
      key: 'viewed',
      label: 'Просмотрено',
      state: viewed && !withdrawnBeforeView ? 'done' : status === 'sent' ? 'current' : 'upcoming',
      timestamp: moments.viewedAt ?? null,
    },
  ];

  const finalStep: Record<InvitationStatus, TimelineStep> = {
    sent: { key: 'answer', label: 'Ответ кандидата', state: 'upcoming' },
    viewed: { key: 'answer', label: 'Ответ кандидата', state: 'current' },
    accepted: {
      key: 'answer',
      label: 'Принято',
      state: 'success',
      description: 'Контакты открыты обеим сторонам',
    },
    declined: { key: 'answer', label: 'Отклонено', state: 'negative' },
    withdrawn: { key: 'answer', label: 'Отозвано компанией', state: 'negative' },
    expired: { key: 'answer', label: 'Срок ответа истёк', state: 'negative' },
  };

  steps.push({ ...finalStep[status], timestamp: moments.respondedAt ?? null });
  return steps;
}
