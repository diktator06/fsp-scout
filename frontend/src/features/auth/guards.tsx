import { Center, Loader, Stack, Text } from '@mantine/core';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import type { UserRole } from '@/api/types';
import { ROLE_HOME } from './roles';
import { useAuth } from './useAuth';

function SessionLoader() {
  return (
    <Center mih="100dvh">
      <Stack align="center" gap="sm">
        <Loader color="fsp" type="dots" />
        <Text c="dimmed" size="sm">
          Восстанавливаем сессию…
        </Text>
      </Stack>
    </Center>
  );
}

export function RequireRole({ roles, children }: { roles: UserRole[]; children: ReactNode }) {
  // Защита маршрутов кабинетов. Гостя отправляем на вход с возвратом на исходную
  // страницу, а пользователя чужой роли — на экран «нет доступа». Так не выйдет
  // молча перекинуть работодателя в кабинет кандидата и наоборот.
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <SessionLoader />;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/auth/login?next=${next}`} replace />;
  }
  if (!roles.includes(user.role)) return <Navigate to="/forbidden" replace />;
  return <>{children}</>;
}

export function GuestOnly({ children }: { children: ReactNode }) {
  // Вошедшему пользователю формы входа и регистрации не нужны: сразу ведём в кабинет.
  const { status, user } = useAuth();
  if (status === 'loading') return <SessionLoader />;
  if (user) return <Navigate to={ROLE_HOME[user.role]} replace />;
  return <>{children}</>;
}
