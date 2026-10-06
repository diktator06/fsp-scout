import { Anchor, Badge, Button, Card, Group, Stack, Table, Text, Title } from '@mantine/core';
import { IconClipboardList } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useAssessmentHistory, useEligibility } from '@/api/assessment';
import { useCandidateStatus } from '@/api/candidate';
import { errorMessage } from '@/api/errors';
import type { AssessmentHistory, CandidateStatus } from '@/api/types';
import { GradeLauncher } from '@/features/assessment/GradeLauncher';
import { MODE_LABELS, OUTCOME_COPY } from '@/shared/lib/assessment';
import { GRADE_STATUS_COPY } from '@/shared/lib/candidate';
import { formatDateTime } from '@/shared/lib/format';
import { CategoryBadge, ErrorState, LoadingState, PageHeader } from '@/shared/ui';

const SESSION_STATUS_LABELS = {
  in_progress: 'идёт',
  completed: 'завершён',
  abandoned: 'прерван',
  expired: 'истёк',
} as const;

const CHANGE_REASONS = {
  initial: 'первая категория',
  upgrade: 'повышение',
  downgrade_voluntary: 'понижение по желанию',
  accepted_lower: 'принят уровень ниже',
} as const;

function CurrentCategory({ status }: { status: CandidateStatus }) {
  const copy = GRADE_STATUS_COPY[status.grade_status];
  const category = status.category ?? status.claimed_category;
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Title order={4}>Ваша категория</Title>
          <Badge color={copy.color} variant="light">
            {copy.label}
          </Badge>
        </Group>
        {category ? (
          <CategoryBadge
            specialization={category.specialization.name}
            grade={category.grade.code}
            gradeLabel={category.grade.name}
            unconfirmed={status.grade_status !== 'confirmed'}
          />
        ) : (
          <Text c="dimmed" size="sm">
            Категории пока нет. Пройдите опрос — он займёт пару минут.
          </Text>
        )}
        <Text size="sm" c="dimmed" lh={1.6}>
          {status.grade_status === 'confirmed'
            ? 'Подтверждённая категория — главный фильтр работодателей. Повысить её можно тестом на следующий уровень.'
            : 'Заявленный грейд виден работодателям с пометкой «не подтверждён» и ниже в выдаче. Тест это исправит.'}
        </Text>
      </Stack>
    </Card>
  );
}

function History({ history }: { history: AssessmentHistory }) {
  if (history.sessions.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        Попыток пока не было.
      </Text>
    );
  }
  return (
    <Stack gap="lg">
      <Table.ScrollContainer minWidth={460}>
        <Table verticalSpacing="sm" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Дата</Table.Th>
              <Table.Th>Тест</Table.Th>
              <Table.Th>Итог</Table.Th>
              <Table.Th ta="right">Заданий</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history.sessions.map((session) => (
              <Table.Tr key={session.id}>
                <Table.Td style={{ whiteSpace: 'nowrap' }}>
                  <Anchor component={Link} to={`/c/assessment/sessions/${session.id}`} size="sm">
                    {formatDateTime(session.started_at)}
                  </Anchor>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" fw={600}>
                    {session.specialization.name} · {session.target_grade.name}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {MODE_LABELS[session.mode]}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {session.outcome ? (
                    <Badge
                      color={OUTCOME_COPY[session.outcome].color}
                      variant="light"
                      style={{ flexShrink: 0, maxWidth: 'none' }}
                    >
                      {OUTCOME_COPY[session.outcome].short}
                    </Badge>
                  ) : (
                    <Text size="sm" c="dimmed">
                      {SESSION_STATUS_LABELS[session.status]}
                    </Text>
                  )}
                </Table.Td>
                <Table.Td ta="right" className="tabular">
                  {session.items_scored}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {history.grade_changes.length > 0 && (
        <Stack gap={6}>
          <Text fw={700} size="sm">
            Изменения категории
          </Text>
          {history.grade_changes.map((change) => (
            <Group key={`${change.changed_at}-${change.category.id}`} gap="sm" wrap="wrap">
              <Text size="sm" c="dimmed" className="tabular" miw={110}>
                {formatDateTime(change.changed_at)}
              </Text>
              <Text size="sm" fw={600}>
                {change.category.title}
              </Text>
              <Text size="sm" c="dimmed">
                {CHANGE_REASONS[change.reason]}
              </Text>
            </Group>
          ))}
        </Stack>
      )}
    </Stack>
  );
}

export function AssessmentPage() {
  // Всё о категории в одном месте: что есть сейчас, какие тесты доступны
  // и почему другие закрыты, и история попыток.
  const status = useCandidateStatus();
  const eligibility = useEligibility();
  const history = useAssessmentHistory();

  const header = (
    <PageHeader
      kicker="Категория и тест"
      title="Подтверждение уровня"
      description="Категория = специализация + грейд. Её присваивает только адаптивный тест; опрос задаёт его состав."
      actions={
        <Button component={Link} to="/c/onboarding?step=survey" variant="default">
          Изменить опрос
        </Button>
      }
    />
  );

  if (status.isPending || eligibility.isPending) {
    return (
      <>
        {header}
        <LoadingState />
      </>
    );
  }
  const failed = status.error ?? eligibility.error;
  if (failed || !status.data || !eligibility.data) {
    return (
      <>
        {header}
        <ErrorState message={errorMessage(failed)} onRetry={() => void eligibility.refetch()} />
      </>
    );
  }

  return (
    <>
      {header}
      <Stack gap="lg">
        <CurrentCategory status={status.data} />
        <Card>
          <Stack gap="lg">
            <Title order={4}>Новый тест</Title>
            {eligibility.data.survey ? (
              <GradeLauncher eligibility={eligibility.data} />
            ) : (
              <Group gap="md" wrap="wrap">
                <IconClipboardList size={28} color="#520978" />
                <Text size="sm" c="dimmed" maw={520}>
                  Чтобы собрать тест, нужен опрос: специализация, стек и опыт.
                </Text>
                <Button component={Link} to="/c/onboarding">
                  Пройти опрос
                </Button>
              </Group>
            )}
          </Stack>
        </Card>
        <Card>
          <Stack gap="md">
            <Title order={4}>История</Title>
            {history.data ? (
              <History history={history.data} />
            ) : history.isError ? (
              <ErrorState
                message={errorMessage(history.error)}
                onRetry={() => void history.refetch()}
              />
            ) : (
              <LoadingState blocks={1} height={120} />
            )}
          </Stack>
        </Card>
      </Stack>
    </>
  );
}
