export interface ScoreFactor {
  key: string;
  label: string;
  value: number;
  weight: number;
  color?: string;
  hint?: string;
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function computeScore(factors: ScoreFactor[]): number {
  // Индекс = Σ вес × значение, в баллах от 0 до 100. Та же формула, что в
  // разделе 3.6.1 плана: виджет показывает ровно то, что посчитал бэкенд.
  const total = factors.reduce((sum, factor) => sum + clamp01(factor.value) * factor.weight, 0);
  return Math.round(total * 100);
}
