import {
  Alert,
  Badge,
  Card,
  Group,
  Pagination,
  ScrollArea,
  Select,
  Skeleton,
  Table,
  Tabs,
  Text,
  TextInput,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { useCategories, useGrades, useSkillSearch, useSpecializations } from '@/api/dictionaries';
import { errorMessage } from '@/api/errors';
import type { SkillKind } from '@/api/types';
import { CategoryBadge, PageHeader } from '@/shared/ui';

const SKILL_KIND_LABELS: Record<SkillKind, string> = {
  language: 'Язык',
  framework: 'Фреймворк',
  database: 'Хранилище',
  tool: 'Инструмент',
  concept: 'Концепция',
  soft: 'Софт-скилл',
};

const PAGE_SIZE = 12;

function QueryState({ error, pending }: { error: unknown; pending: boolean }) {
  if (error) {
    return (
      <Alert color="signal" variant="light">
        {errorMessage(error)}
      </Alert>
    );
  }
  if (pending) return <Skeleton height={160} radius="md" />;
  return null;
}

function SpecializationsTab() {
  const specializations = useSpecializations();
  const categories = useCategories();
  return (
    <>
      <QueryState error={specializations.error} pending={specializations.isPending} />
      {specializations.data && (
        <ScrollArea>
          <Table verticalSpacing="sm" highlightOnHover miw={640}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Код</Table.Th>
                <Table.Th>Название</Table.Th>
                <Table.Th>Описание</Table.Th>
                <Table.Th ta="right">Категорий</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {specializations.data.map((item) => (
                <Table.Tr key={item.id}>
                  <Table.Td ff="monospace">{item.code}</Table.Td>
                  <Table.Td fw={600}>{item.name}</Table.Td>
                  <Table.Td c="dimmed" fz="sm">
                    {item.description}
                  </Table.Td>
                  <Table.Td ta="right" className="tabular">
                    {categories.data?.filter((category) => category.specialization.id === item.id)
                      .length ?? '—'}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </>
  );
}

function GradesTab() {
  const grades = useGrades();
  return (
    <>
      <QueryState error={grades.error} pending={grades.isPending} />
      {grades.data && (
        <ScrollArea>
          <Table verticalSpacing="sm" miw={640}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Ранг</Table.Th>
                <Table.Th>Грейд</Table.Th>
                <Table.Th>Опыт</Table.Th>
                <Table.Th ta="right">Порог θ</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {grades.data.map((grade) => (
                <Table.Tr key={grade.id}>
                  <Table.Td className="tabular">{grade.rank}</Table.Td>
                  <Table.Td>
                    <Text fw={700}>{grade.name}</Text>
                    <Text size="xs" c="dimmed">
                      {grade.description}
                    </Text>
                  </Table.Td>
                  <Table.Td>{grade.experience_hint}</Table.Td>
                  <Table.Td ta="right" ff="monospace">
                    {grade.default_theta_cut.toFixed(1)}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </>
  );
}

function CategoriesTab() {
  const categories = useCategories();
  return (
    <>
      <QueryState error={categories.error} pending={categories.isPending} />
      {categories.data && (
        <ScrollArea>
          <Table verticalSpacing="xs" miw={640}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Категория</Table.Th>
                <Table.Th>Код</Table.Th>
                <Table.Th ta="right">Порог θ</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {categories.data.map((category) => (
                <Table.Tr key={category.id}>
                  <Table.Td>
                    <CategoryBadge
                      specialization={category.specialization.name}
                      grade={category.grade.code}
                      gradeLabel={category.grade.name}
                      size="sm"
                    />
                  </Table.Td>
                  <Table.Td ff="monospace" fz="sm">
                    {category.code}
                  </Table.Td>
                  <Table.Td ta="right" ff="monospace">
                    {category.theta_cut.toFixed(1)}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </>
  );
}

function SkillsTab() {
  const specializations = useSpecializations();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<SkillKind | null>(null);
  const [specializationId, setSpecializationId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [debouncedQuery] = useDebouncedValue(query, 250);

  const skills = useSkillSearch({
    query: debouncedQuery,
    kind: kind ?? undefined,
    specializationId: specializationId ? Number(specializationId) : undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const totalPages = skills.data ? Math.max(1, Math.ceil(skills.data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <Group gap="sm" mb="md" wrap="wrap" align="flex-end">
        <TextInput
          label="Поиск"
          placeholder="Например, «питон» или «k8s»"
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(event) => {
            setQuery(event.currentTarget.value);
            setPage(1);
          }}
          style={{ flex: '1 1 260px' }}
        />
        <Select
          label="Тип"
          placeholder="Все типы"
          clearable
          size="md"
          data={Object.entries(SKILL_KIND_LABELS).map(([value, label]) => ({ value, label }))}
          value={kind}
          onChange={(value) => {
            setKind(value as SkillKind | null);
            setPage(1);
          }}
          w={190}
        />
        <Select
          label="Специализация"
          placeholder="Все"
          clearable
          size="md"
          data={(specializations.data ?? []).map((item) => ({
            value: String(item.id),
            label: item.name,
          }))}
          value={specializationId}
          onChange={(value) => {
            setSpecializationId(value);
            setPage(1);
          }}
          w={230}
        />
      </Group>
      <QueryState error={skills.error} pending={skills.isPending} />
      {skills.data && (
        <>
          <Text size="sm" c="dimmed" mb="xs">
            Найдено: <span className="tabular">{skills.data.total}</span>
          </Text>
          <ScrollArea>
            <Table verticalSpacing="sm" highlightOnHover miw={640}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Навык</Table.Th>
                  <Table.Th>Тип</Table.Th>
                  <Table.Th>Алиасы</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {skills.data.items.map((skill) => (
                  <Table.Tr key={skill.id}>
                    <Table.Td>
                      <Text fw={600}>{skill.name}</Text>
                      <Text size="xs" c="dimmed" ff="monospace">
                        {skill.slug}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge variant="light" color="lilac">
                        {SKILL_KIND_LABELS[skill.kind]}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        {skill.aliases.map((alias) => (
                          <Badge key={alias} variant="outline" color="gray" tt="none" fw={500}>
                            {alias}
                          </Badge>
                        ))}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
          {totalPages > 1 && (
            <Pagination total={totalPages} value={page} onChange={setPage} mt="md" color="fsp" />
          )}
        </>
      )}
    </>
  );
}

export function MethodistHomePage() {
  return (
    <>
      <PageHeader
        kicker="Кабинет методиста"
        title="Справочники"
        description="Специализации, грейды, категории и навыки, на которых строятся опрос, тесты и подбор. Данные загружаются из API."
      />
      <Card padding="lg">
        <Tabs defaultValue="skills" keepMounted={false}>
          <Tabs.List mb="lg">
            <Tabs.Tab value="skills">Навыки</Tabs.Tab>
            <Tabs.Tab value="specializations">Специализации</Tabs.Tab>
            <Tabs.Tab value="grades">Грейды</Tabs.Tab>
            <Tabs.Tab value="categories">Категории</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="skills">
            <SkillsTab />
          </Tabs.Panel>
          <Tabs.Panel value="specializations">
            <SpecializationsTab />
          </Tabs.Panel>
          <Tabs.Panel value="grades">
            <GradesTab />
          </Tabs.Panel>
          <Tabs.Panel value="categories">
            <CategoriesTab />
          </Tabs.Panel>
        </Tabs>
      </Card>
    </>
  );
}
