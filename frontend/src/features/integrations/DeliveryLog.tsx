import {
  Badge,
  Button,
  Card,
  Code,
  Collapse,
  Group,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { IconChevronDown, IconChevronRight, IconRefresh } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useRetryDelivery } from '@/api/integrations';
import type { WebhookDelivery, WebhookEventInfo } from '@/api/types';
import { formatDateTime } from '@/shared/lib/format';
import { DELIVERY_STATUS_COPY, PING_LABEL, responseSummary } from '@/shared/lib/integrations';

function DeliveryItem({ delivery, title }: { delivery: WebhookDelivery; title: string }) {
  // Тело события раскрывается по клику: по нему удобно настраивать разбор в ATS.
  const [opened, setOpened] = useState(false);
  const retry = useRetryDelivery();
  const status = DELIVERY_STATUS_COPY[delivery.status];
  const outcome = responseSummary(delivery.response_body, delivery.error);
  return (
    <Card padding="md">
      <Stack gap={6}>
        <Group justify="space-between" wrap="nowrap" align="flex-start" gap="sm">
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Text fw={600}>{title}</Text>
            <Text size="xs" c="dimmed" style={{ wordBreak: 'break-all' }}>
              {formatDateTime(delivery.created_at)} · {delivery.endpoint_url}
            </Text>
          </Stack>
          <Badge color={status.color} variant="light" style={{ flexShrink: 0 }}>
            {status.label}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          Попыток: {delivery.attempts} из {delivery.max_attempts}
          {delivery.response_status !== null && ` · ответ ${delivery.response_status}`}
          {delivery.next_attempt_at &&
            delivery.attempts > 0 &&
            ` · следующая попытка ${formatDateTime(delivery.next_attempt_at)}`}
        </Text>
        {outcome && (
          <Text size="sm" style={{ wordBreak: 'break-word' }}>
            {outcome}
          </Text>
        )}
        <Group gap="xs" justify="space-between">
          <UnstyledButton onClick={() => setOpened((value) => !value)}>
            <Group gap={4}>
              {opened ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
              <Text size="xs" c="fsp.8" fw={600}>
                Тело события
              </Text>
            </Group>
          </UnstyledButton>
          {delivery.status === 'failed' && (
            <Button
              size="xs"
              variant="light"
              leftSection={<IconRefresh size={14} />}
              loading={retry.isPending}
              onClick={() => retry.mutate(delivery.id)}
            >
              Повторить
            </Button>
          )}
        </Group>
        {retry.isError && (
          <Text size="sm" c="signal.8">
            {errorMessage(retry.error)}
          </Text>
        )}
        <Collapse expanded={opened}>
          <Code block style={{ maxHeight: 320, overflow: 'auto', fontSize: 12 }}>
            {JSON.stringify(delivery.payload, null, 2)}
          </Code>
        </Collapse>
      </Stack>
    </Card>
  );
}

export function DeliveryLog({
  deliveries,
  catalog,
}: {
  deliveries: WebhookDelivery[];
  catalog: WebhookEventInfo[];
}) {
  const titles = new Map<string, string>(catalog.map((item) => [item.type, item.title]));
  if (!deliveries.length) {
    return (
      <Text size="sm" c="dimmed">
        Событий пока не было. Нажмите «Проверить связь» у получателя или дождитесь, когда кандидат
        примет приглашение.
      </Text>
    );
  }
  return (
    <Stack gap="sm">
      {deliveries.map((item) => (
        <DeliveryItem
          key={item.id}
          delivery={item}
          title={
            item.event_type === 'ping'
              ? PING_LABEL
              : (titles.get(item.event_type) ?? item.event_type)
          }
        />
      ))}
    </Stack>
  );
}
