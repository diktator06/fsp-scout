import { describe, expect, it } from 'vitest';
import { invitationTimeline } from './timeline';

describe('таймлайн приглашения из журнала', () => {
  it('берёт моменты из событий', () => {
    const steps = invitationTimeline('accepted', [
      { status: 'sent', at: '2026-10-07T09:00:00Z', actor: 'employer' },
      { status: 'viewed', at: '2026-10-07T10:00:00Z', actor: 'candidate' },
      { status: 'accepted', at: '2026-10-07T11:00:00Z', actor: 'candidate' },
    ]);
    expect(steps.map((step) => step.state)).toEqual(['done', 'done', 'success']);
    expect(steps[2]?.timestamp).toBe('2026-10-07T11:00:00Z');
  });

  it('истёкшее без просмотра оставляет просмотр непройденным', () => {
    const steps = invitationTimeline('expired', [
      { status: 'sent', at: '2026-10-07T09:00:00Z', actor: 'employer' },
      { status: 'expired', at: '2026-10-21T09:00:00Z', actor: 'system' },
    ]);
    expect(steps.map((step) => step.state)).toEqual(['done', 'upcoming', 'negative']);
  });
});
