import { Anchor, Button, Loader, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconCircleCheck, IconLinkOff } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import type { CurrentUser } from '@/api/types';
import { errorMessage } from '@/api/errors';
import { ROLE_HOME } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';
import classes from './AuthPages.module.css';

type VerificationState =
  | { kind: 'pending' }
  | { kind: 'success'; user: CurrentUser }
  | { kind: 'failed'; message: string };

const REDIRECT_DELAY_MS = 1500;

export function VerifyEmailPage() {
  const { verifyEmail } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [state, setState] = useState<VerificationState>(
    token ? { kind: 'pending' } : { kind: 'failed', message: 'В ссылке нет токена подтверждения' },
  );
  const requested = useRef(false);

  useEffect(() => {
    // Токен одноразовый. В StrictMode React вызывает эффект дважды, и второй вызов
    // получил бы «ссылка уже использована». Флаг гарантирует один запрос.
    if (!token || requested.current) return;
    requested.current = true;
    verifyEmail(token)
      .then((user) => setState({ kind: 'success', user }))
      .catch((error: unknown) => setState({ kind: 'failed', message: errorMessage(error) }));
  }, [token, verifyEmail]);

  useEffect(() => {
    if (state.kind !== 'success') return undefined;
    const timeout = window.setTimeout(
      () => navigate(ROLE_HOME[state.user.role], { replace: true }),
      REDIRECT_DELAY_MS,
    );
    return () => window.clearTimeout(timeout);
  }, [state, navigate]);

  return (
    <Paper p={{ base: 'lg', sm: 40 }} shadow="md" className={classes.card}>
      {state.kind === 'pending' && (
        <Stack align="center" gap="md" py="xl">
          <Loader color="fsp" />
          <Text c="dimmed">Подтверждаем адрес…</Text>
        </Stack>
      )}

      {state.kind === 'success' && (
        <Stack gap="lg">
          <ThemeIcon size={56} radius="lg" color="teal" variant="light">
            <IconCircleCheck size={30} stroke={1.6} />
          </ThemeIcon>
          <Stack gap={6}>
            <Title order={2}>Email подтверждён</Title>
            <Text c="dimmed">Аккаунт активирован, открываем ваш кабинет.</Text>
          </Stack>
          <Button component={Link} to={ROLE_HOME[state.user.role]} replace>
            Перейти в кабинет
          </Button>
        </Stack>
      )}

      {state.kind === 'failed' && (
        <Stack gap="lg">
          <ThemeIcon size={56} radius="lg" color="signal" variant="light">
            <IconLinkOff size={30} stroke={1.6} />
          </ThemeIcon>
          <Stack gap={6}>
            <Title order={2}>Ссылка не сработала</Title>
            <Text c="dimmed" lh={1.6}>
              {state.message}
            </Text>
          </Stack>
          <Button component={Link} to="/auth/login">
            Войти в аккаунт
          </Button>
          <Text size="sm" ta="center">
            Нужна новая ссылка?{' '}
            <Anchor component={Link} to="/auth/check-email" fw={600}>
              Запросить письмо
            </Anchor>
          </Text>
        </Stack>
      )}
    </Paper>
  );
}
