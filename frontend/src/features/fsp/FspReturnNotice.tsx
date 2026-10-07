import { Button, Loader, Paper, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { Link } from 'react-router';

interface FspReturnNoticeProps {
  pending: boolean;
  pendingText: string;
  error: string | null;
  backTo: string;
  backLabel: string;
}

export function FspReturnNotice({
  pending,
  pendingText,
  error,
  backTo,
  backLabel,
}: FspReturnNoticeProps) {
  // Экран возврата из ФСП ID: пока сервер проверяет ответ — ожидание, при ошибке —
  // понятная причина и путь назад.
  return (
    <Paper p={{ base: 'lg', sm: 40 }} shadow="md" maw={520} mx="auto" mt="xl">
      {pending || !error ? (
        <Stack align="center" gap="md" py="xl">
          <Loader color="fsp" />
          <Text c="dimmed">{pendingText}</Text>
        </Stack>
      ) : (
        <Stack gap="lg">
          <ThemeIcon size={56} radius="lg" color="signal" variant="light">
            <IconAlertTriangle size={30} stroke={1.6} />
          </ThemeIcon>
          <Stack gap={6}>
            <Title order={2}>ФСП ID не подтвердил вход</Title>
            <Text c="dimmed" lh={1.6}>
              {error}
            </Text>
          </Stack>
          <Button component={Link} to={backTo} replace>
            {backLabel}
          </Button>
        </Stack>
      )}
    </Paper>
  );
}
