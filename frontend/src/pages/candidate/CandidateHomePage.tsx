import {
  Badge,
  Button,
  Card,
  Group,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconArrowRight, IconEyeOff, IconLock, IconTargetArrow } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useCandidateStatus } from '@/api/candidate';
import { errorMessage } from '@/api/errors';
import type { CandidateStatus } from '@/api/types';
import { useAuth } from '@/features/auth/useAuth';
import { GRADE_STATUS_COPY } from '@/shared/lib/candidate';
import type { TimelineStep } from '@/shared/lib/invitationStatus';
import {
  CategoryBadge,
  ErrorState,
  LoadingState,
  PageHeader,
  SalaryRange,
  StatusTimeline,
} from '@/shared/ui';

const STEP_ORDER = ['profile', 'survey', 'grade', 'test', 'done'] as const;

function buildTimeline(status: CandidateStatus): TimelineStep[] {
  // Шаг «тест» объединяет выбор уровня и прохождение: для кандидата это одно действие.
  const position = STEP_ORDER.indexOf(status.onboarding_step);
  const stateOf = (index: number): TimelineStep['state'] =>
    position > index ? 'done' : position === index ? 'current' : 'upcoming';
  const testIndex = status.onboarding_step === 'test' ? 3 : 2;
  return [
    { key: 'account', label: 'Аккаунт', state: 'done', description: 'Email подтверждён' },
    { key: 'profile', label: 'О себе', state: stateOf(0), description: 'Имя, опыт, формат' },
    { key: 'survey', label: 'Опрос', state: stateOf(1), description: 'Специализация и стек' },
    {
      key: 'test',
      label: 'Тест на грейд',
      state: status.onboarding_step === 'done' ? 'done' : stateOf(testIndex),
      description: 'Адаптивный, 12–20 заданий',
    },
    {
      key: 'category',
      label: 'Категория',
      state: status.onboarding_step === 'done' ? 'success' : 'upcoming',
      description: 'Вас видят компании',
    },
  ];
}

function NextAction({ status }: { status: CandidateStatus }) {
  // Одна главная кнопка под текущий шаг: человеку не нужно искать, что делать дальше.
  const actions: Record<
    CandidateStatus['onboarding_step'],
    { text: string; to: string; label: string }
  > = {
    profile: {
      text: 'Начните с пары фактов о себе — это займёт минуту.',
      to: '/c/onboarding',
      label: 'Заполнить',
    },
    survey: {
      text: 'Расскажите о стеке: из него соберём тест под вашу специализацию.',
      to: '/c/onboarding',
      label: 'Пройти опрос',
    },
    grade: {
      text: 'Всё готово к тесту. Выберите уровень и режим.',
      to: '/c/onboarding',
      label: 'Выбрать тест',
    },
    test: {
      text: 'У вас есть незавершённый тест.',
      to: status.active_session_id
        ? `/c/assessment/sessions/${status.active_session_id}`
        : '/c/assessment',
      label: 'Продолжить тест',
    },
    done: {
      text: 'Категория подтверждена. Следующий уровень — тестом в разделе «Категория и тест».',
      to: '/c/assessment',
      label: 'Открыть раздел',
    },
  };
  const action = actions[status.onboarding_step];
  return (
    <Group justify="space-between" wrap="wrap" gap="md" mt="lg">
      <Text size="sm" c="dimmed">
        {action.text}
      </Text>
      <Button component={Link} to={action.to} rightSection={<IconArrowRight size={16} />}>
        {action.label}
      </Button>
    </Group>
  );
}

export function CandidateHomePage() {
  const { user } = useAuth();
  const status = useCandidateStatus();

  const header = (
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
  );

  if (status.isPending) {
    return (
      <>
        {header}
        <LoadingState />
      </>
    );
  }
  if (status.isError) {
    return (
      <>
        {header}
        <ErrorState message={errorMessage(status.error)} onRetry={() => void status.refetch()} />
      </>
    );
  }

  const data = status.data;
  const gradeCopy = GRADE_STATUS_COPY[data.grade_status];
  const category = data.category ?? data.claimed_category;
  const doneSteps = buildTimeline(data).filter(
    (step) => step.state === 'done' || step.state === 'success',
  ).length;

  return (
    <>
      {header}
      <Card mb="lg">
        <Group justify="space-between" mb="lg" wrap="wrap" gap="sm">
          <Title order={4}>Шаги онбординга</Title>
          <Badge color="lilac" variant="light">
            {doneSteps} из 5
          </Badge>
        </Group>
        <StatusTimeline steps={buildTimeline(data)} />
        <NextAction status={data} />
      </Card>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Card>
          <Stack gap="md">
            <Group justify="space-between" wrap="wrap" gap="sm">
              <Group gap="sm">
                <ThemeIcon color="fsp" variant="light" radius="md" size={36}>
                  <IconTargetArrow size={20} />
                </ThemeIcon>
                <Title order={4}>Текущий статус</Title>
              </Group>
              <Badge color={gradeCopy.color} variant="light">
                {gradeCopy.label}
              </Badge>
            </Group>
            {category ? (
              <CategoryBadge
                specialization={category.specialization.name}
                grade={category.grade.code}
                gradeLabel={category.grade.name}
                unconfirmed={data.grade_status !== 'confirmed'}
              />
            ) : (
              <Text c="dimmed" size="sm">
                Категория пока не заявлена. После опроса здесь появится грейд с пометкой «не
                подтверждён», после теста — подтверждённая категория.
              </Text>
            )}
            <Stack gap={6}>
              <Group justify="space-between">
                <Text size="sm" fw={600}>
                  Профиль заполнен
                </Text>
                <Text size="sm" fw={700} className="tabular">
                  {data.completeness}%
                </Text>
              </Group>
              <Progress
                value={data.completeness}
                color="fsp"
                size="md"
                radius="xl"
                aria-label="Заполненность профиля"
              />
            </Stack>
            <Group gap={8}>
              <Badge color={data.bank_published ? 'teal' : 'gray'} variant="dot">
                {data.bank_published ? 'Опубликован в банке кандидатов' : 'Не опубликован в банке'}
              </Badge>
              {!data.bank_published && (
                <Button component={Link} to="/c/settings" variant="subtle" size="compact-sm">
                  Включить
                </Button>
              )}
            </Group>
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
