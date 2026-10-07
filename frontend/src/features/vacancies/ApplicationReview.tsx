import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Select,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { IconLockOpen } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import type { EmployerApplication, RejectReason } from '@/api/types';
import { useApplicationActions } from '@/api/vacancies';
import { CandidateSummary } from '@/features/employer/CandidateSummary';
import { REJECT_REASON_LABELS, buildApplicationTimeline } from '@/shared/lib/applicationStatus';
import { toOptions } from '@/shared/lib/candidate';
import { formatDateTime } from '@/shared/lib/format';
import { ApplicationStatusBadge, MatchScore, StatusTimeline } from '@/shared/ui';

interface ApplicationReviewProps {
  application: EmployerApplication;
  vacancyId: string;
}

export function ApplicationReview({ application, vacancyId }: ApplicationReviewProps) {
  // Отклик в списке: карточка кандидата, балл соответствия и контакты — отклик открыл их
  // сам кандидат. Первый просмотр отмечается, и кандидат видит «просмотрен».
  const { open, decide } = useApplicationActions(vacancyId);
  const [mode, setMode] = useState<'interview' | 'rejected' | null>(null);
  const [message, setMessage] = useState('');
  const [reason, setReason] = useState<RejectReason | null>(null);
  const active = application.status === 'submitted' || application.status === 'viewed';
  const contacts = application.contacts;

  const submit = () => {
    if (!mode) return;
    decide.mutate(
      {
        applicationId: application.id,
        body: { status: mode, reject_reason: mode === 'rejected' ? reason : null, message },
      },
      { onSuccess: () => setMode(null) },
    );
  };

  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
          {application.card ? (
            <CandidateSummary card={application.card} contactsDisclosed={Boolean(contacts)} />
          ) : (
            <Text c="dimmed">Профиль кандидата недоступен</Text>
          )}
          <Group gap="sm" wrap="nowrap">
            {application.match_score !== null && application.match_score !== undefined && (
              <MatchScore score={application.match_score} size={56} />
            )}
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
        {application.cover_letter && (
          <Text size="sm" lh={1.6} style={{ whiteSpace: 'pre-line' }}>
            «{application.cover_letter}»
          </Text>
        )}
        {contacts && (
          <Group gap="sm" wrap="nowrap" align="flex-start">
            <IconLockOpen size={18} color="#0c8a6b" />
            <Text size="sm">
              <b>{contacts.full_name}</b>
              {' · '}
              {[contacts.telegram, contacts.email, contacts.phone].filter(Boolean).join(' · ')}
              <Text span size="xs" c="dimmed">
                {' '}
                — открыты откликом {formatDateTime(contacts.disclosed_at)}
              </Text>
            </Text>
          </Group>
        )}
        {application.status === 'rejected' && application.reject_reason && (
          <Badge color="gray" variant="light" tt="none">
            Отказ: {REJECT_REASON_LABELS[application.reject_reason]}
          </Badge>
        )}
        <Group gap="sm">
          {application.card && (
            <Button
              size="xs"
              variant="default"
              component={Link}
              to={`/e/candidates/${application.card.candidate_id}`}
            >
              Карточка
            </Button>
          )}
          {application.status === 'submitted' && (
            <Button
              size="xs"
              variant="light"
              loading={open.isPending}
              onClick={() => open.mutate(application.id)}
            >
              Отметить просмотренным
            </Button>
          )}
          {active && (
            <>
              <Button size="xs" onClick={() => setMode('interview')}>
                Пригласить на собеседование
              </Button>
              <Button size="xs" variant="subtle" color="signal" onClick={() => setMode('rejected')}>
                Отказать
              </Button>
            </>
          )}
        </Group>
      </Stack>
      <Modal
        opened={mode !== null}
        onClose={() => setMode(null)}
        title={mode === 'interview' ? 'Приглашение на собеседование' : 'Отказ по отклику'}
        centered
      >
        <Stack gap="md">
          {mode === 'rejected' && (
            <Select<RejectReason>
              label="Причина"
              description="Кандидат увидит её и поймёт, что подтянуть"
              data={toOptions(REJECT_REASON_LABELS)}
              value={reason}
              onChange={setReason}
              required
            />
          )}
          <Textarea
            label={mode === 'interview' ? 'Сообщение кандидату' : 'Комментарий'}
            description={
              mode === 'interview'
                ? 'Как и когда связаться. Кандидат увидит контакты компании'
                : 'Необязательно'
            }
            autosize
            minRows={2}
            maxLength={500}
            value={message}
            onChange={(event) => setMessage(event.currentTarget.value)}
          />
          {decide.isError && (
            <Alert color="signal" variant="light">
              {errorMessage(decide.error)}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setMode(null)}>
              Отмена
            </Button>
            <Button
              color={mode === 'rejected' ? 'signal' : 'fsp'}
              loading={decide.isPending}
              disabled={mode === 'rejected' && !reason}
              onClick={submit}
            >
              {mode === 'interview' ? 'Пригласить' : 'Отказать'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

export function ApplicationsSection({
  applications,
  vacancyId,
}: {
  applications: EmployerApplication[];
  vacancyId: string;
}) {
  return (
    <Stack gap="md">
      <Title order={4}>Отклики</Title>
      {applications.length === 0 ? (
        <Card>
          <Text size="sm" c="dimmed">
            Откликов пока нет. Не ждите: найдите кандидатов сами в банке или подборке и пригласите с
            вилкой.
          </Text>
        </Card>
      ) : (
        applications.map((application) => (
          <ApplicationReview key={application.id} application={application} vacancyId={vacancyId} />
        ))
      )}
    </Stack>
  );
}
