import { Checkbox } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { useNeed } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import { useCreateVacancy, useEmployerVacancy, useSaveVacancy } from '@/api/vacancies';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { NeedForm } from '@/features/employer/NeedForm';
import {
  needToVacancyValues,
  type NeedFormValues,
  vacancyToValues,
  valuesToVacancyPayload,
} from '@/features/employer/needValues';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

const EMPTY: NeedFormValues = {
  title: '',
  raw_text: '',
  team_description: '',
  specialization_id: null,
  grade_ids: [],
  skills: [],
  work_formats: [],
  city: '',
  salary_from: null,
  salary_to: null,
  salary_gross: true,
};

function NewVacancy() {
  // Вакансию можно собрать из потребности: требования уже разобраны, остаётся
  // дописать условия для кандидата.
  const [searchParams] = useSearchParams();
  const needId = searchParams.get('need');
  const need = useNeed(needId ?? '');
  const create = useCreateVacancy();
  const navigate = useNavigate();
  const [publish, setPublish] = useState(true);
  if (needId && need.isPending) return <LoadingState />;
  if (needId && need.isError) {
    return <ErrorState message={errorMessage(need.error)} onRetry={() => void need.refetch()} />;
  }
  return (
    <NeedForm
      variant="vacancy"
      initial={need.data ? needToVacancyValues(need.data) : EMPTY}
      submitLabel={publish ? 'Опубликовать вакансию' : 'Сохранить черновик'}
      footer={
        <Checkbox
          label="Сразу опубликовать"
          checked={publish}
          onChange={(event) => setPublish(event.currentTarget.checked)}
        />
      }
      onSubmit={async (values) => {
        const vacancy = await create.mutateAsync({
          body: valuesToVacancyPayload(values, needId),
          publish,
        });
        notifications.show({
          color: 'teal',
          title: publish ? 'Вакансия опубликована' : 'Черновик сохранён',
          message: vacancy.title,
        });
        navigate(`/e/vacancies/${vacancy.id}`);
      }}
    />
  );
}

function EditVacancy({ vacancyId }: { vacancyId: string }) {
  const vacancy = useEmployerVacancy(vacancyId);
  const save = useSaveVacancy(vacancyId);
  const navigate = useNavigate();
  if (vacancy.isPending) return <LoadingState />;
  if (vacancy.isError) {
    return (
      <ErrorState message={errorMessage(vacancy.error)} onRetry={() => void vacancy.refetch()} />
    );
  }
  return (
    <NeedForm
      variant="vacancy"
      initial={vacancyToValues(vacancy.data)}
      submitLabel="Сохранить"
      onSubmit={async (values) => {
        await save.mutateAsync(valuesToVacancyPayload(values, vacancy.data.need_id ?? null));
        navigate(`/e/vacancies/${vacancyId}`);
      }}
    />
  );
}

export function VacancyFormPage() {
  const { vacancyId } = useParams();
  return (
    <>
      <PageHeader
        kicker="Вакансии"
        title={vacancyId ? 'Изменить вакансию' : 'Новая вакансия'}
        description="Вилка обязательна: кандидат видит её до отклика. Новая компания может держать опубликованными до пяти вакансий."
      />
      <CompanyGate>
        {vacancyId ? <EditVacancy vacancyId={vacancyId} /> : <NewVacancy />}
      </CompanyGate>
    </>
  );
}
