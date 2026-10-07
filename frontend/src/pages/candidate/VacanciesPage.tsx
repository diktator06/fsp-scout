import {
  Alert,
  Anchor,
  Button,
  Card,
  Group,
  NumberInput,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconListCheck, IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useSpecializations } from '@/api/dictionaries';
import { errorMessage } from '@/api/errors';
import type { WorkFormat } from '@/api/types';
import { useVacancyBoard } from '@/api/vacancies';
import { VacancySummaryCard } from '@/features/vacancies/VacancySummaryCard';
import { groupByDirection } from '@/shared/lib/assessment';
import { WORK_FORMAT_LABELS, toOptions } from '@/shared/lib/candidate';
import { pluralizeRu } from '@/shared/lib/format';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

const PAGE_SIZE = 10;

export function VacanciesPage() {
  // Дополнительный канал к приглашениям: кандидат, которого ещё не нашли, может
  // проявить инициативу сам. Лента упорядочена по соответствию его профилю.
  const specializations = useSpecializations();
  const [specializationId, setSpecializationId] = useState<string | null>(null);
  const [workFormat, setWorkFormat] = useState<WorkFormat | null>(null);
  const [salaryMin, setSalaryMin] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [debouncedText] = useDebouncedValue(text, 300);
  const [page, setPage] = useState(1);
  const board = useVacancyBoard({
    specializationId: specializationId ? Number(specializationId) : null,
    workFormat,
    salaryMin,
    text: debouncedText,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const reset =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value);
      setPage(1);
    };
  const total = board.data?.total ?? 0;

  return (
    <>
      <PageHeader
        kicker="Вакансии"
        title="Откликнуться самому"
        description="Основной путь — приглашения от компаний. Но если вы видите подходящую вакансию, откликнитесь: вилка указана в каждой."
        actions={
          <Button
            component={Link}
            to="/c/applications"
            variant="light"
            leftSection={<IconListCheck size={16} />}
          >
            Мои отклики
          </Button>
        }
      />
      {board.data && !board.data.can_apply && (
        <Alert color="lilac" variant="light" mb="lg">
          Чтобы видеть соответствие вакансиям и откликаться, пройдите опрос о стеке —{' '}
          <Anchor component={Link} to="/c/onboarding" fw={600}>
            это займёт пару минут
          </Anchor>
          .
        </Alert>
      )}
      <Card mb="lg">
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
          <TextInput
            label="Поиск"
            placeholder="Python, платежи, аналитика…"
            leftSection={<IconSearch size={16} />}
            value={text}
            onChange={(event) => reset(setText)(event.currentTarget.value)}
          />
          <Select
            label="Специализация"
            placeholder="Любая"
            data={groupByDirection(specializations.data ?? []).map((group) => ({
              group: group.name,
              items: group.items.map((item) => ({ value: String(item.id), label: item.name })),
            }))}
            value={specializationId}
            onChange={reset(setSpecializationId)}
            clearable
          />
          <Select<WorkFormat>
            label="Формат"
            placeholder="Любой"
            data={toOptions(WORK_FORMAT_LABELS)}
            value={workFormat}
            onChange={reset(setWorkFormat)}
            clearable
          />
          <NumberInput
            label="Зарплата от, ₽"
            placeholder="Например, 200 000"
            thousandSeparator=" "
            min={0}
            step={10000}
            value={salaryMin ?? ''}
            onChange={(value) => reset(setSalaryMin)(typeof value === 'number' ? value : null)}
          />
        </SimpleGrid>
      </Card>
      {board.isPending ? (
        <LoadingState blocks={3} height={120} />
      ) : board.isError ? (
        <ErrorState message={errorMessage(board.error)} onRetry={() => void board.refetch()} />
      ) : board.data.items.length === 0 ? (
        <Card>
          <Text c="dimmed">
            Под эти фильтры вакансий нет. Ослабьте фильтры — а лучше проверьте, что профиль
            опубликован в банке: компании сами находят кандидатов по категориям.
          </Text>
        </Card>
      ) : (
        <Stack gap="md">
          <Text size="sm" c="dimmed">
            {total} {pluralizeRu(total, ['вакансия', 'вакансии', 'вакансий'])}
            {board.data.can_apply ? ', сначала самые подходящие вам' : ''}
          </Text>
          {board.data.items.map((vacancy) => (
            <VacancySummaryCard key={vacancy.id} vacancy={vacancy} />
          ))}
          {total > PAGE_SIZE && (
            <Group justify="center">
              <Pagination
                total={Math.ceil(total / PAGE_SIZE)}
                value={page}
                onChange={setPage}
                color="fsp"
              />
            </Group>
          )}
        </Stack>
      )}
    </>
  );
}
