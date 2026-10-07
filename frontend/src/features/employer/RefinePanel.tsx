import {
  Button,
  Checkbox,
  Chip,
  Group,
  MultiSelect,
  Slider,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useState } from 'react';
import type { Need, ShortlistFilters, WorkFormat } from '@/api/types';
import { WORK_FORMAT_LABELS, toOptions } from '@/shared/lib/candidate';

interface RefinePanelProps {
  need: Need;
  current: ShortlistFilters;
  loading: boolean;
  onApply: (filters: ShortlistFilters) => void;
}

export function RefinePanel({ need, current, loading, onApply }: RefinePanelProps) {
  // Уточнения не перестраивают текущую выдачу, а создают новую версию подборки:
  // прежняя остаётся доступной, закреплённые кандидаты переходят в новую.
  const [filters, setFilters] = useState<ShortlistFilters>(current);
  const skillOptions = need.skills.map((item) => ({
    value: String(item.skill.id),
    label: item.skill.name,
  }));
  const set = <K extends keyof ShortlistFilters>(key: K, value: ShortlistFilters[K]) =>
    setFilters((previous) => ({ ...previous, [key]: value }));

  return (
    <Stack gap="md">
      <Text fw={700}>Уточнить подборку</Text>
      <Checkbox
        label="Только с подтверждённым грейдом"
        checked={filters.confirmed_only ?? false}
        onChange={(event) => set('confirmed_only', event.currentTarget.checked)}
      />
      <Checkbox
        label="Добавить соседние грейды"
        description="Ниже в выдаче, с пометкой"
        checked={filters.expand_grades ?? false}
        onChange={(event) => set('expand_grades', event.currentTarget.checked)}
      />
      <Checkbox
        label="Ожидания в моей вилке"
        checked={filters.within_budget ?? false}
        onChange={(event) => set('within_budget', event.currentTarget.checked)}
      />
      <MultiSelect
        label="Навык подтверждён тестом"
        placeholder="Python, SQL…"
        data={skillOptions}
        value={(filters.verified_skill_ids ?? []).map(String)}
        onChange={(value) => set('verified_skill_ids', value.map(Number))}
        clearable
      />
      <MultiSelect
        label="Навык есть в профиле"
        data={skillOptions}
        value={(filters.required_skill_ids ?? []).map(String)}
        onChange={(value) => set('required_skill_ids', value.map(Number))}
        clearable
      />
      <div>
        <Text size="sm" fw={500} mb={6}>
          Формат работы
        </Text>
        <Chip.Group<true, WorkFormat>
          multiple
          value={filters.work_formats ?? []}
          onChange={(value) => set('work_formats', value)}
        >
          <Group gap={6}>
            {toOptions(WORK_FORMAT_LABELS).map((option) => (
              <Chip key={option.value} value={option.value} size="xs" variant="light" color="fsp">
                {option.label}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </div>
      <TextInput
        label="Город"
        placeholder="Только если кандидат его показывает"
        value={filters.city ?? ''}
        onChange={(event) => set('city', event.currentTarget.value || null)}
        size="sm"
      />
      <div>
        <Text size="sm" fw={500}>
          Минимальный балл: {Math.round((filters.min_score ?? 0) * 100)}
        </Text>
        <Slider
          mt={6}
          min={0}
          max={80}
          step={5}
          value={Math.round((filters.min_score ?? 0) * 100)}
          onChange={(value) => set('min_score', value / 100)}
          label={null}
          color="fsp"
          aria-label="Минимальный балл соответствия"
        />
      </div>
      <Button onClick={() => onApply(filters)} loading={loading}>
        Применить — новая версия
      </Button>
    </Stack>
  );
}
