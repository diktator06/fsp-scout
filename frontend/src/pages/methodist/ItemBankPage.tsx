import {
  Badge,
  Card,
  Group,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { useMemo, useState } from 'react';
import { useSpecializations } from '@/api/dictionaries';
import { errorMessage } from '@/api/errors';
import { useItemBank } from '@/api/methodist';
import type { ItemFamily, ItemFamilyStatus } from '@/api/types';
import { FamilyDrawer } from '@/features/methodist/FamilyDrawer';
import { FamilyStatusBadge } from '@/features/methodist/FamilyStatusBadge';
import {
  exposureTone,
  FAMILY_STATUS_COPY,
  formatDecimal,
  formatShare,
} from '@/shared/lib/itemBank';
import { ErrorState, FilterChips, LoadingState, PageHeader } from '@/shared/ui';

const EXPOSURE_COLORS = { ok: undefined, warn: 'orange', high: 'signal' } as const;
const ALL = 'all';

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card padding="md">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fz={26} fw={700} className="tabular" lh={1.2}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Card>
  );
}

function FamiliesTable({
  families,
  onOpen,
}: {
  families: ItemFamily[];
  onOpen: (family: ItemFamily) => void;
}) {
  return (
    <ScrollArea>
      <Table verticalSpacing="sm" highlightOnHover miw={860}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Семейство</Table.Th>
            <Table.Th>Компетенция</Table.Th>
            <Table.Th>Грейд</Table.Th>
            <Table.Th ta="right">a</Table.Th>
            <Table.Th ta="right">b</Table.Th>
            <Table.Th>Статус</Table.Th>
            <Table.Th ta="right">Показы</Table.Th>
            <Table.Th ta="right">Верных</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {families.map((family) => {
            const tone = exposureTone(family.exposure_rate);
            return (
              <Table.Tr key={family.id}>
                <Table.Td>
                  <UnstyledButton
                    onClick={() => onOpen(family)}
                    aria-label={`Открыть «${family.title}»`}
                  >
                    <Text fw={600} c="fsp.8">
                      {family.title}
                    </Text>
                    <Text size="xs" c="dimmed" ff="monospace">
                      {family.code}
                    </Text>
                  </UnstyledButton>
                </Table.Td>
                <Table.Td fz="sm">{family.competency.name}</Table.Td>
                <Table.Td fz="sm">{family.nominal_grade.name}</Table.Td>
                <Table.Td ta="right" ff="monospace" fz="sm">
                  {formatDecimal(family.irt_a)}
                </Table.Td>
                <Table.Td ta="right" ff="monospace" fz="sm">
                  {formatDecimal(family.irt_b)}
                </Table.Td>
                <Table.Td>
                  <FamilyStatusBadge status={family.status} />
                </Table.Td>
                <Table.Td ta="right" className="tabular">
                  <Text size="sm" c={EXPOSURE_COLORS[tone]} fw={tone === 'ok' ? 400 : 700}>
                    {family.exposure_count}
                    {family.exposure_rate !== null && ` · ${formatShare(family.exposure_rate)}`}
                  </Text>
                </Table.Td>
                <Table.Td ta="right" className="tabular" fz="sm">
                  {formatShare(family.correct_rate)}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

export function ItemBankPage() {
  const specializations = useSpecializations();
  const [specializationId, setSpecializationId] = useState<string | null>(null);
  const [status, setStatus] = useState<ItemFamilyStatus | typeof ALL>(ALL);
  const [competency, setCompetency] = useState<string | null>(null);
  const [openedId, setOpenedId] = useState<number | null>(null);
  const bank = useItemBank(specializationId ? Number(specializationId) : null);

  const families = useMemo(
    () =>
      (bank.data?.families ?? []).filter(
        (family) =>
          (status === ALL || family.status === status) &&
          (!competency || family.competency.code === competency),
      ),
    [bank.data, status, competency],
  );
  // Открытое семейство берём из свежих данных: после смены статуса карточка
  // показывает новое значение без закрытия.
  const opened = bank.data?.families.find((family) => family.id === openedId) ?? null;
  const counts = (bank.data?.families ?? []).reduce<Record<string, number>>((acc, family) => {
    acc[family.status] = (acc[family.status] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <PageHeader
        kicker="Кабинет методиста"
        title="Банк заданий"
        description="Задание в «Скауте» — это семейство: генератор и параметры модели IRT. Каждый кандидат получает свой экземпляр, поэтому слитый ответ не подходит другому. Здесь видно, какие семейства участвуют в оценке, как часто показываются и как выглядят их экземпляры."
      />
      <Stack gap="lg">
        <Group gap="sm" align="flex-end" wrap="wrap">
          <Select
            label="Специализация"
            placeholder="Весь банк"
            clearable
            w={260}
            data={(specializations.data ?? []).map((item) => ({
              value: String(item.id),
              label: item.name,
            }))}
            value={specializationId}
            onChange={(value) => {
              setSpecializationId(value);
              setCompetency(null);
            }}
          />
          <Select
            label="Компетенция"
            placeholder="Все"
            clearable
            w={260}
            data={(bank.data?.competencies ?? []).map((item) => ({
              value: item.code,
              label: item.name,
            }))}
            value={competency}
            onChange={setCompetency}
          />
        </Group>

        {bank.isPending ? (
          <LoadingState blocks={2} height={200} />
        ) : bank.isError ? (
          <ErrorState message={errorMessage(bank.error)} onRetry={() => void bank.refetch()} />
        ) : (
          <>
            <SimpleGrid cols={{ base: 2, md: 4 }} spacing="md">
              <Stat label="Семейств" value={String(bank.data.families.length)} />
              <Stat label="В оценке" value={String(counts.active ?? 0)} />
              <Stat
                label="Пилот"
                value={String(counts.pilot ?? 0)}
                hint="Без влияния на результат"
              />
              <Stat
                label="Сессий теста"
                value={bank.data.sessions_total === null ? '—' : String(bank.data.sessions_total)}
                hint={
                  bank.data.specialization
                    ? bank.data.specialization.name
                    : 'Выберите специализацию'
                }
              />
            </SimpleGrid>

            {bank.data.specialization && (
              <Card padding="lg">
                <Stack gap="sm">
                  <Title order={4}>Состав теста {bank.data.specialization.name}</Title>
                  <Text size="sm" c="dimmed">
                    Вес — доля заданий компетенции в тесте до учёта стека. Компетенция с
                    навыком-ключом входит в тест, только если навык есть в опросе кандидата.
                  </Text>
                  <ScrollArea>
                    <Table verticalSpacing="xs" miw={720}>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Компетенция</Table.Th>
                          <Table.Th ta="right">Вес</Table.Th>
                          <Table.Th ta="right">В оценке / всего</Table.Th>
                          <Table.Th>Входит, если в стеке</Table.Th>
                          <Table.Th>Подтверждает навыки</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {bank.data.competencies.map((item) => (
                          <Table.Tr key={item.code}>
                            <Table.Td fw={600}>{item.name}</Table.Td>
                            <Table.Td ta="right" className="tabular">
                              {formatShare(item.weight)}
                            </Table.Td>
                            <Table.Td ta="right" className="tabular">
                              <Text
                                size="sm"
                                c={item.active_families < 3 ? 'signal' : undefined}
                                fw={item.active_families < 3 ? 700 : 400}
                              >
                                {item.active_families} / {item.total_families}
                              </Text>
                            </Table.Td>
                            <Table.Td fz="sm" c="dimmed">
                              {item.gate_skills.length ? item.gate_skills.join(', ') : 'всегда'}
                            </Table.Td>
                            <Table.Td>
                              <Group gap={4}>
                                {item.verifies_skills.map((skill) => (
                                  <Badge
                                    key={skill}
                                    variant="outline"
                                    color="gray"
                                    tt="none"
                                    fw={500}
                                  >
                                    {skill}
                                  </Badge>
                                ))}
                              </Group>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </ScrollArea>
                </Stack>
              </Card>
            )}

            <Card padding="lg">
              <Stack gap="md">
                <Group justify="space-between" wrap="wrap" gap="sm">
                  <Title order={4}>Семейства</Title>
                  <FilterChips
                    value={status}
                    onChange={setStatus}
                    options={[
                      { value: ALL, label: 'Все' },
                      ...(['active', 'pilot', 'retired', 'compromised'] as const).map((value) => ({
                        value,
                        label: FAMILY_STATUS_COPY[value].label,
                      })),
                    ]}
                  />
                </Group>
                <Text size="sm" c="dimmed">
                  a — дискриминация, b — сложность на шкале θ (порог Middle около 0,4). Показы
                  выделены, если семейство выпало больше чем в 35 % тестов с его компетенцией: его
                  шаблон легче слить. Откройте семейство, чтобы сгенерировать экземпляры.
                </Text>
                {families.length === 0 ? (
                  <Text size="sm" c="dimmed">
                    Под фильтр ничего не попало.
                  </Text>
                ) : (
                  <FamiliesTable families={families} onOpen={(family) => setOpenedId(family.id)} />
                )}
              </Stack>
            </Card>
          </>
        )}
      </Stack>
      <FamilyDrawer family={opened} onClose={() => setOpenedId(null)} />
    </>
  );
}
