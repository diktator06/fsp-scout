import { Badge, Card, Group, SimpleGrid, Stack, Text } from '@mantine/core';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useCandidateInvitations } from '@/api/invitations';
import { formatDate } from '@/shared/lib/format';
import {
  ErrorState,
  InvitationStatusBadge,
  LoadingState,
  PageHeader,
  SalaryRange,
} from '@/shared/ui';
import classes from './InvitationsPage.module.css';

export function CandidateInvitationsPage() {
  // Входящие: зарплата и компания видны сразу, ещё до того как человек откроет
  // приглашение. Непросмотренные выделены.
  const invitations = useCandidateInvitations();
  return (
    <>
      <PageHeader
        kicker="Приглашения"
        title="Компании, которые вас нашли"
        description="Компания видит только обезличенную карточку. Ваши контакты откроются ей, если вы примете приглашение."
      />
      {invitations.isPending ? (
        <LoadingState blocks={2} height={150} />
      ) : invitations.isError ? (
        <ErrorState
          message={errorMessage(invitations.error)}
          onRetry={() => void invitations.refetch()}
        />
      ) : invitations.data.length === 0 ? (
        <Card>
          <Text c="dimmed">
            Приглашений пока нет. Они появятся, когда работодатель найдёт вас в банке кандидатов, —
            проверьте, что профиль опубликован в разделе «Приватность».
          </Text>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
          {invitations.data.map((item) => (
            <Card
              key={item.id}
              component={Link}
              to={`/c/invitations/${item.id}`}
              className={classes.card}
              data-new={item.status === 'sent' || undefined}
            >
              <Stack gap="sm">
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <Stack gap={2}>
                    <Text fw={800}>{item.title}</Text>
                    <Text size="sm" c="dimmed">
                      {item.company.name}
                      {item.company.industry ? ` · ${item.company.industry}` : ''}
                    </Text>
                  </Stack>
                  {item.status === 'sent' ? (
                    <Badge color="signal">новое</Badge>
                  ) : (
                    <InvitationStatusBadge status={item.status} />
                  )}
                </Group>
                <SalaryRange
                  from={item.salary_from}
                  to={item.salary_to}
                  caption={item.salary_gross ? 'до вычета НДФЛ' : 'на руки'}
                />
                {(item.status === 'sent' || item.status === 'viewed') && (
                  <Text size="xs" c="dimmed">
                    Ответить до {formatDate(item.expires_at)}
                  </Text>
                )}
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </>
  );
}
