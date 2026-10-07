import {
  Button,
  Card,
  Checkbox,
  Group,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useState } from 'react';
import { Link } from 'react-router';
import { useGrades, useSpecializations } from '@/api/dictionaries';
import { useBank } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import type { BankSort, CandidateCard, Skill, WorkFormat } from '@/api/types';
import { SkillPicker } from '@/features/candidate/SkillPicker';
import { CandidateSummary } from '@/features/employer/CandidateSummary';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { InviteModal } from '@/features/invitations/InviteModal';
import { groupByDirection } from '@/shared/lib/assessment';
import { WORK_FORMAT_LABELS, toOptions } from '@/shared/lib/candidate';
import { pluralizeRu } from '@/shared/lib/format';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

const PAGE_SIZE = 10;
const SORT_OPTIONS: Array<{ value: BankSort; label: string }> = [
  { value: 'score', label: 'Подтверждённые выше, по индексу' },
  { value: 'experience', label: 'По опыту' },
  { value: 'recent', label: 'Недавно обновлённые' },
];

export function BankPage() {
  // Банк — поиск без потребности: фильтры по категории, стеку и условиям. Кандидаты
  // с подтверждённым грейдом идут раньше заявленных, внутри — по индексу профиля.
  const specializations = useSpecializations();
  const grades = useGrades();
  const [specializationId, setSpecializationId] = useState<string | null>(null);
  const [gradeId, setGradeId] = useState<string | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [workFormat, setWorkFormat] = useState<WorkFormat | null>(null);
  const [city, setCity] = useState('');
  const [debouncedCity] = useDebouncedValue(city, 300);
  const [sort, setSort] = useState<BankSort>('score');
  const [page, setPage] = useState(1);
  const [inviting, setInviting] = useState<CandidateCard | null>(null);

  const bank = useBank({
    specializationId: specializationId ? Number(specializationId) : null,
    gradeId: gradeId ? Number(gradeId) : null,
    skillIds: skills.map((skill) => skill.id),
    confirmedOnly,
    verifiedSkillsOnly: verifiedOnly,
    workFormat,
    city: debouncedCity,
    sort,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const reset =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value);
      setPage(1);
    };
  const total = bank.data?.total ?? 0;

  return (
    <>
      <PageHeader
        kicker="Банк кандидатов"
        title="Специалисты с подтверждённой категорией"
        description="Только те, кто дал согласие на публикацию. Имена и контакты скрыты до принятия приглашения."
      />
      <CompanyGate>
        <Card mb="lg">
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
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
            <Select
              label="Грейд"
              placeholder="Любой"
              data={(grades.data ?? []).map((grade) => ({
                value: String(grade.id),
                label: grade.name,
              }))}
              value={gradeId}
              onChange={reset(setGradeId)}
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
            <TextInput
              label="Город"
              placeholder="Если кандидат его показывает"
              value={city}
              onChange={(event) => reset(setCity)(event.currentTarget.value)}
            />
          </SimpleGrid>
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md" mt="md">
            <SkillPicker
              label="Стек — все навыки"
              value={skills}
              onChange={reset(setSkills)}
              maxValues={10}
            />
            <Stack gap="xs" justify="flex-end">
              <Checkbox
                label="Только с подтверждённым грейдом"
                checked={confirmedOnly}
                onChange={(event) => reset(setConfirmedOnly)(event.currentTarget.checked)}
              />
              <Checkbox
                label="Навыки подтверждены тестом"
                checked={verifiedOnly}
                onChange={(event) => reset(setVerifiedOnly)(event.currentTarget.checked)}
                disabled={skills.length === 0}
              />
            </Stack>
          </SimpleGrid>
        </Card>
        <Group justify="space-between" mb="md" wrap="wrap">
          <Text c="dimmed" size="sm">
            {bank.data
              ? `${total} ${pluralizeRu(total, ['кандидат', 'кандидата', 'кандидатов'])}: подтверждённых ${bank.data.confirmed}, заявленных ${bank.data.unconfirmed}`
              : 'Ищем…'}
          </Text>
          <Select
            size="xs"
            w={260}
            data={SORT_OPTIONS}
            value={sort}
            onChange={(value) => value && reset(setSort)(value as BankSort)}
            allowDeselect={false}
            aria-label="Сортировка"
          />
        </Group>
        {bank.isPending ? (
          <LoadingState blocks={3} height={120} />
        ) : bank.isError ? (
          <ErrorState message={errorMessage(bank.error)} onRetry={() => void bank.refetch()} />
        ) : (
          <Stack gap="md">
            {bank.data.items.map((item) => (
              <Card key={item.card.candidate_id} padding="lg">
                <Stack gap="sm">
                  <CandidateSummary
                    card={item.card}
                    invitation={item.invitation}
                    contactsDisclosed={item.contacts_disclosed}
                  />
                  <Group gap={6}>
                    {item.card.skills.slice(0, 8).map((skill) => (
                      <Text
                        key={skill.id}
                        size="xs"
                        fw={600}
                        c={skill.verified ? 'teal.9' : 'fsp.8'}
                        span
                      >
                        {skill.verified ? '✓ ' : ''}
                        {skill.name}
                      </Text>
                    ))}
                  </Group>
                  <Group gap="sm">
                    <Button
                      size="xs"
                      variant="default"
                      component={Link}
                      to={`/e/candidates/${item.card.candidate_id}`}
                    >
                      Карточка
                    </Button>
                    <Button
                      size="xs"
                      onClick={() => setInviting(item.card)}
                      disabled={Boolean(
                        item.invitation &&
                        ['sent', 'viewed', 'accepted'].includes(item.invitation.status),
                      )}
                    >
                      Пригласить
                    </Button>
                  </Group>
                </Stack>
              </Card>
            ))}
            {total > PAGE_SIZE && (
              <Pagination
                total={Math.ceil(total / PAGE_SIZE)}
                value={page}
                onChange={setPage}
                color="fsp"
              />
            )}
          </Stack>
        )}
      </CompanyGate>
      <InviteModal opened={inviting !== null} onClose={() => setInviting(null)} card={inviting} />
    </>
  );
}
