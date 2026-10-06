import { describe, expect, it } from 'vitest';
import { buildInvitationTimeline } from './invitationStatus';

function states(status: Parameters<typeof buildInvitationTimeline>[0], viewedAt?: string) {
  return buildInvitationTimeline(status, { viewedAt: viewedAt ?? null }).map((step) => step.state);
}

describe('buildInvitationTimeline', () => {
  it('всегда возвращает три шага', () => {
    expect(buildInvitationTimeline('sent')).toHaveLength(3);
  });

  it('отправленное приглашение ждёт просмотра', () => {
    expect(states('sent')).toEqual(['done', 'current', 'upcoming']);
  });

  it('просмотренное ждёт ответа кандидата', () => {
    expect(states('viewed')).toEqual(['done', 'done', 'current']);
  });

  it('принятое отмечает успех и сообщает о раскрытии контактов', () => {
    const timeline = buildInvitationTimeline('accepted');
    expect(timeline.map((step) => step.state)).toEqual(['done', 'done', 'success']);
    expect(timeline[2]?.description).toContain('Контакты');
  });

  it('истёкшее без просмотра оставляет шаг «просмотрено» непройденным', () => {
    expect(states('expired')).toEqual(['done', 'upcoming', 'negative']);
    expect(states('expired', '2026-10-06T10:00:00Z')).toEqual(['done', 'done', 'negative']);
  });

  it('отзыв до просмотра не отмечает просмотр', () => {
    expect(states('withdrawn')).toEqual(['done', 'upcoming', 'negative']);
  });
});
