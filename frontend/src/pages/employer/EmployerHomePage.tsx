import {
  Alert,
  Card,
  Group,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconInfoCircle, IconRadar } from '@tabler/icons-react';
import { useMemo } from 'react';
import { useCategories } from '@/api/dictionaries';
import { errorMessage } from '@/api/errors';
import type { Category } from '@/api/types';
import { buildInvitationTimeline } from '@/shared/lib/invitationStatus';
import {
  CategoryBadge,
  InvitationStatusBadge,
  PageHeader,
  SalaryRange,
  StatusTimeline,
} from '@/shared/ui';

function groupBySpecialization(categories: Category[]) {
  // Категории приходят плоским списком: для обзора собираем их под специализациями,
  // сохраняя порядок справочника.
  const groups = new Map<string, { name: string; items: Category[] }>();
  categories.forEach((category) => {
    const key = category.specialization.code;
    const group = groups.get(key) ?? { name: category.specialization.name, items: [] };
    group.items.push(category);
    groups.set(key, group);
  });
  return Array.from(groups.values());
}

export function EmployerHomePage() {
  const categories = useCategories();
  const grouped = useMemo(() => groupBySpecialization(categories.data ?? []), [categories.data]);

  return (
    <>
      <PageHeader
        kicker="Кабинет работодателя"
        title="Найдите специалиста по результату, а не по ключевым словам"
        description="Опишите потребность — система предложит категории и кандидатов с объяснением, почему они подходят. Приглашение отправляется конкретному человеку с обязательной вилкой зарплаты."
      />

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg" mb="lg">
        <Card>
          <Group gap="sm" mb="md">
            <ThemeIcon color="fsp" variant="light" radius="md" size={36}>
              <IconRadar size={20} />
            </ThemeIcon>
            <Title order={4}>Как устроен контакт</Title>
          </Group>
          <Text size="sm" c="dimmed" mb="lg" lh={1.6}>
            Кандидат видит компанию и зарплату до начала общения. Контакты кандидата открываются,
            когда он принимает приглашение. Статус приглашения видят обе стороны.
          </Text>
          <StatusTimeline steps={buildInvitationTimeline('accepted')} />
        </Card>

        <Card>
          <Group justify="space-between" align="flex-start" mb="md" wrap="wrap" gap="sm">
            <Stack gap={4}>
              <Text
                size="xs"
                c="dimmed"
                fw={700}
                tt="uppercase"
                style={{ letterSpacing: '0.08em' }}
              >
                Пример приглашения
              </Text>
              <Title order={4}>Frontend-разработчик в продуктовую команду</Title>
            </Stack>
            <InvitationStatusBadge status="viewed" />
          </Group>
          <Stack gap="md">
            <CategoryBadge specialization="Frontend-разработка" grade="junior" />
            <SalaryRange from={140000} to={190000} caption="до вычета НДФЛ" size="lg" />
            <Text size="sm" c="dimmed">
              Вилка обязательна: без неё приглашение не отправится.
            </Text>
          </Stack>
        </Card>
      </SimpleGrid>

      <Card>
        <Title order={4} mb={4}>
          Категории кандидатов
        </Title>
        <Text size="sm" c="dimmed" mb="lg">
          Кандидаты распределяются по связке «специализация × грейд» по итогам теста.
        </Text>
        {categories.isError && (
          <Alert color="signal" variant="light" icon={<IconInfoCircle size={18} />}>
            {errorMessage(categories.error)}
          </Alert>
        )}
        {categories.isPending && (
          <Stack gap="sm">
            {[1, 2, 3].map((row) => (
              <Skeleton key={row} height={34} radius="xl" />
            ))}
          </Stack>
        )}
        <Stack gap="md">
          {grouped.map((group) => (
            <Stack key={group.name} gap={8}>
              <Text fw={700} size="sm">
                {group.name}
              </Text>
              <Group gap={8} wrap="wrap">
                {group.items.map((category) => (
                  <CategoryBadge
                    key={category.code}
                    specialization={category.specialization.name}
                    grade={category.grade.code}
                    gradeLabel={category.grade.name}
                    size="sm"
                  />
                ))}
              </Group>
            </Stack>
          ))}
        </Stack>
      </Card>
    </>
  );
}
