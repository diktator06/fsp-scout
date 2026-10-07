import { useNavigate, useParams } from 'react-router';
import { useNeed, useSaveNeed } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import { NeedForm } from '@/features/employer/NeedForm';
import { needToValues, valuesToPayload } from '@/features/employer/needValues';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

export function EditNeedPage() {
  const { needId = '' } = useParams();
  const navigate = useNavigate();
  const need = useNeed(needId);
  const save = useSaveNeed(needId);
  return (
    <>
      <PageHeader
        kicker="Подборки"
        title="Изменить потребность"
        description="Уже построенные версии подборки останутся как были. Новая версия учтёт изменения."
      />
      {need.isPending ? (
        <LoadingState />
      ) : need.isError ? (
        <ErrorState message={errorMessage(need.error)} onRetry={() => void need.refetch()} />
      ) : (
        <NeedForm
          initial={needToValues(need.data)}
          submitLabel="Сохранить"
          onSubmit={async (values) => {
            const saved = await save.mutateAsync(valuesToPayload(values));
            navigate(`/e/needs/${saved.id}`);
          }}
        />
      )}
    </>
  );
}
