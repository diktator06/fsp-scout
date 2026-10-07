import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/api/client';
import { unwrap } from '@/api/errors';
import { applySession, refreshSession, subscribeSession } from '@/api/session';
import type { CurrentUser, RegisterRequest } from '@/api/types';
import { AuthContext, type AuthContextValue, type AuthStatus } from './authContext';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');

  useEffect(() => {
    // Любое изменение сессии (вход, обновление, истечение при 401) приходит
    // через подписку. Так состояние интерфейса не расходится с токеном в памяти.
    const unsubscribe = subscribeSession((nextUser) => {
      setUser(nextUser);
      setStatus(nextUser ? 'authenticated' : 'anonymous');
    });
    void refreshSession().then((session) => {
      if (!session) setStatus('anonymous');
    });
    return unsubscribe;
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const session = await unwrap(api.POST('/api/v1/auth/login', { body: { email, password } }));
    applySession(session);
    return session.user;
  }, []);

  const register = useCallback(
    (payload: RegisterRequest) => unwrap(api.POST('/api/v1/auth/register', { body: payload })),
    [],
  );

  const verifyEmail = useCallback(async (token: string) => {
    const session = await unwrap(api.POST('/api/v1/auth/verify-email', { body: { token } }));
    applySession(session);
    return session.user;
  }, []);

  const loginWithFsp = useCallback(async (code: string, state: string) => {
    const session = await unwrap(api.POST('/api/v1/auth/fsp/callback', { body: { code, state } }));
    applySession(session);
    return session.user;
  }, []);

  const resendVerification = useCallback(async (email: string) => {
    await unwrap(api.POST('/api/v1/auth/resend-verification', { body: { email } }));
  }, []);

  const logout = useCallback(async () => {
    // Даже если сервер недоступен, локально сессию закрываем: пользователь нажал «Выйти»
    // и не должен оставаться в кабинете. Кеш запросов чистим, чтобы данные прошлого
    // пользователя не мелькнули следующему.
    try {
      await api.POST('/api/v1/auth/logout');
    } finally {
      applySession(null);
      queryClient.clear();
    }
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      login,
      register,
      verifyEmail,
      loginWithFsp,
      resendVerification,
      logout,
    }),
    [status, user, login, register, verifyEmail, loginWithFsp, resendVerification, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
