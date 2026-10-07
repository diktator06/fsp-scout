import { Badge, Group, Skeleton, Stack, Text } from '@mantine/core';
import type { CategorySlice } from '@/api/types';
import { formatRub } from '@/shared/lib/format';
import { RELATION_LABELS } from '@/shared/lib/matching';
import classes from './CategorySlices.module.css';

export function CategorySlices({
  slices,
  loading,
}: {
  slices?: CategorySlice[];
  loading: boolean;
}) {
  // «Сначала рынок, потом люди»: сколько кандидатов в целевой и соседних категориях,
  // сколько из них сильные и реалистична ли вилка.
  if (loading && !slices) return <Skeleton height={240} radius="md" />;
  if (!slices?.length) {
    return (
      <Text size="sm" c="dimmed">
        В подходящих категориях пока нет кандидатов.
      </Text>
    );
  }
  return (
    <Stack gap="sm">
      {slices.map((slice) => (
        <div key={slice.category.id} className={classes.slice} data-relation={slice.relation}>
          <Group justify="space-between" gap={6} wrap="nowrap">
            <Text size="sm" fw={700} lh={1.3}>
              {slice.category.title}
            </Text>
            <Text size="lg" fw={800} className="tabular">
              {slice.candidates}
            </Text>
          </Group>
          <Text size="xs" c="dimmed">
            {RELATION_LABELS[slice.relation] ?? slice.relation} · подтверждено {slice.confirmed}
          </Text>
          <Group gap={6} mt={6}>
            <Badge size="sm" variant="light" color={slice.strong_matches ? 'teal' : 'gray'}>
              сильных: {slice.strong_matches}
            </Badge>
            <Badge size="sm" variant="light" color="fsp">
              весь стек: {slice.covering_must}
            </Badge>
          </Group>
          {slice.median_expectation != null && (
            <Text size="xs" mt={6} c={slice.within_budget ? 'teal.8' : 'signal.8'} fw={600}>
              Медиана ожиданий {formatRub(slice.median_expectation)} ₽ —{' '}
              {slice.within_budget ? 'в вашей вилке' : 'выше вашей вилки'}
            </Text>
          )}
        </div>
      ))}
    </Stack>
  );
}
