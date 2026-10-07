const INDEX_BEFORE_KEY = 'scout.fsp.indexBefore';

export function rememberIndexBefore(value: number | null | undefined): void {
  // Перед уходом на страницу ФСП ID запоминаем индекс, чтобы после возврата показать,
  // насколько он вырос. Хранилище вкладки может быть недоступно — тогда просто без сравнения.
  try {
    if (value == null) sessionStorage.removeItem(INDEX_BEFORE_KEY);
    else sessionStorage.setItem(INDEX_BEFORE_KEY, String(Math.round(value)));
  } catch {
    // Сравнение «было — стало» необязательно, привязка работает и без него.
  }
}

export function takeIndexBefore(): number | null {
  // Забирает сохранённый индекс один раз: повторное открытие страницы его не покажет.
  try {
    const raw = sessionStorage.getItem(INDEX_BEFORE_KEY);
    sessionStorage.removeItem(INDEX_BEFORE_KEY);
    const value = raw === null ? Number.NaN : Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}
