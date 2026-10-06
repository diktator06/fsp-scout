import { MultiSelect, type ComboboxItem, type ComboboxItemGroup } from '@mantine/core';
import { useMemo, useState } from 'react';
import { useSkillCatalog } from '@/api/dictionaries';
import type { Skill, SkillKind } from '@/api/types';
import { searchSkills } from '@/shared/lib/skills';

interface SkillPickerProps {
  value: Skill[];
  onChange: (skills: Skill[]) => void;
  label?: string;
  description?: string;
  placeholder?: string;
  error?: string | null;
  maxValues?: number;
  required?: boolean;
}

const KIND_TITLES: Record<SkillKind, string> = {
  language: 'Языки',
  framework: 'Фреймворки и библиотеки',
  database: 'Базы данных',
  tool: 'Инструменты',
  concept: 'Подходы и практики',
  soft: 'Софт-скиллы',
};

export function SkillPicker({
  value,
  onChange,
  label = 'Навыки',
  description,
  placeholder = 'Начните вводить: Python, постгрес, k8s…',
  error,
  maxValues,
  required,
}: SkillPickerProps) {
  // Поиск идёт по каталогу навыков на клиенте и понимает синонимы («питон» →
  // Python). Встроенный фильтр Mantine отключён: он сравнивает только подписи
  // и спрятал бы Python при запросе «питон». Список считается синхронно с вводом,
  // поэтому Enter всегда выбирает первый найденный навык.
  const [search, setSearch] = useState('');
  const catalog = useSkillCatalog();

  const byId = useMemo(() => {
    const map = new Map<number, Skill>();
    for (const skill of [...value, ...(catalog.data ?? [])]) map.set(skill.id, skill);
    return map;
  }, [value, catalog.data]);

  const options = useMemo(() => {
    const picked = new Set(value.map((skill) => skill.id));
    const found = searchSkills(catalog.data ?? [], search).filter((skill) => !picked.has(skill.id));
    const groups = new Map<SkillKind, ComboboxItem<number>[]>();
    for (const skill of [...value, ...found]) {
      const items = groups.get(skill.kind) ?? [];
      items.push({ value: skill.id, label: skill.name });
      groups.set(skill.kind, items);
    }
    return (Object.keys(KIND_TITLES) as SkillKind[])
      .filter((kind) => groups.has(kind))
      .map((kind): ComboboxItemGroup<ComboboxItem<number>> => ({
        group: KIND_TITLES[kind],
        items: groups.get(kind) ?? [],
      }));
  }, [catalog.data, search, value]);

  return (
    <MultiSelect<number>
      label={label}
      description={description}
      placeholder={value.length === 0 ? placeholder : undefined}
      data={options}
      value={value.map((skill) => skill.id)}
      onChange={(ids) =>
        onChange(ids.map((id) => byId.get(id)).filter((skill): skill is Skill => Boolean(skill)))
      }
      searchable
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options: all }) => all}
      selectFirstOptionOnChange
      nothingFoundMessage={catalog.isPending ? 'Загружаем справочник…' : 'Ничего не нашлось'}
      maxValues={maxValues}
      hidePickedOptions
      clearable
      required={required}
      error={error}
      maxDropdownHeight={280}
      size="md"
    />
  );
}
