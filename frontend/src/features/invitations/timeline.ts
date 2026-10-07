import type { InvitationEvent, InvitationStatusCode } from '@/api/types';
import { buildInvitationTimeline, type TimelineStep } from '@/shared/lib/invitationStatus';

export function invitationTimeline(
  status: InvitationStatusCode,
  events: InvitationEvent[],
): TimelineStep[] {
  // Таймлайн из журнала переходов: момент отправки, просмотра и ответа берётся из
  // событий, а не из полей приглашения, поэтому совпадает у обеих сторон.
  const at = (target: InvitationStatusCode) =>
    events.find((event) => event.status === target)?.at ?? null;
  const responded = events.find((event) =>
    ['accepted', 'declined', 'withdrawn', 'expired'].includes(event.status),
  );
  return buildInvitationTimeline(status, {
    sentAt: at('sent'),
    viewedAt: at('viewed'),
    respondedAt: responded?.at ?? null,
  });
}
