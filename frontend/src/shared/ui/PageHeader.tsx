import { Group, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';
import { Kicker } from './Kicker';

interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  kicker?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, description, kicker, actions }: PageHeaderProps) {
  return (
    <Group justify="space-between" align="flex-end" gap="lg" mb="xl" wrap="wrap">
      <Stack gap={8} maw={760}>
        {kicker && <Kicker>{kicker}</Kicker>}
        <Title order={2}>{title}</Title>
        {description && (
          <Text c="dimmed" size="md" lh={1.55}>
            {description}
          </Text>
        )}
      </Stack>
      {actions && <Group gap="sm">{actions}</Group>}
    </Group>
  );
}
