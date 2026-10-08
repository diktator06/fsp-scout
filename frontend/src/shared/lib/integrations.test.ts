import { describe, expect, it } from 'vitest';
import { responseSummary } from './integrations';

describe('responseSummary', () => {
  it('показывает message из JSON-ответа получателя', () => {
    expect(responseSummary('{"received":true,"message":"Связь установлена"}', '')).toBe(
      'Связь установлена',
    );
  });

  it('оставляет текстовый ответ и ошибку соединения как есть', () => {
    expect(responseSummary('maintenance', 'Получатель ответил 503')).toBe('maintenance');
    expect(responseSummary('', 'Получатель не ответил вовремя')).toBe(
      'Получатель не ответил вовремя',
    );
    expect(responseSummary('{"ok":true}', '')).toBe('{"ok":true}');
  });
});
