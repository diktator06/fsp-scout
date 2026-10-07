import { describe, expect, it } from 'vitest';
import { aliasHue, salaryWarning, scoreTone } from './matching';
import { salaryRangeError, toGross } from './salary';

describe('проверка вилки', () => {
  it('совпадает с правилами бэкенда', () => {
    expect(salaryRangeError({ from: 200_000, to: 300_000 })).toBeNull();
    expect(salaryRangeError({ from: null, to: 300_000 })).toMatch('«от» и «до»');
    expect(salaryRangeError({ from: 300_000, to: 200_000 })).toMatch('больше верхней');
    expect(salaryRangeError({ from: 100_000, to: 250_000 })).toMatch('широкая');
  });

  it('переводит «на руки» в гросс', () => {
    expect(toGross(87_000, false)).toBeCloseTo(100_000);
    expect(toGross(100_000, true)).toBe(100_000);
  });
});

describe('предупреждение о вилке', () => {
  it('срабатывает, только если ожидания выше верхней границы', () => {
    expect(salaryWarning(250_000, true, 300_000, true)).toBeNull();
    expect(salaryWarning(330_000, true, 300_000, true)).toMatch('на 10 %');
    expect(salaryWarning(null, true, 300_000, true)).toBeNull();
  });

  it('сравнивает ожидания на руки с вилкой до вычета НДФЛ', () => {
    expect(salaryWarning(270_000, false, 300_000, true)).toMatch('на 3 %');
  });
});

describe('мелочи подбора', () => {
  it('тон балла и стабильный цвет псевдонима', () => {
    expect([scoreTone(72), scoreTone(45), scoreTone(10)]).toEqual(['strong', 'medium', 'weak']);
    expect(aliasHue('A7F3')).toBe(aliasHue('A7F3'));
    expect(aliasHue('A7F3')).toBeGreaterThanOrEqual(260);
  });
});
