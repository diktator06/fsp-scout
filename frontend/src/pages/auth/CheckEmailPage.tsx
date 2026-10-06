import {
  Alert,
  Anchor,
  Button,
  Paper,
  Stack,
  Text,
  TextInput,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { useInterval } from '@mantine/hooks';
import { IconInbox, IconMailCheck } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useAuth } from '@/features/auth/useAuth';
import { env } from '@/shared/config/env';
import classes from './AuthPages.module.css';

const RESEND_COOLDOWN_SECONDS = 60;

export function CheckEmailPage() {
  const { resendVerification } = useAuth();
  const [searchParams] = useSearchParams();
  const emailFromLink = searchParams.get('email') ?? '';
  const [email, setEmail] = useState(emailFromLink);
  const deliveryFailed = searchParams.get('delivery') === 'failed';

  const [cooldown, setCooldown] = useState(
    deliveryFailed || !emailFromLink ? 0 : RESEND_COOLDOWN_SECONDS,
  );
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [sending, setSending] = useState(false);
  useInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000, { autoInvoke: true });

  const handleResend = async () => {
    // Пауза между отправками совпадает с лимитом на бэкенде: кнопку нельзя
    // нажимать чаще, чем сервер готов отправлять письма.
    setSending(true);
    setNotice(null);
    try {
      await resendVerification(email);
      setNotice({
        ok: true,
        text: 'Новое письмо отправлено. Предыдущая ссылка больше не действует.',
      });
      setCooldown(RESEND_COOLDOWN_SECONDS);
    } catch (error) {
      setNotice({ ok: false, text: errorMessage(error) });
    } finally {
      setSending(false);
    }
  };

  return (
    <Paper p={{ base: 'lg', sm: 40 }} shadow="md" className={classes.card}>
      <Stack gap="lg">
        <ThemeIcon size={56} radius="lg" color="fsp" variant="light">
          <IconMailCheck size={30} stroke={1.6} />
        </ThemeIcon>
        <Stack gap={6}>
          <Title order={2}>Проверьте почту</Title>
          <Text c="dimmed" lh={1.6}>
            {emailFromLink ? (
              <>
                Мы отправили ссылку для подтверждения на <b>{emailFromLink}</b>. Перейдите по ней,
                чтобы активировать аккаунт. Ссылка действует 24 часа.
              </>
            ) : (
              'Укажите email, и мы отправим новую ссылку для подтверждения. Ссылка действует 24 часа.'
            )}
          </Text>
        </Stack>

        {!emailFromLink && (
          <TextInput
            label="Email, указанный при регистрации"
            placeholder="you@example.com"
            value={email}
            onChange={(event) => setEmail(event.currentTarget.value.trim())}
            autoComplete="email"
          />
        )}

        {deliveryFailed && (
          <Alert color="signal" variant="light" title="Письмо не ушло">
            Почтовый сервер временно недоступен. Отправьте письмо повторно через минуту.
          </Alert>
        )}

        {notice && (
          <Alert color={notice.ok ? 'teal' : 'signal'} variant="light">
            {notice.text}
          </Alert>
        )}

        <Button
          variant="light"
          onClick={handleResend}
          loading={sending}
          disabled={!/^\S+@\S+\.\S+$/.test(email) || cooldown > 0}
        >
          {cooldown > 0 ? `Отправить ещё раз через ${cooldown} с` : 'Отправить письмо ещё раз'}
        </Button>

        {env.mailpitUrl && (
          <Alert variant="outline" color="lilac" icon={<IconInbox size={18} />} title="Демо-стенд">
            Письма не уходят наружу, их принимает Mailpit.{' '}
            <Anchor href={env.mailpitUrl} target="_blank" rel="noreferrer" fw={600}>
              Открыть почтовый ящик
            </Anchor>
          </Alert>
        )}

        <Text size="sm" ta="center">
          <Anchor component={Link} to="/auth/login" fw={600}>
            Вернуться ко входу
          </Anchor>
        </Text>
      </Stack>
    </Paper>
  );
}
