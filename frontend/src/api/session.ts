import type { CurrentUser, TokenResponse } from './types';

type SessionListener = (user: CurrentUser | null) => void;

let accessToken: string | null = null;
let refreshInFlight: Promise<TokenResponse | null> | null = null;
const listeners = new Set<SessionListener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function applySession(payload: TokenResponse | null): void {
  // Access-токен живёт только в памяти вкладки и не попадает в localStorage:
  // XSS-скрипт не сможет его вытащить. После перезагрузки страницы сессию
  // восстанавливает refresh-cookie, которую JavaScript не видит.
  accessToken = payload?.access_token ?? null;
  const user = payload?.user ?? null;
  listeners.forEach((listener) => listener(user));
}

export function subscribeSession(listener: SessionListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function refreshSession(): Promise<TokenResponse | null> {
  // Одновременные запросы, получившие 401, обновляют сессию одним вызовом.
  // Иначе второй вызов предъявил бы уже отозванный refresh-токен, и сервер
  // принял бы это за кражу и закрыл все сессии.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          credentials: 'same-origin',
        });
        if (!response.ok) {
          applySession(null);
          return null;
        }
        const payload = (await response.json()) as TokenResponse;
        applySession(payload);
        return payload;
      } catch {
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}
