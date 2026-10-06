import { Badge, Card, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconEyeOff, IconLock, IconTargetArrow } from '@tabler/icons-react';
import { useAuth } from '@/features/auth/useAuth';
import type { TimelineStep } from '@/shared/lib/invitationStatus';
import { type ScoreFactor } from '@/shared/lib/score';
import {
  CategoryBadge,
  PageHeader,
  SalaryRange,
  StatusTimeline,
  VerifiedScoreBar,
} from '@/shared/ui';

const ONBOARDING_STEPS: TimelineStep[] = [
  { key: 'account', label: 'Аккаунт', state: 'done', description: 'Email подтверждён' },
  { key: 'profile', label: 'Профиль', state: 'current', description: 'Форма или PDF-резюме' },
  { key: 'survey', label: 'Опрос', state: 'upcoming', description: 'Специализация и стек' },
  { key: 'test', label: 'Тест на грейд', state: 'upcoming', description: '20–30 минут' },
  { key: 'category', label: 'Категория', state: 'upcoming', description: 'Вас видят компании' },
];

const SAMPLE_FACTORS: ScoreFactor[] = [
  { key: 'test', label: 'Адаптивный тест', value: 0, weight: 0.55, hint: 'Появится после теста' },
  { key: 'tasks', label: 'Микрозадачи', value: 0, weight: 0.2 },
  { key: 'fsp', label: 'Достижения ФСП', value: 0, weight: 0.15, hint: 'Привяжите ФСП ID' },
  { key: 'profile', label: 'Подтверждённость профиля', value: 0.3, weight: 0.1 },
];

export function CandidateHomePage() {
  const { user } = useAuth();
  return (
    <>
      <PageHeader
        kicker="Кабинет специалиста"
        title="Путь к вашей категории"
        description={
          <>
            Вы вошли как <b>{user?.email}</b>. Категория определяется опросом и тестом, а не резюме.
            Как только она появится, работодатели смогут пригласить вас с вилкой зарплаты.
          </>
        }
      />

      <Card mb="lg">
        <Group justify="space-between" mb="lg" wrap="wrap" gap="sm">
          <Title order={4}>Шаги онбординга</Title>
          <Badge color="lilac" variant="light">
            Шаг 2 из 5
          </Badge>
        </Group>
        <StatusTimeline steps={ONBOARDING_STEPS} />
      </Card>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Card>
          <Stack gap="md">
            <Group gap="sm">
              <ThemeIcon color="fsp" variant="light" radius="md" size={36}>
                <IconTargetArrow size={20} />
              </ThemeIcon>
              <Title order={4}>Текущий статус</Title>
            </Group>
            <Text c="dimmed" size="sm">
              Категория пока не присвоена. После теста здесь появится бейдж категории, например:
            </Text>
            <Group gap="xs">
              <CategoryBadge specialization="Backend-разработка" grade="middle" />
              <CategoryBadge specialization="Аналитика данных" grade="junior" size="sm" />
            </Group>
            <VerifiedScoreBar factors={SAMPLE_FACTORS} />
          </Stack>
        </Card>

        <Card>
          <Stack gap="md">
            <Group gap="sm">
              <ThemeIcon color="fsp" variant="light" radius="md" size={36}>
                <IconEyeOff size={20} />
              </ThemeIcon>
              <Title order={4}>Как вас увидит работодатель</Title>
            </Group>
            <Text c="dimmed" size="sm" lh={1.6}>
              До вашего согласия компания видит обезличенную карточку: категорию, подтверждённые
              навыки и индекс профиля. Имя, телефон и email открываются, только когда вы принимаете
              приглашение или откликаетесь сами.
            </Text>
            <Card withBorder radius="md" padding="md" bg="var(--scout-surface-muted)">
              <Group justify="space-between" align="flex-start" wrap="wrap" gap="sm">
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
                  <Text fw={700}>Python-разработчик в команду платежей</Text>
                  <Text size="sm" c="dimmed">
                    Кедр Технологии · гибрид
                  </Text>
                </Stack>
                <SalaryRange from={260000} to={320000} size="sm" />
              </Group>
            </Card>
            <Group gap={8} c="dimmed">
              <IconLock size={16} />
              <Text size="xs">Видимость отдельных полей настраивается в разделе «Приватность»</Text>
            </Group>
          </Stack>
        </Card>
      </SimpleGrid>
    </>
  );
}
