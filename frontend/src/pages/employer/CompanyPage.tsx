import { useNavigate } from 'react-router';
import { useEmployerProfile } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import { CompanyForm } from '@/features/employer/CompanyForm';
import { RestrictionBanner } from '@/features/trust/RestrictionBanner';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

export function CompanyPage() {
  // После первого сохранения ведём сразу к описанию потребности — это следующий шаг.
  const profile = useEmployerProfile();
  const navigate = useNavigate();
  const isNew = profile.data?.company == null;
  return (
    <>
      <PageHeader
        kicker="Компания"
        title={isNew ? 'Расскажите о компании' : 'Профиль компании'}
        description="Название, отрасль и описание кандидат видит в приглашении сразу, контакты — после того как примет его."
      />
      <RestrictionBanner />
      {profile.isPending ? (
        <LoadingState />
      ) : profile.isError ? (
        <ErrorState message={errorMessage(profile.error)} onRetry={() => void profile.refetch()} />
      ) : (
        <CompanyForm
          key={profile.data.company?.id ?? 'new'}
          profile={profile.data}
          onSaved={() => isNew && navigate('/e/needs/new')}
        />
      )}
    </>
  );
}
