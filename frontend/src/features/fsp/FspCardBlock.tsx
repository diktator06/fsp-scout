import { Badge, Card, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconCircleCheck, IconTrophy } from '@tabler/icons-react';
import type { FspSummary } from '@/api/types';
import { FSP_STATE_LABELS } from '@/shared/lib/fsp';
import { formatDateTime } from '@/shared/lib/format';
import { FspAchievementList } from './FspAchievementList';

interface FspCardBlockProps {
  fsp: FspSummary;
}

export function FspCardBlock({ fsp }: FspCardBlockProps) {
  // Блок ФСП в карточке для работодателя. Без привязки, без истории или со скрытыми
  // достижениями это нейтральная справка, а не минус: такой кандидат просто не получает
  // бонуса к индексу.
  const linked = fsp.state === 'linked';
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <ThemeIcon color={linked ? 'fsp' : 'gray'} variant="light" radius="md" size={36}>
              <IconTrophy size={20} />
            </ThemeIcon>
            <Title order={4}>Достижения ФСП</Title>
          </Group>
          <Badge
            color={linked ? 'teal' : 'gray'}
            variant="light"
            leftSection={linked ? <IconCircleCheck size={12} /> : undefined}
          >
            {FSP_STATE_LABELS[fsp.state]}
          </Badge>
        </Group>
        {linked ? (
          <>
            <Stack gap={4}>
              {fsp.summary && <Text fw={700}>{fsp.summary}</Text>}
              {fsp.best_result && (
                <Text size="sm">
                  Лучший результат: <b>{fsp.best_result}</b>
                </Text>
              )}
              <Text size="sm" c="dimmed">
                {[
                  fsp.sport_rank ? `Разряд: ${fsp.sport_rank}` : null,
                  `Балл ФСП ${Math.round(fsp.score * 100)}%`,
                  fsp.synced_at ? `реестр сверен ${formatDateTime(fsp.synced_at)}` : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            </Stack>
            <FspAchievementList items={fsp.achievements} limit={6} />
          </>
        ) : (
          <Text size="sm" c="dimmed" lh={1.6}>
            {fsp.message}
            {fsp.state === 'linked_empty' && fsp.sport_rank ? ` Разряд: ${fsp.sport_rank}.` : ''}
          </Text>
        )}
      </Stack>
    </Card>
  );
}
