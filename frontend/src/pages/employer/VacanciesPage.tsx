import { Badge, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import type { Vacancy } from '@/api/types';
import { useEmployerVacancies } from '@/api/vacancies';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { VACANCY_STATUS_COPY } from '@/shared/lib/applicationStatus';
import { formatDate } from '@/shared/lib/format';
import { ErrorState, LoadingState, PageHeader, SalaryRange } from '@/shared/ui';

function VacancyCard({ vacancy }: { vacancy: Vacancy }) {
  const status = VACANCY_STATUS_COPY[vacancy.status];
  return (
    <Card component={Link} to={`/e/vacancies/${vacancy.id}`}>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Title order={4}>{vacancy.title}</Title>
          <Badge color={status.color} variant="light" style={{ flexShrink: 0 }}>
            {status.label}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          {vacancy.specialization.name} · {vacancy.grades.map((grade) => grade.name).join(', ')}
          {vacancy.published_at ? ` · опубликована ${formatDate(vacancy.published_at)}` : ''}
        </Text>
        <SalaryRange
          from={vacancy.salary_from}
          to={vacancy.salary_to}
          size="sm"
          caption={vacancy.salary_gross ? 'до НДФЛ' : 'на руки'}
        />
        <Group gap="xs">
          <Badge variant="dot" color={vacancy.applications_new ? 'signal' : 'gray'}>
            Новых откликов: {vacancy.applications_new}
          </Badge>
          <Badge variant="dot" color="lilac">
            Всего: {vacancy.applications_total}
          </Badge>
        </Group>
      </Stack>
    </Card>
  );
}

export function EmployerVacanciesPage() {
  const vacancies = useEmployerVacancies();
  return (
    <>
      <PageHeader
        kicker="Вакансии"
        title="Открытые вакансии компании"
        description="Дополнительный канал: кандидаты, которых вы ещё не нашли в банке, откликаются сами. Вилка обязательна, отклик сразу открывает контакты кандидата."
        actions={
          <Button component={Link} to="/e/vacancies/new" leftSection={<IconPlus size={16} />}>
            Новая вакансия
          </Button>
        }
      />
      <CompanyGate>
        {vacancies.isPending ? (
          <LoadingState />
        ) : vacancies.isError ? (
          <ErrorState
            message={errorMessage(vacancies.error)}
            onRetry={() => void vacancies.refetch()}
          />
        ) : vacancies.data.length === 0 ? (
          <Card>
            <Stack gap="sm" align="flex-start">
              <Text fw={700}>Вакансий пока нет</Text>
              <Text size="sm" c="dimmed">
                Опубликуйте вакансию с нуля или из потребности — кнопка есть на странице подборки.
              </Text>
            </Stack>
          </Card>
        ) : (
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
            {vacancies.data.map((vacancy) => (
              <VacancyCard key={vacancy.id} vacancy={vacancy} />
            ))}
          </SimpleGrid>
        )}
      </CompanyGate>
    </>
  );
}
