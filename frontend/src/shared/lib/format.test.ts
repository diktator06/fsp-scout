import { describe, expect, it } from 'vitest';
import { formatRub, formatSalaryRange, pluralizeRu } from './format';

const NBSP = '\u00a0';

describe('formatRub', () => {
  it('разделяет разряды неразрывным пробелом', () => {
    expect(formatRub(220000).replace(/\s/g, ' ')).toBe('220 000');
    expect(formatRub(220000)).not.toContain(' ');
  });
});

describe('formatSalaryRange', () => {
  it('показывает полную вилку с длинным тире и знаком рубля', () => {
    expect(formatSalaryRange(220000, 300000).replace(/[\u00a0\u202f]/g, ' ')).toBe(
      '220 000 – 300 000 ₽',
    );
  });

  it('схлопывает одинаковые границы и не зависит от порядка аргументов', () => {
    expect(formatSalaryRange(150000, 150000)).toBe(`150${NBSP}000${NBSP}₽`);
    expect(formatSalaryRange(300000, 220000)).toBe(formatSalaryRange(220000, 300000));
  });

  it('в компактном виде пишет единицу измерения один раз', () => {
    expect(formatSalaryRange(220000, 300000, { compact: true })).toBe(`220–300${NBSP}тыс.${NBSP}₽`);
    expect(formatSalaryRange(1200000, 1500000, { compact: true })).toBe(
      `1,2–1,5${NBSP}млн${NBSP}₽`,
    );
    expect(formatSalaryRange(800000, 1200000, { compact: true })).toBe(
      `800${NBSP}тыс. – 1,2${NBSP}млн${NBSP}₽`,
    );
  });

  it('может не добавлять знак валюты', () => {
    expect(formatSalaryRange(90000, 120000, { withCurrency: false })).not.toContain('₽');
  });
});

describe('pluralizeRu', () => {
  const forms = ['кандидат', 'кандидата', 'кандидатов'] as const;

  it.each([
    [1, 'кандидат'],
    [2, 'кандидата'],
    [5, 'кандидатов'],
    [11, 'кандидатов'],
    [14, 'кандидатов'],
    [21, 'кандидат'],
    [104, 'кандидата'],
  ])('%i → %s', (count, expected) => {
    expect(pluralizeRu(count, forms)).toBe(expected);
  });
});
