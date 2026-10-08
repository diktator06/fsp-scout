import {
  Alert,
  Button,
  Divider,
  Drawer,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconRefresh } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useFamilySamples, useFamilyStatus } from '@/api/methodist';
import type { ItemFamily, ItemFamilyStatus } from '@/api/types';
import {
  EDITABLE_STATUSES,
  FAMILY_STATUS_COPY,
  formatDecimal,
  formatShare,
} from '@/shared/lib/itemBank';
import { ErrorState, FilterChips } from '@/shared/ui';
import { FamilyStatusBadge } from './FamilyStatusBadge';
import { InstancePreview } from './InstancePreview';

const FORMAT_LABELS = { single_choice: 'Выбор из четырёх', numeric: 'Число' } as const;

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={600} className="tabular">
        {value}
      </Text>
    </Stack>
  );
}

function StatusForm({ family }: { family: ItemFamily }) {
  // Смена статуса пишется в журнал аудита с причиной: от состава банка зависят
  // грейды людей, поэтому решение должно быть объяснимо и через полгода.
  const [status, setStatus] = useState<ItemFamilyStatus>(family.status);
  const [reason, setReason] = useState('');
  const mutation = useFamilyStatus(family.id);
  const changed = status !== family.status;

  const submit = () => {
    mutation.mutate(
      { status: status as Exclude<ItemFamilyStatus, 'draft'>, reason: reason.trim() },
      {
        onSuccess: () => {
          setReason('');
          notifications.show({
            color: 'teal',
            message: `Статус: ${FAMILY_STATUS_COPY[status].label}`,
          });
        },
      },
    );
  };

  return (
    <Stack gap="sm">
      <Title order={5}>Статус в банке</Title>
      <FilterChips
        value={status}
        onChange={setStatus}
        options={EDITABLE_STATUSES.map((value) => ({
          value,
          label: FAMILY_STATUS_COPY[value].label,
        }))}
      />
      <Text size="xs" c="dimmed">
        {FAMILY_STATUS_COPY[status].hint}
      </Text>
      {changed && (
        <Textarea
          label="Причина"
          description="Попадёт в журнал аудита"
          placeholder="Например, низкая корреляция с итогом на пилоте"
          autosize
          minRows={2}
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
      )}
      {mutation.isError && (
        <Alert color="signal" variant="light">
          {errorMessage(mutation.error)}
        </Alert>
      )}
      <Group justify="flex-end">
        <Button
          onClick={submit}
          disabled={!changed || reason.trim().length < 3}
          loading={mutation.isPending}
        >
          Сохранить статус
        </Button>
      </Group>
    </Stack>
  );
}

function Samples({ family }: { family: ItemFamily }) {
  const [round, setRound] = useState(0);
  const samples = useFamilySamples(family.has_generator ? family.id : null, round);
  if (!family.has_generator) {
    return (
      <Alert color="signal" variant="light">
        У семейства нет генератора в коде — экземпляры не собрать.
      </Alert>
    );
  }
  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="nowrap">
        <Title order={5}>Экземпляры</Title>
        <Button
          size="xs"
          variant="light"
          leftSection={samples.isFetching ? <Loader size={14} /> : <IconRefresh size={14} />}
          onClick={() => setRound((value) => value + 1)}
          disabled={samples.isFetching}
        >
          Сгенерировать другие
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        Три экземпляра одного семейства — так их получат три разных кандидата. Генератор тот же, что
        в тесте: числа, данные и порядок вариантов у каждого свои, поэтому слитый ответ одного
        кандидата не подходит другому.
      </Text>
      {samples.isError ? (
        <ErrorState message={errorMessage(samples.error)} onRetry={() => void samples.refetch()} />
      ) : !samples.data ? (
        <Loader size="sm" />
      ) : (
        <Tabs defaultValue="0" keepMounted={false}>
          <Tabs.List>
            {samples.data.instances.map((instance, index) => (
              <Tabs.Tab key={instance.seed} value={String(index)}>
                Кандидат {index + 1}
              </Tabs.Tab>
            ))}
          </Tabs.List>
          {samples.data.instances.map((instance, index) => (
            <Tabs.Panel key={instance.seed} value={String(index)} pt="md">
              <InstancePreview instance={instance} />
            </Tabs.Panel>
          ))}
        </Tabs>
      )}
    </Stack>
  );
}

interface FamilyDrawerProps {
  family: ItemFamily | null;
  onClose: () => void;
}

export function FamilyDrawer({ family, onClose }: FamilyDrawerProps) {
  return (
    <Drawer
      opened={family !== null}
      onClose={onClose}
      position="right"
      size="xl"
      title={family ? <Text fw={700}>{family.title}</Text> : null}
    >
      {family && (
        <Stack gap="lg" key={family.id}>
          <Group gap="xs">
            <FamilyStatusBadge status={family.status} />
            <Text size="sm" ff="monospace" c="dimmed">
              {family.code}
            </Text>
          </Group>
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="md">
            <Fact label="Компетенция" value={family.competency.name} />
            <Fact label="Номинальный грейд" value={family.nominal_grade.name} />
            <Fact label="Формат" value={FORMAT_LABELS[family.response_format]} />
            <Fact label="Лимит" value={`${family.time_limit_sec} с`} />
            <Fact label="Дискриминация a" value={formatDecimal(family.irt_a)} />
            <Fact label="Сложность b" value={formatDecimal(family.irt_b)} />
            <Fact label="Угадывание c" value={formatDecimal(family.irt_c)} />
            <Fact
              label="Калибровка"
              value={family.calibrated_at ? `v${family.version}` : 'экспертная'}
            />
            <Fact label="Показов" value={String(family.exposure_count)} />
            <Fact label="Ответов" value={String(family.responses_count)} />
            <Fact label="Верных" value={formatShare(family.correct_rate)} />
          </SimpleGrid>
          <Divider />
          <Samples family={family} />
          <Divider />
          <StatusForm family={family} />
        </Stack>
      )}
    </Drawer>
  );
}
