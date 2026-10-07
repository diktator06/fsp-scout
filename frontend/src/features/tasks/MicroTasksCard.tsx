import { Badge, Card, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconPuzzle } from '@tabler/icons-react';
import type { CandidateCard } from '@/api/types';
import { formatDate } from '@/shared/lib/format';
import { TASK_KIND_LABELS, scoreOutOfFive } from '@/shared/lib/tasks';

export function MicroTasksCard({ summary }: { summary: CandidateCard['micro_tasks'] }) {
  // Свежий сигнал о кандидате: последние микрозадачи и фактор актуальности M.
  // Без задач — нейтральная справка: отсутствие задач не штрафуется.
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <ThemeIcon color={summary.count ? 'fsp' : 'gray'} variant="light" radius="md" size={36}>
              <IconPuzzle size={20} />
            </ThemeIcon>
            <Title order={4}>Микрозадачи</Title>
          </Group>
          {summary.count > 0 && (
            <Badge color="fsp" variant="light">
              Актуальность {Math.round(summary.score * 100)}%
            </Badge>
          )}
        </Group>
        {summary.count === 0 ? (
          <Text size="sm" c="dimmed">
            Микрозадач пока не было — фактор актуальности не добавляет баллов, это не штраф.
          </Text>
        ) : (
          <Stack gap="xs">
            {summary.recent.map((item) => (
              <Group key={`${item.title}-${item.graded_at}`} justify="space-between" wrap="nowrap">
                <Stack gap={0} style={{ minWidth: 0 }}>
                  <Text size="sm" fw={600} truncate>
                    {item.title}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {TASK_KIND_LABELS[item.kind]} · {formatDate(item.graded_at)}
                  </Text>
                </Stack>
                <Badge color={item.score >= 0.6 ? 'teal' : 'gray'} variant="light">
                  {scoreOutOfFive(item.score)}
                </Badge>
              </Group>
            ))}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
