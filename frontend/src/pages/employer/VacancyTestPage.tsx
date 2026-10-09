import { Button, Stack } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import { Link, useParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useEmployerVacancyTest } from '@/api/vacancies';
import { VacancyTestView } from '@/features/vacancies/VacancyTestView';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

export function EmployerVacancyTestPage() {
  const { vacancyId = '' } = useParams();
  const test = useEmployerVacancyTest(vacancyId);
  return (
    <>
      <PageHeader
        kicker="Вакансия → тест"
        title={test.data?.vacancy.title ?? 'Как проверяются навыки'}
        description="Как кандидат подтверждает категорию и навыки вашей вакансии: какие темы теста закрывают её стек и какие навыки стоит проверить микрозадачей."
        actions={
          <Button
            component={Link}
            to={`/e/vacancies/${vacancyId}`}
            variant="default"
            leftSection={<IconArrowLeft size={16} />}
          >
            К вакансии
          </Button>
        }
      />
      {test.isPending ? (
        <LoadingState blocks={3} height={160} />
      ) : test.isError ? (
        <ErrorState message={errorMessage(test.error)} onRetry={() => void test.refetch()} />
      ) : (
        <Stack gap="lg">
          <VacancyTestView test={test.data} />
        </Stack>
      )}
    </>
  );
}
