export interface SalaryRangeValue {
  from: number | null;
  to: number | null;
}

export function salaryRangeError(value: SalaryRangeValue): string | null {
  // Те же правила, что на бэкенде: обе границы обязательны, положительны и «от» ≤ «до».
  if (value.from == null || value.to == null) return 'Укажите вилку зарплаты «от» и «до»';
  if (value.from <= 0 || value.to <= 0) return 'Суммы должны быть больше нуля';
  if (value.from > value.to) return 'Нижняя граница не может быть больше верхней';
  return null;
}
