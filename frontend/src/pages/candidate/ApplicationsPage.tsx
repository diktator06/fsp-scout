import { Alert, Anchor, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconLockOpen } from '@tabler/icons-react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import type { CandidateApplication } from '@/api/types';
import { useMyApplications, useWithdrawApplication } from '@/api/vacancies';
import { REJECT_REASON_LABELS, buildApplicationTimeline } from '@/shared/lib/applicationStatus';
import { formatDate } from '@/shared/lib/format';
import {
  ApplicationStatusBadge,
  ErrorState,
  LoadingState,
  PageHeader,
  SalaryRange,
  StatusTimeline,
} from '@/shared/ui';

function ApplicationCard({ application }: { application: CandidateApplication }) {
  // Отклик глазами кандидата: где он сейчас, что ответила компания и как с ней связаться.
  const withdraw = useWithdrawApplication();
  const active = application.status === 'submitted' || application.status === 'viewed';
  const { vacancy } = application;
  const contacts = application.employer_contacts;
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
          <Stack gap={4}>
            <Anchor component={Link} to={`/c/vacancies/${vacancy.id}`} fw={800} size="lg">
              {vacancy.title}
            </Anchor>
            <Text size="sm" c="dimmed">
              {vacancy.company.name} · отклик от {formatDate(application.created_at)}
              {vacancy.status === 'closed' ? ' · вакансия закрыта' : ''}
            </Text>
          </Stack>
          <Group gap="md" wrap="nowrap">
            <SalaryRange
              from={vacancy.salary_from}
              to={vacancy.salary_to}
              size="sm"
              caption={vacancy.salary_gross ? 'до НДФЛ' : 'на руки'}
            />
            <ApplicationStatusBadge status={application.status} />
          </Group>
        </Group>
        <StatusTimeline
          steps={buildApplicationTimeline(application.status, {
            createdAt: application.created_at,
            viewedAt: application.viewed_at,
            respondedAt: application.responded_at,
          })}
        />
        {application.status === 'rejected' && (
          <Alert color="gray" variant="light">
            {application.reject_reason ? REJECT_REASON_LABELS[application.reject_reason] : 'Отказ'}
            {application.reject_comment ? `. ${application.reject_comment}` : ''}
          </Alert>
        )}
        {contacts && (
          <Alert
            color="teal"
            variant="light"
            icon={<IconLockOpen size={18} />}
            title="Компания приглашает на собеседование"
          >
            <Stack gap={2}>
              {application.reject_comment && <Text size="sm">{application.reject_comment}</Text>}
              {contacts.recruiter_name && (
                <Text size="sm">
                  {contacts.recruiter_name}
                  {contacts.recruiter_position ? `, ${contacts.recruiter_position}` : ''}
                </Text>
              )}
              <Text size="sm">
                {[contacts.telegram, contacts.email, contacts.phone].filter(Boolean).join(' · ')}
              </Text>
            </Stack>
          </Alert>
        )}
        {active && (
          <Group>
            <Button
              variant="subtle"
              color="gray"
              size="xs"
              loading={withdraw.isPending && withdraw.variables === application.id}
              onClick={() => withdraw.mutate(application.id)}
            >
              Отозвать отклик
            </Button>
          </Group>
        )}
      </Stack>
    </Card>
  );
}

export function ApplicationsPage() {
  const applications = useMyApplications();
  return (
    <>
      <PageHeader
        kicker="Отклики"
        title="Мои отклики"
        description="Отклик открывает компании ваши контакты. Статус меняется, когда компания открывает отклик и отвечает."
        actions={
          <Button component={Link} to="/c/vacancies" variant="light">
            К вакансиям
          </Button>
        }
      />
      {applications.isPending ? (
        <LoadingState />
      ) : applications.isError ? (
        <ErrorState
          message={errorMessage(applications.error)}
          onRetry={() => void applications.refetch()}
        />
      ) : applications.data.length === 0 ? (
        <Card>
          <Stack gap="sm" align="flex-start">
            <Title order={4}>Откликов пока нет</Title>
            <Text size="sm" c="dimmed">
              Основной путь — приглашения от компаний, но откликнуться самому тоже можно.
            </Text>
            <Button component={Link} to="/c/vacancies">
              Смотреть вакансии
            </Button>
          </Stack>
        </Card>
      ) : (
        <Stack gap="lg">
          {applications.data.map((application) => (
            <ApplicationCard key={application.id} application={application} />
          ))}
        </Stack>
      )}
    </>
  );
}
