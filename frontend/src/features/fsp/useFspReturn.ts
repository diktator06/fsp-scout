import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { errorMessage } from '@/api/errors';

const PROVIDER_ERRORS: Record<string, string> = {
  access_denied: 'Вы отменили вход на странице ФСП ID. Ничего не изменилось.',
};

export function useFspReturn(complete: (code: string, state: string) => Promise<void>) {
  // Разбирает адрес возврата из ФСП ID и один раз передаёт code и state бэкенду.
  // Код одноразовый, а StrictMode вызывает эффект дважды — повтор отсекает флаг.
  const [searchParams] = useSearchParams();
  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const providerError = searchParams.get('error');
  const [error, setError] = useState<string | null>(() => {
    if (providerError) {
      return PROVIDER_ERRORS[providerError] ?? 'ФСП ID вернул ошибку, попробуйте ещё раз.';
    }
    return code && state ? null : 'В ответе ФСП ID нет кода авторизации.';
  });
  const [pending, setPending] = useState(Boolean(code && state && !providerError));
  const requested = useRef(false);

  useEffect(() => {
    if (!code || !state || providerError || requested.current) return;
    requested.current = true;
    complete(code, state)
      .catch((failure: unknown) => setError(errorMessage(failure)))
      .finally(() => setPending(false));
  }, [code, state, providerError, complete]);

  return { pending, error };
}
