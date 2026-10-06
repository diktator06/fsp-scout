import createClient, { type Middleware } from 'openapi-fetch';
import type { paths } from './schema.gen';
import { getAccessToken, refreshSession } from './session';

const PUBLIC_AUTH_PATHS = new Set([
  '/api/v1/auth/login',
  '/api/v1/auth/refresh',
  '/api/v1/auth/register',
  '/api/v1/auth/verify-email',
  '/api/v1/auth/resend-verification',
  '/api/v1/auth/logout',
]);

const retryCopies = new Map<string, Request>();

const authMiddleware: Middleware = {
  onRequest({ request, schemaPath, id }) {
    // Копию запроса снимаем до отправки: тело читается один раз, а при 401
    // запрос придётся повторить с новым токеном.
    const token = getAccessToken();
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    if (!PUBLIC_AUTH_PATHS.has(schemaPath)) retryCopies.set(id, request.clone());
    return request;
  },
  async onResponse({ response, schemaPath, id }) {
    const copy = retryCopies.get(id);
    retryCopies.delete(id);
    if (response.status !== 401 || !copy || PUBLIC_AUTH_PATHS.has(schemaPath)) return response;

    const session = await refreshSession();
    if (!session) return response;
    copy.headers.set('Authorization', `Bearer ${session.access_token}`);
    return fetch(copy);
  },
  onError({ id }) {
    retryCopies.delete(id);
  },
};

export const api = createClient<paths>({ baseUrl: '', credentials: 'same-origin' });
api.use(authMiddleware);
