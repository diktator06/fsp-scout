import { Chip, Group } from '@mantine/core';

interface FilterChipsProps<T extends string> {
  value: T;
  onChange: (value: T) => void;
  options: readonly { value: T; label: string }[];
}

export function FilterChips<T extends string>({ value, onChange, options }: FilterChipsProps<T>) {
  // Фильтр списка чипами: в отличие от SegmentedControl они переносятся на новую
  // строку, поэтому длинные подписи не обрезаются на узком экране.
  return (
    <Chip.Group multiple={false} value={value} onChange={(next) => onChange(next as T)}>
      <Group gap="xs">
        {options.map((item) => (
          <Chip key={item.value} value={item.value} variant="light">
            {item.label}
          </Chip>
        ))}
      </Group>
    </Chip.Group>
  );
}
