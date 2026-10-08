import {
  Accordion,
  Alert,
  Badge,
  Card,
  Group,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useMethodistVacancies, useVacancyTest } from '@/api/methodist';
import type { GradeFocus, VacancyTest } from '@/api/types';
import { InstancePreview } from '@/features/methodist/InstancePreview';
import { pluralizeRu } from '@/shared/lib/format';
import { formatDecimal, formatShare } from '@/shared/lib/itemBank';
import { CategoryBadge, ErrorState, LoadingState, PageHeader } from '@/shared/ui';
import classes from './VacancyTestPage.module.css';

const KIND_LABELS = { solve: 'Решить', approach: 'Предложить подход' } as const;

function Flow({ test }: { test: VacancyTest }) {
  // Цепочка из ТЗ в одну строку: что выбрал работодатель и во что это превращается
  // для кандидата. Подробности — в разделах ниже.
  const included = test.competencies.filter((item) => item.included);
  const families = test.grades.reduce((sum, grade) => sum + grade.families.length, 0);
  const steps = [
    { label: 'Вакансия', value: test.vacancy.title, hint: test.vacancy.company_name },
    {
      label: 'Категория',
      value: `${test.vacancy.specialization.name} · ${test.vacancy.grades.map((grade) => grade.name).join(', ')}`,
      hint: test.grades.map((grade) => `порог ${formatDecimal(grade.theta_cut)}`).join(', '),
    },
    {
      label: 'Тест категории',
      value: `${included.length} ${pluralizeRu(included.length, ['компетенция', 'компетенции', 'компетенций'])}`,
      hint: `${test.min_items}–${test.max_items} заданий, тест покрывает ${formatShare(test.coverage)} обязательных навыков`,
    },
    {
      label: 'Задания и микрозадачи',
      value: `${families} ${pluralizeRu(families, ['семейство', 'семейства', 'семейств'])} у порога`,
      hint: `${test.microtasks.length} ${pluralizeRu(test.microtasks.length, ['микрозадача', 'микрозадачи', 'микрозадач'])} компании`,
    },
  ];
  return (
    <ol className={classes.flow}>
      {steps.map((step) => (
        <li key={step.label} className={classes.step}>
          <span className={classes.stepLabel}>{step.label}</span>
          <span className={classes.stepValue}>{step.value}</span>
          <Text size="xs" c="dimmed">
            {step.hint}
          </Text>
        </li>
      ))}
    </ol>
  );
}

function Blueprint({ test }: { test: VacancyTest }) {
  return (
    <Card padding="lg">
      <Stack gap="md">
        <Title order={4}>Состав теста для стека вакансии</Title>
        <Text size="sm" c="dimmed">
          Тест единый для категории, но языковые компетенции входят в него по стеку: кандидат на эту
          вакансию с её навыками получит именно такой состав. Ожидаемое число заданий — при средней
          длине теста; точная длина зависит от того, как быстро оценка отойдёт от порога.
        </Text>
        <ul className={classes.bars}>
          {test.competencies.map((item) => (
            <li key={item.code} className={classes.bar} data-excluded={!item.included || undefined}>
              <Text fw={600} size="sm">
                {item.name}
                {!item.included && (
                  <Text span size="xs" c="dimmed">
                    {' '}
                    — не входит: нужного языка нет в стеке
                  </Text>
                )}
              </Text>
              <Text size="sm" className="tabular" c="dimmed">
                {item.included
                  ? `${formatShare(item.weight)} · ≈${formatDecimal(item.expected_items, 1)} зад.`
                  : '—'}
              </Text>
              <span className={classes.track} aria-hidden="true">
                <span style={{ width: `${Math.max(item.included ? 3 : 0, item.weight * 100)}%` }} />
              </span>
              {item.covers_skills.length > 0 && (
                <Group gap={4} style={{ gridColumn: '1 / -1' }}>
                  {item.covers_skills.map((skill) => (
                    <Badge key={skill} size="sm" variant="light" color="teal" tt="none">
                      {skill}
                    </Badge>
                  ))}
                </Group>
              )}
            </li>
          ))}
        </ul>
      </Stack>
    </Card>
  );
}

function Coverage({ test }: { test: VacancyTest }) {
  const uncovered = test.skills.filter((skill) => skill.verified_by.length === 0);
  return (
    <Card padding="lg">
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap">
          <Title order={4}>Чем подтверждаются навыки вакансии</Title>
          <Badge size="lg" variant="light" color={test.coverage >= 0.5 ? 'teal' : 'orange'}>
            Тест покрывает {formatShare(test.coverage)} обязательных
          </Badge>
        </Group>
        <ScrollArea>
          <Table verticalSpacing="xs" miw={560}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Навык</Table.Th>
                <Table.Th>Важность</Table.Th>
                <Table.Th>Подтверждает</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {test.skills.map((skill) => (
                <Table.Tr key={skill.skill_id}>
                  <Table.Td fw={600}>{skill.name}</Table.Td>
                  <Table.Td>
                    <Badge
                      size="sm"
                      variant={skill.importance === 'must' ? 'filled' : 'outline'}
                      color="fsp"
                      tt="none"
                    >
                      {skill.importance === 'must' ? 'обязательный' : 'желательный'}
                    </Badge>
                  </Table.Td>
                  <Table.Td fz="sm">
                    {skill.verified_by.length > 0 ? (
                      `Тест: ${skill.verified_by.join(', ')}`
                    ) : (
                      <Text span size="sm" c="dimmed">
                        Тест не проверяет — микрозадачи работодателя
                      </Text>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
        {uncovered.length > 0 && (
          <Alert variant="light" color="lilac" icon={<IconInfoCircle size={18} />}>
            {uncovered.map((skill) => skill.name).join(', ')} — специфика вакансии. По ответу
            организаторов (VS.5) тест не подстраивается под вакансию: такие навыки проверяет
            необязательный блок микрозадач работодателя, их результат входит в индекс профиля.
          </Alert>
        )}
      </Stack>
    </Card>
  );
}

function GradeFocusCard({ focus, specialization }: { focus: GradeFocus; specialization: string }) {
  return (
    <Card padding="lg">
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <CategoryBadge
              specialization={specialization}
              grade={focus.grade.code}
              gradeLabel={focus.grade.name}
              size="sm"
            />
            <Text size="sm" c="dimmed">
              порог θ = {formatDecimal(focus.theta_cut)}
            </Text>
          </Group>
          <Text size="xs" c="dimmed" ff="monospace">
            {focus.category_code}
          </Text>
        </Group>
        <Text size="sm" c="dimmed">
          Алгоритм берёт задания с максимумом информации около порога заявленного грейда, поэтому
          тест на {focus.grade.name} собирается из своих семейств. Ниже — три самых информативных и
          по одному свежему экземпляру каждого.
        </Text>
        <Accordion
          variant="separated"
          multiple
          defaultValue={[String(focus.families[0]?.family.id)]}
        >
          {focus.families.map((item) => (
            <Accordion.Item key={item.family.id} value={String(item.family.id)}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" gap="sm">
                  <Stack gap={0}>
                    <Text fw={600} size="sm">
                      {item.family.title}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {item.family.competency.name} · b = {formatDecimal(item.family.irt_b)} · a ={' '}
                      {formatDecimal(item.family.irt_a)}
                    </Text>
                  </Stack>
                  <Text size="xs" c="dimmed" className="tabular" style={{ flex: 'none' }}>
                    I = {formatDecimal(item.information)}
                  </Text>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                {item.sample ? (
                  <InstancePreview instance={item.sample} showParams={false} />
                ) : (
                  <Text size="sm" c="dimmed">
                    Нет генератора.
                  </Text>
                )}
              </Accordion.Panel>
            </Accordion.Item>
          ))}
        </Accordion>
      </Stack>
    </Card>
  );
}

function Microtasks({ test }: { test: VacancyTest }) {
  return (
    <Card padding="lg">
      <Stack gap="sm">
        <Title order={4}>Микрозадачи компании по специализации</Title>
        {test.microtasks.length === 0 ? (
          <Text size="sm" c="dimmed">
            У компании нет активных микрозадач. Навыки, которых нет в тесте, пока подтверждаются
            только опытом в анкете.
          </Text>
        ) : (
          <Stack gap="xs">
            {test.microtasks.map((task) => (
              <Group key={task.id} justify="space-between" wrap="nowrap" gap="sm">
                <Text size="sm" fw={600}>
                  {task.title}
                </Text>
                <Group gap="xs" wrap="nowrap" style={{ flex: 'none' }}>
                  <Badge size="sm" variant="light" color="lilac" tt="none">
                    {KIND_LABELS[task.kind]}
                  </Badge>
                  <Text size="xs" c="dimmed" className="tabular">
                    {task.time_limit_minutes} мин
                  </Text>
                </Group>
              </Group>
            ))}
          </Stack>
        )}
        <Text size="xs" c="dimmed">
          Микрозадачи система предлагает кандидатам адресно; результат входит в фактор актуальности
          индекса профиля. Тест категории они не заменяют.
        </Text>
      </Stack>
    </Card>
  );
}

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
              <Flow test={test.data} />
              <Blueprint test={test.data} />
              <Coverage test={test.data} />
              {test.data.grades.map((focus) => (
                <GradeFocusCard
                  key={focus.category_code}
                  focus={focus}
                  specialization={test.data.vacancy.specialization.name}
                />
              ))}
              <Microtasks test={test.data} />
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
