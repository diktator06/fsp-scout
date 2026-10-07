import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router';
import { useCandidateCard, useNeed } from '@/api/employer';
import { ApiError, errorMessage } from '@/api/errors';
import { CandidateProfileView } from '@/features/employer/CandidateProfileView';
import { InviteModal } from '@/features/invitations/InviteModal';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

export function CandidatePage() {
  const { candidateId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const needId = searchParams.get('need');
  const view = useCandidateCard(candidateId, needId);
  const need = useNeed(needId);
  const [inviting, setInviting] = useState(false);

  if (view.isPending) return <LoadingState blocks={3} />;
  if (view.isError) {
    const gone = view.error instanceof ApiError && view.error.status === 404;
    return (
      <ErrorState
        message={gone ? 'Кандидат скрыл профиль или его не существует' : errorMessage(view.error)}
        onRetry={gone ? undefined : () => void view.refetch()}
      />
    );
  }
  return (
    <>
      <PageHeader
        kicker={needId ? 'Кандидат из подборки' : 'Кандидат'}
        title={`Кандидат ${view.data.card.alias}`}
        description={
          need.data
            ? `Из подборки «${need.data.title}» — приглашение унаследует её условия`
            : undefined
        }
      />
      <CandidateProfileView view={view.data} onInvite={() => setInviting(true)} />
      <InviteModal
        opened={inviting}
        onClose={() => setInviting(false)}
        card={view.data.card}
        need={needId ? need.data : null}
      />
    </>
  );
}
