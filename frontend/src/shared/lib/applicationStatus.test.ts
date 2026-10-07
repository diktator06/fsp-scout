import { describe, expect, it } from 'vitest';
import { buildApplicationTimeline } from './applicationStatus';

describe('buildApplicationTimeline', () => {
  it('ждёт просмотра после отправки', () => {
    const steps = buildApplicationTimeline('submitted');
    expect(steps.map((step) => step.state)).toEqual(['done', 'current', 'upcoming']);
  });

  it('показывает собеседование успехом, а отзыв без просмотра — без шага просмотра', () => {
    expect(buildApplicationTimeline('interview').at(-1)?.state).toBe('success');
    const withdrawn = buildApplicationTimeline('withdrawn');
    expect(withdrawn[1]?.state).toBe('upcoming');
    expect(withdrawn.at(-1)?.label).toBe('Отозван вами');
  });
});
