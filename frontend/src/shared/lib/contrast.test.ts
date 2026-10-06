import { describe, expect, it } from 'vitest';
import { contrastLevel, contrastRatio } from './contrast';

describe('contrastRatio', () => {
  it('даёт 21:1 для чёрного на белом и 1:1 для одинаковых цветов', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
    expect(contrastRatio('#520978', '#520978')).toBeCloseTo(1, 5);
  });

  it('подтверждает выбор оттенков палитры для белого текста', () => {
    expect(contrastLevel(contrastRatio('#ffffff', '#520978'))).toBe('AAA');
    expect(contrastLevel(contrastRatio('#ffffff', '#d90047'))).toBe('AA');
    expect(contrastLevel(contrastRatio('#ffffff', '#ff0053'))).toBe('AA крупный');
  });

  it('вторичный текст проходит AA на фоне страницы', () => {
    expect(contrastRatio('#5b5e6b', '#f6f4fa')).toBeGreaterThanOrEqual(4.5);
  });
});
