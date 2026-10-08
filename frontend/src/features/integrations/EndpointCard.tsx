import { Alert, Badge, Button, Card, Group, Stack, Switch, Text } from '@mantine/core';
import { IconKey, IconSend, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useWebhookActions } from '@/api/integrations';
import type { WebhookEndpoint, WebhookEndpointWithSecret, WebhookEventInfo } from '@/api/types';

interface EndpointCardProps {
  endpoint: WebhookEndpoint;
  catalog: WebhookEventInfo[];
  onSecret: (endpoint: WebhookEndpointWithSecret) => void;
}

export function EndpointCard({ endpoint, catalog, onSecret }: EndpointCardProps) {
  // Удаление — в два нажатия: вместе с получателем пропадает журнал его доставок.
  const { update, rotate, test, remove } = useWebhookActions(endpoint.id);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const titles = new Map(catalog.map((item) => [item.type, item.title]));
  const failure = update.error ?? rotate.error ?? test.error ?? remove.error;
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" align="flex-start" gap="sm">
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Group gap="xs">
              <Text fw={700}>{endpoint.description || 'Получатель вебхуков'}</Text>
              {endpoint.is_sandbox && (
                <Badge color="lilac" variant="light" size="sm">
                  песочница
                </Badge>
              )}
            </Group>
            <Text size="sm" c="dimmed" ff="monospace" style={{ wordBreak: 'break-all' }}>
              {endpoint.url}
            </Text>
          </Stack>
          <Switch
            aria-label="Получатель включён"
            checked={endpoint.is_active}
            disabled={update.isPending}
            onChange={(event) => update.mutate({ is_active: event.currentTarget.checked })}
          />
        </Group>
        <Group gap={6}>
          {endpoint.events.map((event) => (
            <Badge key={event} variant="outline" color="fsp" tt="none">
              {titles.get(event) ?? event}
            </Badge>
          ))}
        </Group>
        <Text size="xs" c="dimmed">
          Секрет подписи: <span className="tabular">{endpoint.secret_hint}</span>
        </Text>
        {failure && (
          <Alert color="signal" variant="light">
            {errorMessage(failure)}
          </Alert>
        )}
        <Group gap="xs">
          <Button
            size="xs"
            variant="light"
            leftSection={<IconSend size={14} />}
            loading={test.isPending}
            disabled={!endpoint.is_active}
            onClick={() => test.mutate()}
          >
            Проверить связь
          </Button>
          <Button
            size="xs"
            variant="default"
            leftSection={<IconKey size={14} />}
            loading={rotate.isPending}
            onClick={() => rotate.mutate(undefined, { onSuccess: onSecret })}
          >
            Сменить секрет
          </Button>
          <Button
            size="xs"
            variant={confirmDelete ? 'filled' : 'subtle'}
            color={confirmDelete ? 'signal' : 'gray'}
            leftSection={<IconTrash size={14} />}
            loading={remove.isPending}
            onClick={() => (confirmDelete ? remove.mutate() : setConfirmDelete(true))}
            onBlur={() => setConfirmDelete(false)}
          >
            {confirmDelete ? 'Точно отключить?' : 'Отключить'}
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
