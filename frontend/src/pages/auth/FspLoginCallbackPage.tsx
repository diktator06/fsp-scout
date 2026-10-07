import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { ROLE_HOME } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';
import { FspReturnNotice } from '@/features/fsp/FspReturnNotice';
import { useFspReturn } from '@/features/fsp/useFspReturn';

export function FspLoginCallbackPage() {
  // Возврат после «Войти через ФСП ID»: бэкенд находит аккаунт по привязанному
  // участнику и открывает сессию так же, как вход по паролю.
  const navigate = useNavigate();
  const { loginWithFsp } = useAuth();
  const complete = useCallback(
    async (code: string, state: string) => {
      const user = await loginWithFsp(code, state);
      navigate(ROLE_HOME[user.role], { replace: true });
    },
    [loginWithFsp, navigate],
  );
  const { pending, error } = useFspReturn(complete);
  return (
    <FspReturnNotice
      pending={pending}
      pendingText="Проверяем вход через ФСП ID…"
      error={error}
      backTo="/auth/login"
      backLabel="Войти по email"
    />
  );
}
