import { Alert, Button, Skeleton, Stack } from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';

export function LoadingState({ blocks = 2, height = 180 }: { blocks?: number; height?: number }) {
  return (
    <Stack gap="lg" aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: blocks }, (_, index) => (
        <Skeleton key={index} height={height} radius="lg" />
      ))}
    </Stack>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert
      color="signal"
      variant="light"
      icon={<IconAlertCircle size={18} />}
      title="Не удалось загрузить"
    >
      <Stack gap="sm" align="flex-start">
        {message}
        {onRetry && (
          <Button size="xs" variant="light" color="signal" onClick={onRetry}>
            Повторить
          </Button>
        )}
      </Stack>
    </Alert>
  );
}
