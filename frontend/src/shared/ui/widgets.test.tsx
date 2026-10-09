import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithTheme } from '@/test/render';
import { CategoryBadge } from './CategoryBadge';
import { GradeScale } from './GradeScale';
import { SalaryRange } from './SalaryRange';
import { salaryRangeError } from '@/shared/lib/salary';
import { computeScore } from '@/shared/lib/score';
import { VerifiedScoreBar } from './VerifiedScoreBar';

describe('CategoryBadge', () => {
  it('озвучивает категорию для скринридеров', () => {
    renderWithTheme(<CategoryBadge specialization="Backend-разработка" grade="middle" />);
    expect(screen.getByLabelText('Категория: Backend-разработка, грейд Middle')).toBeTruthy();
  });
});

describe('SalaryRange', () => {
  it('показывает подпись и вилку', () => {
    renderWithTheme(<SalaryRange from={220000} to={300000} label="Вилка" />);
    expect(screen.getByText('Вилка')).toBeTruthy();
    expect(screen.getByText('₽')).toBeTruthy();
  });
});

describe('salaryRangeError', () => {
  it('требует обе границы, положительные суммы и «от» ≤ «до»', () => {
    expect(salaryRangeError({ from: null, to: 100000 })).not.toBeNull();
    expect(salaryRangeError({ from: 0, to: 100000 })).not.toBeNull();
    expect(salaryRangeError({ from: 200000, to: 100000 })).not.toBeNull();
    expect(salaryRangeError({ from: 100000, to: 100000 })).toBeNull();
  });
});

describe('VerifiedScoreBar', () => {
  const factors = [
    { key: 'test', label: 'Тест', value: 0.9, weight: 0.55 },
    { key: 'fsp', label: 'ФСП', value: 0, weight: 0.15 },
  ];

  it('считает индекс как сумму вклада факторов', () => {
    expect(computeScore(factors)).toBe(50);
  });

  it('отдаёт значение через role="meter"', () => {
    renderWithTheme(<VerifiedScoreBar factors={factors} />);
    expect(screen.getByRole('meter').getAttribute('aria-valuenow')).toBe('50');
  });
});

describe('GradeScale', () => {
  const cuts = [
    { code: 'junior', name: 'Junior', cut: -0.6 },
    { code: 'middle', name: 'Middle', cut: 0.4 },
    { code: 'senior', name: 'Senior', cut: 1.3 },
  ];

  it('подписывает оценку и порог словами, а не символом θ', () => {
    renderWithTheme(<GradeScale cuts={cuts} theta={0.52} se={0.3} targetCode="middle" />);
    expect(screen.getByText('ваша оценка: 0,52')).toBeTruthy();
    expect(screen.getByText('порог Middle: 0,40')).toBeTruthy();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('зона грейда Middle');
  });
});
