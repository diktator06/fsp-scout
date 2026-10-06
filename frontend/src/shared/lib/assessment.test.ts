import { describe, expect, it } from 'vitest';
import {
  competencyShare,
  confidenceBand,
  formatCountdown,
  groupByDirection,
  splitInlineCode,
  suggestGradeByExperience,
  thetaToPercent,
  timerTone,
} from './assessment';

describe('шкала способностей', () => {
  it('переводит θ в проценты ширины и прижимает выбросы к краям', () => {
    expect(thetaToPercent(0)).toBe(50);
    expect(thetaToPercent(-3)).toBe(0);
    expect(thetaToPercent(1.5)).toBe(75);
    expect(thetaToPercent(9)).toBe(100);
    expect(thetaToPercent(-9)).toBe(0);
  });

  it('строит 90-процентный интервал вокруг оценки', () => {
    const [low, high] = confidenceBand(0.4, 0.3);
    expect(low).toBeCloseTo(-0.092);
    expect(high).toBeCloseTo(0.892);
  });
});

describe('таймер задания', () => {
  it('форматирует секунды как м:сс', () => {
    expect(formatCountdown(65)).toBe('1:05');
    expect(formatCountdown(9.8)).toBe('0:09');
    expect(formatCountdown(-4)).toBe('0:00');
  });

  it('меняет тон ближе к концу времени', () => {
    expect(timerTone(100, 120)).toBe('calm');
    expect(timerTone(30, 120)).toBe('warning');
    expect(timerTone(12, 120)).toBe('critical');
  });
});

describe('подсказка грейда по опыту', () => {
  it.each([
    [null, 'intern'],
    [0, 'intern'],
    [1, 'junior'],
    [2, 'middle'],
    [3.5, 'middle'],
    [4, 'senior'],
    [12, 'senior'],
  ] as const)('%s лет → %s', (years, grade) => {
    expect(suggestGradeByExperience(years)).toBe(grade);
  });
});

describe('формулировка задания', () => {
  it('выделяет код в обратных кавычках', () => {
    expect(splitInlineCode("Что вернёт `df.mean()` для 'Омск'?")).toEqual([
      { text: 'Что вернёт ', code: false },
      { text: 'df.mean()', code: true },
      { text: " для 'Омск'?", code: false },
    ]);
  });

  it('оставляет текст без кода и непарные кавычки как есть', () => {
    expect(splitInlineCode('Сколько строк?')).toEqual([{ text: 'Сколько строк?', code: false }]);
    expect(splitInlineCode('кавычка ` одна')).toEqual([{ text: 'кавычка ` одна', code: false }]);
  });
});

describe('группировка специализаций', () => {
  it('сохраняет порядок справочника внутри и между направлениями', () => {
    const groups = groupByDirection([
      { code: 'backend', direction_code: 'development', direction_name: 'Разработка' },
      { code: 'qa', direction_code: 'quality', direction_name: 'Качество' },
      { code: 'frontend', direction_code: 'development', direction_name: 'Разработка' },
    ]);
    expect(groups.map((group) => group.code)).toEqual(['development', 'quality']);
    expect(groups[0]?.items.map((item) => item.code)).toEqual(['backend', 'frontend']);
  });
});

describe('доля верных ответов', () => {
  it('округляет до процента и не делит на ноль', () => {
    expect(competencyShare(2, 3)).toBe(67);
    expect(competencyShare(0, 0)).toBe(0);
  });
});
