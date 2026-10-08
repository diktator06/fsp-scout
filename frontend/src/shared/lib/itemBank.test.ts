import { describe, expect, it } from 'vitest';
import {
  cutError,
  exposureTone,
  formatAnswer,
  formatDecimal,
  formatParams,
  formatShare,
} from './itemBank';

describe('formatDecimal', () => {
  it('ставит запятую и типографский минус', () => {
    expect(formatDecimal(-0.7)).toBe('−0,70');
    expect(formatDecimal(1.25, 1)).toBe('1,3');
  });
});

describe('formatShare', () => {
  it('показывает тире без данных', () => {
    expect(formatShare(null)).toBe('—');
    expect(formatShare(0.354)).toBe('35 %');
  });
});

describe('exposureTone', () => {
  it('предупреждает с порога ограничения экспозиции', () => {
    expect(exposureTone(null)).toBe('ok');
    expect(exposureTone(0.2)).toBe('ok');
    expect(exposureTone(0.4)).toBe('warn');
    expect(exposureTone(0.8)).toBe('high');
  });
});

describe('formatAnswer', () => {
  it('показывает вариант и число с допуском', () => {
    expect(formatAnswer({ kind: 'choice', correct: 'b', text: 'O(n)' })).toBe('B) O(n)');
    expect(formatAnswer({ kind: 'numeric', value: 11.5, tolerance: 0.1 }, 'мс')).toBe(
      '11,5 ± 0,1 мс',
    );
    expect(formatAnswer({ kind: 'numeric', value: 42, tolerance: 0 })).toBe('42');
  });
});

describe('cutError', () => {
  it('держит порядок грейдов с зазором 0,3', () => {
    expect(cutError(0.4, -0.5, 1.2)).toBeNull();
    expect(cutError(-0.3, -0.5, 1.2)).toContain('Не ниже');
    expect(cutError(1.0, -0.5, 1.2)).toContain('Не выше');
    expect(cutError(0.9, -0.5, 1.2)).toBeNull();
    expect(cutError(2.5, 1.2, null)).toBeNull();
  });
});

describe('formatParams', () => {
  it('сворачивает длинные значения', () => {
    const [short, long] = formatParams({ n: 7, data: 'x'.repeat(60) });
    expect(short).toBe('n = 7');
    expect(long?.endsWith('…')).toBe(true);
  });
});
