import { Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconPlus, IconUsersGroup } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useEmployerDashboard, useEmployerProfile, useNeeds } from '@/api/employer';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { RestrictionBanner } from '@/features/trust/RestrictionBanner';
import { INVITATION_STATUS_LABELS } from '@/shared/lib/invitationStatus';
import { LoadingState, PageHeader } from '@/shared/ui';
import { NeedCard } from './NeedsPage';
import classes from './EmployerHomePage.module.css';

const FUNNEL = ['sent', 'viewed', 'accepted', 'declined'] as const;

function Dashboard() {
  // Сводка: сколько приглашений на каком шаге, сколько контактов получено и сколько
  // приглашений ещё можно отправить сегодня.
  const dashboard = useEmployerDashboard();
  const needs = useNeeds();
  if (!dashboard.data || !needs.data) return <LoadingState />;
  const active = needs.data.filter((need) => need.status === 'active');
  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, sm: 3, xl: 5 }} spacing="md">
        {FUNNEL.map((status) => (
          <Card key={status} padding="lg" className={classes.stat}>
            <Text size="xs" c="dimmed" fw={700} tt="uppercase">
              {INVITATION_STATUS_LABELS[status]}
            </Text>
            <Text className={classes.value}>{dashboard.data.invitations[status] ?? 0}</Text>
          </Card>
        ))}
        <Card padding="lg" className={classes.stat} data-accent>
          <Text size="xs" fw={700} tt="uppercase">
            Осталось приглашений сегодня
          </Text>
          <Text className={classes.value}>
            {dashboard.data.quota.remaining}
            <span className={classes.of}> из {dashboard.data.quota.daily_limit}</span>
          </Text>
        </Card>
      </SimpleGrid>
      <Group justify="space-between">
        <Title order={4}>Активные потребности</Title>
        <Button component={Link} to="/e/needs/new" leftSection={<IconPlus size={16} />}>
          Новая потребность
        </Button>
      </Group>
      {active.length === 0 ? (
        <Card>
          <Text c="dimmed">
            Опишите первую потребность — подборка с объяснениями появится сразу после сохранения.
          </Text>
        </Card>
      ) : (
        <SimpleGrid type="container" cols={{ base: 1, '640px': 2, '1150px': 3 }} spacing="lg">
          {active.map((need) => (
            <NeedCard key={need.id} need={need} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

export function EmployerHomePage() {
  const profile = useEmployerProfile();
  return (
    <>
      <PageHeader
        kicker="Кабинет работодателя"
        title={
          profile.data?.company ? profile.data.company.name : 'Найдите специалиста по результату'
        }
        description="Опишите потребность — система предложит категории и кандидатов с объяснением, почему они подходят. Приглашение уходит конкретному человеку с обязательной вилкой."
        actions={
          <Button
            variant="default"
            component={Link}
            to="/e/bank"
            leftSection={<IconUsersGroup size={16} />}
          >
            Банк кандидатов
          </Button>
        }
      />
      <RestrictionBanner />
      <CompanyGate>
        <Dashboard />
      </CompanyGate>
    </>
  );
}
