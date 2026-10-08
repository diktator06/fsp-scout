import {
  Alert,
  Button,
  Card,
  Group,
  NumberInput,
  ScrollArea,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconInfoCircle } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useAssessmentSettings, useThetaCut } from '@/api/methodist';
import type { EngineSettings, ScaleCategory, SpecializationScale } from '@/api/types';
import { thetaToPercent } from '@/shared/lib/assessment';
import { cutError, formatDecimal, formatShare } from '@/shared/lib/itemBank';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';
import classes from './AssessmentSettingsPage.module.css';

const ENGINE_ROWS: {
  key: keyof EngineSettings;
  label: string;
  format: (value: number) => string;
}[] = [
  { key: 'min_items', label: 'Минимум заданий', format: String },
  { key: 'max_items', label: 'Максимум заданий', format: String },
  {
    key: 'confidence_z',
    label: 'Остановка: |θ − порог| ≥ z·SE',
    format: (value) => `z = ${formatDecimal(value)}`,
  },
  {
    key: 'target_se',
    label: 'Остановка по точности: SE ≤',
    format: (value) => formatDecimal(value),
  },
  {
    key: 'randomesque',
    label: 'Случайный выбор из лучших',
    format: (value) => `из ${value}`,
  },
  { key: 'max_exposure_rate', label: 'Целевой потолок показов', format: formatShare },
  { key: 'pilot_items', label: 'Пилотных заданий', format: String },
];

function ScaleTrack({ categories }: { categories: ScaleCategory[] }) {
  // Шкала θ от −3 до 3: сплошные риски — текущие пороги, пунктир — исходные из
  // справочника грейдов. Видно, насколько методист сдвинул пороги после калибровки.
  return (
    <div className={classes.scale} role="img" aria-label="Пороги грейдов на шкале способностей">
      {categories.map((category) => (
        <span key={category.category_id}>
          {category.default_theta_cut !== category.theta_cut && (
            <span
              className={classes.default}
              style={{ left: `${thetaToPercent(category.default_theta_cut)}%` }}
            />
          )}
          <span className={classes.cut} style={{ left: `${thetaToPercent(category.theta_cut)}%` }}>
            <span className={classes.cutLabel}>{category.grade.name}</span>
          </span>
        </span>
      ))}
    </div>
  );
}

function CutRow({
  category,
  lower,
  higher,
}: {
  category: ScaleCategory;
  lower: number | null;
  higher: number | null;
}) {
  const [value, setValue] = useState<number>(category.theta_cut);
  const [reason, setReason] = useState('');
  const mutation = useThetaCut(category.category_id);
  const changed = Math.abs(value - category.theta_cut) > 1e-9;
  const error = changed ? cutError(value, lower, higher) : null;

  const save = () =>
    mutation.mutate(
      { theta_cut: value, reason: reason.trim() },
      {
        onSuccess: () => {
          setReason('');
          notifications.show({
            color: 'teal',
            message: `Порог ${category.grade.name}: ${formatDecimal(value)}`,
          });
        },
      },
    );

  return (
    <>
      <Table.Tr>
        <Table.Td fw={600}>{category.grade.name}</Table.Td>
        <Table.Td ta="right" ff="monospace" c="dimmed">
          {formatDecimal(category.default_theta_cut)}
        </Table.Td>
        <Table.Td>
          <NumberInput
            aria-label={`Порог ${category.grade.name}`}
            value={value}
            onChange={(next) => setValue(typeof next === 'number' ? next : Number(next) || 0)}
            step={0.05}
            decimalScale={2}
            decimalSeparator=","
            min={-3}
            max={3}
            w={120}
            error={error}
          />
        </Table.Td>
      </Table.Tr>
      {changed && (
        <Table.Tr>
          <Table.Td colSpan={3}>
            <Group gap="sm" align="flex-start" wrap="wrap">
              <TextInput
                aria-label={`Причина изменения порога ${category.grade.name}`}
                placeholder="Причина — попадёт в журнал аудита"
                value={reason}
                onChange={(event) => setReason(event.currentTarget.value)}
                style={{ flex: '1 1 220px' }}
                error={mutation.isError ? errorMessage(mutation.error) : undefined}
              />
              <Button
                variant="light"
                onClick={save}
                disabled={error !== null || reason.trim().length < 3}
                loading={mutation.isPending}
              >
                Сохранить
              </Button>
              <Button variant="subtle" color="gray" onClick={() => setValue(category.theta_cut)}>
                Отменить
              </Button>
            </Group>
          </Table.Td>
        </Table.Tr>
      )}
    </>
  );
}

function ScaleCard({ scale }: { scale: SpecializationScale }) {
  const ordered = [...scale.categories].sort((a, b) => a.grade.rank - b.grade.rank);
  return (
    <Card padding="lg">
      <Stack gap="sm">
        <Title order={5}>{scale.specialization.name}</Title>
        <ScaleTrack categories={ordered} />
        <ScrollArea>
          <Table verticalSpacing="xs" miw={320}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Грейд</Table.Th>
                <Table.Th ta="right">Исходный</Table.Th>
                <Table.Th>Порог θ</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {ordered.map((category, index) => (
                <CutRow
                  key={`${category.category_id}-${category.theta_cut}`}
                  category={category}
                  lower={ordered[index - 1]?.theta_cut ?? null}
                  higher={ordered[index + 1]?.theta_cut ?? null}
                />
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      </Stack>
    </Card>
  );
}

export function AssessmentSettingsPage() {
  const settings = useAssessmentSettings();
  if (settings.isPending) return <LoadingState blocks={3} height={180} />;
  if (settings.isError) {
    return (
      <ErrorState message={errorMessage(settings.error)} onRetry={() => void settings.refetch()} />
    );
  }
  const data = settings.data;
  return (
    <>
      <PageHeader
        kicker="Кабинет методиста"
        title="Настройки оценки"
        description="Параметры адаптивного теста, правила пересдачи и пороги грейдов на шкале способностей. Пороги методист двигает после калибровки на реальных ответах."
      />
      <Stack gap="lg">
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
          <Card padding="lg">
            <Stack gap="sm">
              <Title order={4}>Алгоритм {data.algorithm_version}</Title>
              <Text size="sm">
                <b>По ходу теста:</b> {data.interim_estimator}.
              </Text>
              <Text size="sm">
                <b>Итог:</b> {data.final_estimator}.
              </Text>
              <ScrollArea>
                <Table verticalSpacing={6} miw={380}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Параметр</Table.Th>
                      <Table.Th ta="right">Полный</Table.Th>
                      <Table.Th ta="right">Экспресс</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {ENGINE_ROWS.map((row) => (
                      <Table.Tr key={row.key}>
                        <Table.Td fz="sm">{row.label}</Table.Td>
                        <Table.Td ta="right" className="tabular" fz="sm">
                          {row.format(data.full[row.key])}
                        </Table.Td>
                        <Table.Td ta="right" className="tabular" fz="sm">
                          {row.format(data.express[row.key])}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
              <Text size="xs" c="dimmed">
                Экспресс-режим {data.express_enabled ? 'включён' : 'выключен'} настройкой стенда.
                Параметры движка обоснованы симуляцией (docs/VALIDATION.md) и меняются релизом, а не
                из интерфейса: от них зависит сопоставимость грейдов.
              </Text>
            </Stack>
          </Card>
          <Card padding="lg">
            <Stack gap="sm">
              <Title order={4}>Правила пересдачи</Title>
              <Table verticalSpacing={6}>
                <Table.Tbody>
                  <Table.Tr>
                    <Table.Td fz="sm">Смена присвоенного грейда</Table.Td>
                    <Table.Td
                      ta="right"
                      className="tabular"
                      fz="sm"
                      style={{ whiteSpace: 'nowrap' }}
                    >
                      раз в {data.policy.grade_change_cooldown_days} дн.
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td fz="sm">Повтор неудачного повышения</Table.Td>
                    <Table.Td
                      ta="right"
                      className="tabular"
                      fz="sm"
                      style={{ whiteSpace: 'nowrap' }}
                    >
                      через {data.policy.upgrade_retry_days} дн.
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td fz="sm">Повтор на онбординге (уровень и выше)</Table.Td>
                    <Table.Td
                      ta="right"
                      className="tabular"
                      fz="sm"
                      style={{ whiteSpace: 'nowrap' }}
                    >
                      через {data.policy.onboarding_retry_hours} ч
                    </Table.Td>
                  </Table.Tr>
                  <Table.Tr>
                    <Table.Td fz="sm">Окно сразу после «подтверждён с запасом»</Table.Td>
                    <Table.Td ta="right" className="tabular" fz="sm">
                      {data.policy.confident_upgrade_window_hours} ч
                    </Table.Td>
                  </Table.Tr>
                </Table.Tbody>
              </Table>
              <Text size="xs" c="dimmed">
                Провал не сжигает попытку: уровни ниже доступны сразу. Сроки задаются переменными
                окружения стенда.
              </Text>
            </Stack>
          </Card>
        </SimpleGrid>

        <Stack gap="sm">
          <Title order={4}>Пороги грейдов</Title>
          <Alert variant="light" color="lilac" icon={<IconInfoCircle size={18} />}>
            Порог должен быть выше порога младшего грейда и ниже старшего хотя бы на 0,3 — иначе
            грейды неразличимы при типичной ошибке измерения. Новый порог действует для тестов,
            завершённых после изменения; присвоенные категории не пересчитываются. Каждое изменение
            пишется в журнал аудита.
          </Alert>
          <SimpleGrid cols={{ base: 1, xl: 2 }} spacing="lg">
            {data.scales.map((scale) => (
              <ScaleCard key={scale.specialization.id} scale={scale} />
            ))}
          </SimpleGrid>
        </Stack>
      </Stack>
    </>
  );
}
