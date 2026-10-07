export interface SalaryRangeValue {
  from: number | null;
  to: number | null;
}

export const MAX_SALARY_SPREAD = 2;
export const NET_TO_GROSS = 1 / 0.87;

export function toGross(amount: number, gross: boolean): number {
  // Ожидания «на руки» и вилки «до вычета НДФЛ» сравниваются в одной базе, как на бэкенде.
  return gross ? amount : amount * NET_TO_GROSS;
}

export function salaryRangeError(value: SalaryRangeValue): string | null {
  // Те же правила, что на бэкенде: обе границы обязательны, положительны, «от» ≤ «до»
  // и вилка не шире чем вдвое — иначе она ничего не говорит кандидату.
  if (value.from == null || value.to == null) return 'Укажите вилку зарплаты «от» и «до»';
  if (value.from <= 0 || value.to <= 0) return 'Суммы должны быть больше нуля';
  if (value.from > value.to) return 'Нижняя граница не может быть больше верхней';
  if (value.to > value.from * MAX_SALARY_SPREAD) {
    return 'Вилка слишком широкая: верхняя граница больше нижней больше чем вдвое';
  }
  return null;
}
