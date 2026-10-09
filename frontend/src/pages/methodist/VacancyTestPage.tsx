import { Alert, Select, Stack, Text } from '@mantine/core';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useMethodistVacancies, useVacancyTest } from '@/api/methodist';
import { VacancyTestView } from '@/features/vacancies/VacancyTestView';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

export function VacancyTestPage() {
  const vacancies = useMethodistVacancies();
  const [selected, setSelected] = useState<string | null>(null);
  const vacancyId = selected ?? vacancies.data?.[0]?.id ?? null;
  const test = useVacancyTest(vacancyId);

  return (
    <>
      <PageHeader
        kicker="Кабинет методиста"
        title="Вакансия → тест"
        description="Как кандидат подтверждает категорию и навыки конкретной вакансии: категория, состав теста под её стек, задания около порога грейда и микрозадачи работодателя."
      />
      <Stack gap="lg">
        {vacancies.isPending ? (
          <LoadingState blocks={1} height={60} />
        ) : vacancies.isError ? (
          <ErrorState
            message={errorMessage(vacancies.error)}
            onRetry={() => void vacancies.refetch()}
          />
        ) : vacancies.data.length === 0 ? (
          <Alert variant="light" color="lilac">
            Опубликованных вакансий пока нет. Их создают работодатели в разделе «Вакансии».
          </Alert>
        ) : (
          <Select
            label="Вакансия"
            searchable
            maw={620}
            data={vacancies.data.map((item) => ({
              value: item.id,
              label: `${item.title} — ${item.company_name}`,
            }))}
            value={vacancyId}
            onChange={setSelected}
            allowDeselect={false}
            nothingFoundMessage="Не нашли"
          />
        )}

        {vacancyId &&
          (test.isPending ? (
            <LoadingState blocks={3} height={160} />
          ) : test.isError ? (
            <ErrorState message={errorMessage(test.error)} onRetry={() => void test.refetch()} />
          ) : (
            <>
              <VacancyTestView test={test.data} />
              <Text size="sm" c="dimmed">
                Параметры и экземпляры всех семейств — в{' '}
                <Link to="/m/item-bank">банке заданий</Link>.
              </Text>
            </>
          ))}
      </Stack>
    </>
  );
}
