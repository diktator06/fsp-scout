import { Badge, Button, Card, Group, SimpleGrid, Stack, Text } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useNeeds } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import type { Need } from '@/api/types';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { ErrorState, LoadingState, PageHeader, SalaryRange } from '@/shared/ui';
import classes from './NeedsPage.module.css';

export function NeedCard({ need }: { need: Need }) {
  return (
    <Card component={Link} to={`/e/needs/${need.id}`} className={classes.card}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start" wrap="nowrap">
          <Text fw={800} lh={1.3}>
            {need.title}
          </Text>
          {need.status === 'closed' && (
            <Badge color="gray" variant="light">
              закрыта
            </Badge>
          )}
        </Group>
        <Text size="sm" c="dimmed">
          {need.specialization.name} · {need.grades.map((grade) => grade.name).join(', ')}
        </Text>
        <SalaryRange from={need.salary_from} to={need.salary_to} size="sm" compact />
        <Group gap={6}>
          {need.skills.slice(0, 5).map((item) => (
            <Badge
              key={item.skill.id}
              variant={item.importance === 'must' ? 'light' : 'outline'}
              color="fsp"
              tt="none"
            >
              {item.skill.name}
            </Badge>
          ))}
        </Group>
        <Text size="xs" c="dimmed">
          Версий подборки: {need.latest_version} · приглашений: {need.invitations_sent}
        </Text>
      </Stack>
    </Card>
  );
}

export function NeedsPage() {
  const needs = useNeeds();
  return (
    <>
      <PageHeader
        kicker="Подборки"
        title="Потребности"
        description="Каждая потребность — это подборка кандидатов с объяснением, почему они подходят."
        actions={
          <Button component={Link} to="/e/needs/new" leftSection={<IconPlus size={16} />}>
            Новая потребность
          </Button>
        }
      />
      <CompanyGate>
        {needs.isPending ? (
          <LoadingState />
        ) : needs.isError ? (
          <ErrorState message={errorMessage(needs.error)} onRetry={() => void needs.refetch()} />
        ) : needs.data.length === 0 ? (
          <Card>
            <Stack gap="sm" align="flex-start">
              <Text fw={700}>Пока ни одной потребности</Text>
              <Text c="dimmed" size="sm">
                Опишите, кого ищете, обычным текстом — система разберёт стек, грейд и вилку.
              </Text>
              <Button component={Link} to="/e/needs/new">
                Описать потребность
              </Button>
            </Stack>
          </Card>
        ) : (
          <SimpleGrid type="container" cols={{ base: 1, '640px': 2, '1150px': 3 }} spacing="lg">
            {needs.data.map((need) => (
              <NeedCard key={need.id} need={need} />
            ))}
          </SimpleGrid>
        )}
      </CompanyGate>
    </>
  );
}
