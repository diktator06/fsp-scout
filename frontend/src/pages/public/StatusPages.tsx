import { Button, Center, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconCompassOff, IconLockAccess, IconPlugConnectedX } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { isRouteErrorResponse, Link, useRouteError } from 'react-router';
import { ROLE_HOME } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';

function StatusScreen({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action: ReactNode;
}) {
  return (
    <Center mih="70dvh" px="md">
      <Stack align="center" gap="md" maw={460} ta="center">
        <ThemeIcon size={64} radius="xl" variant="light" color="fsp">
          {icon}
        </ThemeIcon>
        <Title order={2}>{title}</Title>
        <Text c="dimmed" lh={1.6}>
          {text}
        </Text>
        {action}
      </Stack>
    </Center>
  );
}

export function NotFoundPage() {
  return (
    <StatusScreen
      icon={<IconCompassOff size={32} />}
      title="Страница не найдена"
      text="Возможно, ссылка устарела или в адресе опечатка."
      action={
        <Button component={Link} to="/">
          На главную
        </Button>
      }
    />
  );
}

export function ForbiddenPage() {
  // Сюда попадают, открыв раздел чужой роли. Предлагаем вернуться в свой кабинет,
  // а не на главную: так человек не теряет контекст.
  const { user } = useAuth();
  return (
    <StatusScreen
      icon={<IconLockAccess size={32} />}
      title="Нет доступа к разделу"
      text="Этот раздел относится к кабинету другой роли."
      action={
        <Button component={Link} to={user ? ROLE_HOME[user.role] : '/auth/login'}>
          {user ? 'Вернуться в свой кабинет' : 'Войти'}
        </Button>
      }
    />
  );
}

export function RouteErrorPage() {
  const error = useRouteError();
  const notFound = isRouteErrorResponse(error) && error.status === 404;
  if (notFound) return <NotFoundPage />;
  return (
    <StatusScreen
      icon={<IconPlugConnectedX size={32} />}
      title="Что-то пошло не так"
      text="Обновите страницу или вернитесь на главную. Если ошибка повторяется, напишите нам."
      action={
        <Button component={Link} to="/" reloadDocument>
          На главную
        </Button>
      }
    />
  );
}
