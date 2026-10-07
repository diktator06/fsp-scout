import { Card, SegmentedControl, SimpleGrid, Stack, Tabs, Text, Title } from '@mantine/core';
import { IconBuildingSkyscraper, IconFlag } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useModerationComplaints, useModerationCompanies } from '@/api/trust';
import type { ComplaintStatus } from '@/api/types';
import { CompanyModerationCard } from '@/features/moderation/CompanyModerationCard';
import { ComplaintCard } from '@/features/moderation/ComplaintCard';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

function ComplaintsTab() {
  const [status, setStatus] = useState<ComplaintStatus | 'all'>('open');
  const complaints = useModerationComplaints(status === 'all' ? null : status);
  return (
    <Stack gap="md">
      <SegmentedControl
        value={status}
        onChange={(value) => setStatus(value as ComplaintStatus | 'all')}
        data={[
          { value: 'open', label: 'Ждут решения' },
          { value: 'confirmed', label: 'Подтверждённые' },
          { value: 'rejected', label: 'Отклонённые' },
          { value: 'all', label: 'Все' },
        ]}
        style={{ alignSelf: 'flex-start', maxWidth: '100%' }}
      />
      {complaints.isPending ? (
        <LoadingState blocks={2} height={180} />
      ) : complaints.isError ? (
        <ErrorState
          message={errorMessage(complaints.error)}
          onRetry={() => void complaints.refetch()}
        />
      ) : complaints.data.length === 0 ? (
        <Card>
          <Stack gap="xs">
            <Title order={4}>Жалоб нет</Title>
            <Text size="sm" c="dimmed">
              Когда кандидат пожалуется на приглашение, вакансию или компанию, жалоба появится
              здесь.
            </Text>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
          {complaints.data.map((item) => (
            <ComplaintCard key={item.id} complaint={item} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}

function CompaniesTab() {
  const companies = useModerationCompanies();
  if (companies.isPending) return <LoadingState blocks={2} height={180} />;
  if (companies.isError) {
    return (
      <ErrorState
        message={errorMessage(companies.error)}
        onRetry={() => void companies.refetch()}
      />
    );
  }
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        Выше — ограниченные, с открытыми жалобами и с вилками в разы выше рынка.
      </Text>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
        {companies.data.map((item) => (
          <CompanyModerationCard key={item.id} company={item} />
        ))}
      </SimpleGrid>
    </Stack>
  );
}

export function ModerationPage() {
  return (
    <>
      <PageHeader
        kicker="Модерация"
        title="Жалобы и работодатели"
        description="Три жалобы разных кандидатов за 30 дней ставят компанию на проверку автоматически. Здесь решается, подтвердить жалобу, снять ограничение или сменить уровень доверия."
      />
      <Tabs defaultValue="complaints" keepMounted={false}>
        <Tabs.List mb="lg">
          <Tabs.Tab value="complaints" leftSection={<IconFlag size={16} />}>
            Жалобы
          </Tabs.Tab>
          <Tabs.Tab value="companies" leftSection={<IconBuildingSkyscraper size={16} />}>
            Компании
          </Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="complaints">
          <ComplaintsTab />
        </Tabs.Panel>
        <Tabs.Panel value="companies">
          <CompaniesTab />
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
