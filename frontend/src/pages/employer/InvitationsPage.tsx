import { Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { useParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useEmployerInvitation, useEmployerInvitations } from '@/api/invitations';
import type { InvitationStatusCode } from '@/api/types';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { EmployerInvitationCard } from '@/features/invitations/EmployerInvitationCard';
import { ErrorState, FilterChips, LoadingState, PageHeader } from '@/shared/ui';

type InvitationFilter = 'all' | 'active' | 'accepted' | 'closed';

const FILTERS: Record<InvitationFilter, InvitationStatusCode[]> = {
  all: [],
  active: ['sent', 'viewed'],
  accepted: ['accepted'],
  closed: ['declined', 'withdrawn', 'expired'],
};

const FILTER_OPTIONS: { value: InvitationFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'active', label: 'Ждут ответа' },
  { value: 'accepted', label: 'Приняты' },
  { value: 'closed', label: 'Закрыты' },
];

function InvitationList() {
  const [filter, setFilter] = useState<InvitationFilter>('all');
  const invitations = useEmployerInvitations(FILTERS[filter]);
  return (
    <Stack gap="md">
      <FilterChips value={filter} onChange={setFilter} options={FILTER_OPTIONS} />
      {invitations.isPending ? (
        <LoadingState blocks={2} height={160} />
      ) : invitations.isError ? (
        <ErrorState
          message={errorMessage(invitations.error)}
          onRetry={() => void invitations.refetch()}
        />
      ) : invitations.data.length === 0 ? (
        <Text c="dimmed">Здесь будут приглашения, отправленные из подборки или банка.</Text>
      ) : (
        invitations.data.map((item) => <EmployerInvitationCard key={item.id} invitation={item} />)
      )}
    </Stack>
  );
}

function SingleInvitation({ invitationId }: { invitationId: string }) {
  const invitation = useEmployerInvitation(invitationId);
  if (invitation.isPending) return <LoadingState blocks={1} />;
  if (invitation.isError) return <ErrorState message={errorMessage(invitation.error)} />;
  return <EmployerInvitationCard invitation={invitation.data} />;
}

export function InvitationsPage() {
  // По ссылке из уведомления открывается одно приглашение, без неё — весь список.
  const { invitationId } = useParams();
  return (
    <>
      <PageHeader
        kicker="Приглашения"
        title={invitationId ? 'Приглашение' : 'Отправленные приглашения'}
        description="Статус виден обеим сторонам: отправлено → просмотрено → ответ. Контакты кандидата появляются после принятия."
      />
      <CompanyGate>
        {invitationId ? <SingleInvitation invitationId={invitationId} /> : <InvitationList />}
      </CompanyGate>
    </>
  );
}
