import { Badge, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconEdit, IconEyeOff, IconSend } from '@tabler/icons-react';
import { Link, useParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useEmployerVacancy, useVacancyApplications, useVacancyPublication } from '@/api/vacancies';
import { ApplicationsSection } from '@/features/vacancies/ApplicationReview';
import { VACANCY_STATUS_COPY } from '@/shared/lib/applicationStatus';
import { WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import { ErrorState, LoadingState, PageHeader, SalaryRange } from '@/shared/ui';
import classes from '../candidate/InvitationPage.module.css';

export function EmployerVacancyPage() {
  const { vacancyId = '' } = useParams();
  const vacancy = useEmployerVacancy(vacancyId);
  const applications = useVacancyApplications(vacancyId);
  const publication = useVacancyPublication(vacancyId);
  if (vacancy.isPending) return <LoadingState />;
  if (vacancy.isError) {
    return (
      <ErrorState message={errorMessage(vacancy.error)} onRetry={() => void vacancy.refetch()} />
    );
  }
  const data = vacancy.data;
  const status = VACANCY_STATUS_COPY[data.status];
  return (
    <>
      <PageHeader
        kicker="Вакансия"
        title={data.title}
        actions={
          <Group gap="sm">
            {data.status !== 'closed' && (
              <Button
                component={Link}
                to={`/e/vacancies/${data.id}/edit`}
                variant="default"
                leftSection={<IconEdit size={16} />}
              >
                Изменить
              </Button>
            )}
            {data.status === 'published' ? (
              <Button
                variant="subtle"
                color="gray"
                leftSection={<IconEyeOff size={16} />}
                loading={publication.isPending}
                onClick={() => publication.mutate('close')}
              >
                Снять с публикации
              </Button>
            ) : (
              <Button
                leftSection={<IconSend size={16} />}
                loading={publication.isPending}
                onClick={() => publication.mutate('publish')}
              >
                Опубликовать
              </Button>
            )}
          </Group>
        }
      />
      {publication.isError && (
        <Text c="signal.8" size="sm" mb="md">
          {errorMessage(publication.error)}
        </Text>
      )}
      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="lg" mb="lg">
        <Card className={classes.offer}>
          <Stack gap="sm">
            <Group justify="space-between">
              <Text size="sm" c="dimmed">
                {data.specialization.name} · {data.grades.map((grade) => grade.name).join(', ')} ·{' '}
                {data.work_formats.map((item) => WORK_FORMAT_LABELS[item]).join(', ')}
                {data.city ? ` · ${data.city}` : ''}
              </Text>
              <Badge color={status.color} variant="light">
                {status.label}
              </Badge>
            </Group>
            <Text lh={1.65} style={{ whiteSpace: 'pre-line' }}>
              {data.description}
            </Text>
            <Group gap={6}>
              {data.skills.map((item) => (
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
          </Stack>
        </Card>
        <Card>
          <Stack gap="md">
            <Title order={4}>Условия</Title>
            <SalaryRange
              from={data.salary_from}
              to={data.salary_to}
              caption={data.salary_gross ? 'до вычета НДФЛ' : 'на руки'}
            />
            <Group gap="xs">
              <Badge variant="dot" color={data.applications_new ? 'signal' : 'gray'}>
                Новых: {data.applications_new}
              </Badge>
              <Badge variant="dot" color="lilac">
                Всего откликов: {data.applications_total}
              </Badge>
            </Group>
          </Stack>
        </Card>
      </SimpleGrid>
      {applications.isPending ? (
        <LoadingState blocks={2} height={140} />
      ) : applications.isError ? (
        <ErrorState
          message={errorMessage(applications.error)}
          onRetry={() => void applications.refetch()}
        />
      ) : (
        <ApplicationsSection applications={applications.data} vacancyId={vacancyId} />
      )}
    </>
  );
}
