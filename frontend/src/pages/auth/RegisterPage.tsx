import {
  Alert,
  Anchor,
  Box,
  Button,
  Checkbox,
  List,
  Paper,
  PasswordInput,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import {
  IconAlertCircle,
  IconBuildingSkyscraper,
  IconCircleCheck,
  IconCircleDashed,
  IconUserCode,
  type Icon,
} from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { ApiError, errorMessage, fieldErrors } from '@/api/errors';
import type { RegisterRequest } from '@/api/types';
import { useAuth } from '@/features/auth/useAuth';
import classes from './AuthPages.module.css';

type RegistrationRole = RegisterRequest['role'];

interface RegisterValues {
  role: RegistrationRole;
  email: string;
  password: string;
  consent: boolean;
}

const ROLE_OPTIONS: Array<{ value: RegistrationRole; title: string; text: string; icon: Icon }> = [
  {
    value: 'candidate',
    title: 'Я специалист',
    text: 'Хочу получать предложения с вилкой зарплаты',
    icon: IconUserCode,
  },
  {
    value: 'employer',
    title: 'Я работодатель',
    text: 'Ищу специалистов в команду',
    icon: IconBuildingSkyscraper,
  },
];

const PASSWORD_RULES: Array<{ label: string; test: (value: string) => boolean }> = [
  { label: 'Не короче 8 символов', test: (value) => value.length >= 8 },
  { label: 'Есть буква', test: (value) => /[A-Za-zА-Яа-яЁё]/.test(value) },
  { label: 'Есть цифра', test: (value) => /\d/.test(value) },
];

function initialRole(raw: string | null): RegistrationRole {
  return raw === 'employer' ? 'employer' : 'candidate';
}

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [failure, setFailure] = useState<string | null>(null);

  const form = useForm<RegisterValues>({
    initialValues: {
      role: initialRole(searchParams.get('role')),
      email: '',
      password: '',
      consent: false,
    },
    validate: {
      email: (value) => (/^\S+@\S+\.\S+$/.test(value.trim()) ? null : 'Укажите корректный email'),
      password: (value) =>
        PASSWORD_RULES.every((rule) => rule.test(value)) && value.trim() === value
          ? null
          : 'Пароль не соответствует требованиям',
      consent: (value) => (value ? null : 'Без согласия зарегистрироваться не получится'),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setFailure(null);
    try {
      const result = await register({
        email: values.email.trim(),
        password: values.password,
        role: values.role,
        accept_personal_data_processing: values.consent,
      });
      const params = new URLSearchParams({ email: result.email });
      if (!result.verification_email_sent) params.set('delivery', 'failed');
      navigate(`/auth/check-email?${params.toString()}`);
    } catch (error) {
      // Ошибки полей с сервера (например, занятый email) подсвечиваем прямо в форме,
      // остальное показываем общим сообщением над кнопкой.
      if (error instanceof ApiError && error.code === 'email_already_registered') {
        form.setFieldError('email', error.message);
        return;
      }
      const byField = fieldErrors(error);
      if (Object.keys(byField).length > 0) {
        form.setErrors({
          email: byField.email,
          password: byField.password,
          consent: byField.accept_personal_data_processing,
        });
        return;
      }
      setFailure(errorMessage(error));
    }
  });

  return (
    <Paper p={{ base: 'lg', sm: 40 }} shadow="md" className={classes.card}>
      <Stack gap={6} mb="xl">
        <Title order={2}>Регистрация</Title>
        <Text c="dimmed">Аккаунт активируется после подтверждения email</Text>
      </Stack>

      <form onSubmit={handleSubmit} noValidate>
        <Stack gap="md">
          <Box role="radiogroup" aria-label="Роль">
            <SimpleGrid cols={2} spacing="sm">
              {ROLE_OPTIONS.map((option) => {
                const selected = form.values.role === option.value;
                return (
                  <UnstyledButton
                    key={option.value}
                    role="radio"
                    aria-checked={selected}
                    className={classes.roleOption}
                    data-selected={selected || undefined}
                    onClick={() => form.setFieldValue('role', option.value)}
                  >
                    <ThemeIcon
                      variant={selected ? 'filled' : 'light'}
                      color="fsp"
                      radius="md"
                      size={36}
                    >
                      <option.icon size={20} stroke={1.8} />
                    </ThemeIcon>
                    <Text fw={700} size="sm" mt="sm">
                      {option.title}
                    </Text>
                    <Text size="xs" c="dimmed" lh={1.4}>
                      {option.text}
                    </Text>
                  </UnstyledButton>
                );
              })}
            </SimpleGrid>
          </Box>

          <TextInput
            label="Email"
            placeholder="you@example.com"
            autoComplete="email"
            inputMode="email"
            required
            {...form.getInputProps('email')}
          />
          <div>
            <PasswordInput
              label="Пароль"
              autoComplete="new-password"
              required
              {...form.getInputProps('password')}
            />
            <List spacing={2} size="xs" mt={8} center>
              {PASSWORD_RULES.map((rule) => {
                const passed = rule.test(form.values.password);
                return (
                  <List.Item
                    key={rule.label}
                    icon={
                      passed ? (
                        <IconCircleCheck size={14} color="#0c8a6b" />
                      ) : (
                        <IconCircleDashed size={14} color="#8f8aa1" />
                      )
                    }
                  >
                    <Text size="xs" c={passed ? 'dark' : 'dimmed'}>
                      {rule.label}
                    </Text>
                  </List.Item>
                );
              })}
            </List>
          </div>

          <Checkbox
            label={
              <Text size="sm" lh={1.45}>
                Я даю согласие на обработку персональных данных в соответствии с{' '}
                <Anchor component={Link} to="/legal/personal-data" target="_blank">
                  политикой обработки
                </Anchor>
              </Text>
            }
            {...form.getInputProps('consent', { type: 'checkbox' })}
          />

          {failure && (
            <Alert color="signal" variant="light" icon={<IconAlertCircle size={18} />}>
              {failure}
            </Alert>
          )}

          <Button type="submit" size="md" loading={form.submitting} fullWidth>
            Создать аккаунт
          </Button>
        </Stack>
      </form>

      <Text size="sm" ta="center" mt="lg">
        Уже зарегистрированы?{' '}
        <Anchor component={Link} to="/auth/login" fw={600}>
          Войти
        </Anchor>
      </Text>
    </Paper>
  );
}
