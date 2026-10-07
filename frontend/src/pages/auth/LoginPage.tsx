import {
  Alert,
  Anchor,
  Button,
  Divider,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle, IconId, IconMailForward } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { ApiError, errorMessage } from '@/api/errors';
import { startFspLogin } from '@/api/fsp';
import { safeNextPath } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';
import { DEMO_ACCOUNTS, DEMO_PASSWORD, env } from '@/shared/config/env';
import classes from './AuthPages.module.css';

interface LoginValues {
  email: string;
  password: string;
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [fspStarting, setFspStarting] = useState(false);

  const handleFspLogin = async () => {
    // Вход через ФСП ID работает для аккаунтов, к которым ФСП ID уже привязан.
    // Браузер уходит на страницу провайдера и возвращается на /auth/fsp/callback.
    setFailure(null);
    setFspStarting(true);
    try {
      window.location.assign(await startFspLogin());
    } catch (error) {
      setFspStarting(false);
      setFailure(
        error instanceof ApiError ? error : new ApiError(0, 'unknown', errorMessage(error)),
      );
    }
  };

  const form = useForm<LoginValues>({
    initialValues: { email: '', password: '' },
    validate: {
      email: (value) => (/^\S+@\S+\.\S+$/.test(value.trim()) ? null : 'Укажите email'),
      password: (value) => (value ? null : 'Введите пароль'),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setFailure(null);
    try {
      const user = await login(values.email.trim(), values.password);
      navigate(safeNextPath(searchParams.get('next'), user.role), { replace: true });
    } catch (error) {
      // Неподтверждённый email — не ошибка ввода, а незавершённый шаг регистрации.
      // Показываем его отдельно, с кнопкой перехода к повторной отправке письма.
      setFailure(
        error instanceof ApiError ? error : new ApiError(0, 'unknown', errorMessage(error)),
      );
    }
  });

  const emailNotVerified = failure?.code === 'email_not_verified';

  return (
    <Paper p={{ base: 'lg', sm: 40 }} shadow="md" className={classes.card}>
      <Stack gap={6} mb="xl">
        <Title order={2}>Вход</Title>
        <Text c="dimmed">Рады снова видеть вас в «Скауте»</Text>
      </Stack>

      <form onSubmit={handleSubmit} noValidate>
        <Stack gap="md">
          {failure && (
            <Alert
              color={emailNotVerified ? 'lilac' : 'signal'}
              variant="light"
              icon={
                emailNotVerified ? <IconMailForward size={18} /> : <IconAlertCircle size={18} />
              }
              title={emailNotVerified ? 'Подтвердите email' : 'Не удалось войти'}
            >
              <Text size="sm">{failure.message}</Text>
              {emailNotVerified && (
                <Anchor
                  component={Link}
                  to={`/auth/check-email?email=${encodeURIComponent(form.values.email.trim())}`}
                  size="sm"
                  fw={600}
                >
                  Отправить письмо ещё раз
                </Anchor>
              )}
            </Alert>
          )}
          <TextInput
            label="Email"
            placeholder="you@example.com"
            autoComplete="email"
            inputMode="email"
            required
            {...form.getInputProps('email')}
          />
          <PasswordInput
            label="Пароль"
            autoComplete="current-password"
            required
            {...form.getInputProps('password')}
          />
          <Button type="submit" size="md" loading={form.submitting} fullWidth mt="xs">
            Войти
          </Button>
          <Divider label="или" labelPosition="center" />
          <Button
            variant="default"
            size="md"
            fullWidth
            leftSection={<IconId size={18} />}
            loading={fspStarting}
            onClick={() => void handleFspLogin()}
          >
            Войти через ФСП ID
          </Button>
          <Text size="xs" c="dimmed" ta="center" mt={-6}>
            Для аккаунтов, к которым привязан ФСП ID участника соревнований
          </Text>
        </Stack>
      </form>

      <Text size="sm" ta="center" mt="lg">
        Нет аккаунта?{' '}
        <Anchor component={Link} to="/auth/register" fw={600}>
          Зарегистрироваться
        </Anchor>
      </Text>

      {env.showDemoAccounts && (
        <>
          <Divider my="xl" label="Демо-доступ для проверки" labelPosition="center" />
          <Group gap="xs" grow>
            {DEMO_ACCOUNTS.map((account) => (
              <UnstyledButton
                key={account.email}
                className={classes.demoAccount}
                onClick={() => form.setValues({ email: account.email, password: DEMO_PASSWORD })}
              >
                <Text size="sm" fw={700}>
                  {account.label}
                </Text>
                <Text size="xs" c="dimmed" truncate>
                  {account.email}
                </Text>
              </UnstyledButton>
            ))}
          </Group>
        </>
      )}
    </Paper>
  );
}
