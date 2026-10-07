import { Alert, Badge, Button, Card, Group, Stack, Text, Textarea } from '@mantine/core';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useResolveComplaint } from '@/api/trust';
import type { ModerationComplaint } from '@/api/types';
import { formatDateTime } from '@/shared/lib/format';
import { COMPLAINT_REASON_LABELS, COMPLAINT_STATUS_COPY } from '@/shared/lib/trust';

export function ComplaintCard({ complaint }: { complaint: ModerationComplaint }) {
  // Подтверждённая жалоба попадает в репутацию компании, отклонённая — нет.
  // Комментарий модератора видит автор жалобы.
  const resolve = useResolveComplaint();
  const [note, setNote] = useState('');
  const status = COMPLAINT_STATUS_COPY[complaint.status];
  const decide = (decision: 'confirmed' | 'rejected') =>
    resolve.mutate({ complaintId: complaint.id, status: decision, note: note.trim() });
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" gap="sm" align="flex-start">
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Text fw={700}>{COMPLAINT_REASON_LABELS[complaint.reason]}</Text>
            <Text size="sm" c="dimmed">
              {complaint.target_title}
            </Text>
          </Stack>
          <Badge color={status.color} variant="light" style={{ flexShrink: 0 }}>
            {status.label}
          </Badge>
        </Group>
        <Group gap="xs" wrap="wrap">
          <Text size="sm" fw={600}>
            «{complaint.company.name}»
          </Text>
          {complaint.company.inn && (
            <Text size="sm" c="dimmed" ff="monospace">
              ИНН {complaint.company.inn}
            </Text>
          )}
          {complaint.company.restricted_at && (
            <Badge color="signal" variant="outline" size="sm">
              ограничена
            </Badge>
          )}
        </Group>
        {complaint.comment && (
          <Text size="sm" lh={1.6} style={{ whiteSpace: 'pre-line' }}>
            «{complaint.comment}»
          </Text>
        )}
        <Text size="xs" c="dimmed">
          Автор: {complaint.author_alias ? `кандидат ${complaint.author_alias}` : 'кандидат'} ·{' '}
          {formatDateTime(complaint.created_at)}
        </Text>
        {complaint.status === 'open' ? (
          <Stack gap="xs">
            <Textarea
              placeholder="Комментарий к решению — его увидит автор жалобы"
              autosize
              minRows={2}
              maxLength={1000}
              value={note}
              onChange={(event) => setNote(event.currentTarget.value)}
            />
            {resolve.isError && (
              <Alert color="signal" variant="light">
                {errorMessage(resolve.error)}
              </Alert>
            )}
            <Group gap="sm">
              <Button
                color="signal"
                loading={resolve.isPending && resolve.variables?.status === 'confirmed'}
                disabled={resolve.isPending}
                onClick={() => decide('confirmed')}
              >
                Подтвердить
              </Button>
              <Button
                variant="default"
                loading={resolve.isPending && resolve.variables?.status === 'rejected'}
                disabled={resolve.isPending}
                onClick={() => decide('rejected')}
              >
                Отклонить
              </Button>
            </Group>
          </Stack>
        ) : (
          complaint.resolution_note && (
            <Text size="sm">
              <b>Решение:</b> {complaint.resolution_note}
            </Text>
          )
        )}
      </Stack>
    </Card>
  );
}
