import { Button, Card, Group, Stack, Text } from '@mantine/core';
import { IconLockOpen } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useWithdrawInvitation } from '@/api/invitations';
import type { EmployerInvitation } from '@/api/types';
import { DECLINE_REASON_LABELS } from '@/shared/lib/matching';
import { CategoryBadge, InvitationStatusBadge, SalaryRange, StatusTimeline } from '@/shared/ui';
import { invitationTimeline } from './timeline';
import classes from './InvitationCard.module.css';

export function EmployerInvitationCard({ invitation }: { invitation: EmployerInvitation }) {
  // Приглашение глазами работодателя: кому, на каких условиях, где оно сейчас.
  // Контакты появляются здесь же, как только кандидат его принял.
  const withdraw = useWithdrawInvitation();
  const { candidate } = invitation;
  const active = invitation.status === 'sent' || invitation.status === 'viewed';
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
          <Stack gap={6}>
            <Group gap="xs">
              <Text fw={800}>{invitation.title}</Text>
              <InvitationStatusBadge status={invitation.status} />
            </Group>
            <Group gap="xs">
              <Text size="sm" c="dimmed">
                Кандидат {candidate.alias}
              </Text>
              {candidate.category && (
                <CategoryBadge
                  specialization={candidate.category.specialization.name}
                  grade={candidate.category.grade.code}
                  gradeLabel={candidate.category.grade.name}
                  unconfirmed={candidate.grade_status !== 'confirmed'}
                  size="sm"
                />
              )}
            </Group>
            {invitation.need_title && invitation.need_id && (
              <Text size="xs" c="dimmed">
                Потребность:{' '}
                <Link to={`/e/needs/${invitation.need_id}`}>{invitation.need_title}</Link>
              </Text>
            )}
          </Stack>
          <SalaryRange
            from={invitation.salary_from}
            to={invitation.salary_to}
            size="sm"
            caption={invitation.salary_gross ? 'до НДФЛ' : 'на руки'}
          />
        </Group>
        <StatusTimeline steps={invitationTimeline(invitation.status, invitation.events)} />
        {candidate.contacts && (
          <div className={classes.contacts}>
            <Group gap={6}>
              <IconLockOpen size={16} />
              <Text fw={700}>{candidate.contacts.full_name}</Text>
            </Group>
            <Text size="sm">
              {[candidate.contacts.telegram, candidate.contacts.email, candidate.contacts.phone]
                .filter(Boolean)
                .join(' · ')}
            </Text>
          </div>
        )}
        {invitation.status === 'declined' && invitation.decline_reason && (
          <Text size="sm" c="dimmed">
            Причина отказа: {DECLINE_REASON_LABELS[invitation.decline_reason]}
            {invitation.decline_comment ? ` — «${invitation.decline_comment}»` : ''}
          </Text>
        )}
        <Group gap="sm">
          <Button
            size="xs"
            variant="default"
            component={Link}
            to={`/e/candidates/${candidate.candidate_id}${invitation.need_id ? `?need=${invitation.need_id}` : ''}`}
          >
            Карточка кандидата
          </Button>
          {active && (
            <Button
              size="xs"
              variant="subtle"
              color="signal"
              loading={withdraw.isPending}
              onClick={() => withdraw.mutate(invitation.id)}
            >
              Отозвать
            </Button>
          )}
        </Group>
      </Stack>
    </Card>
  );
}
