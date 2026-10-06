import {
  Badge,
  Button,
  Card,
  Container,
  Group,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { contrastLevel, contrastRatio } from '@/shared/lib/contrast';
import { GRADE_ORDER } from '@/shared/lib/grades';
import { buildInvitationTimeline, INVITATION_STATUSES } from '@/shared/lib/invitationStatus';
import { salaryRangeError, type SalaryRangeValue } from '@/shared/lib/salary';
import {
  CategoryBadge,
  InvitationStatusBadge,
  Kicker,
  PageHeader,
  SalaryRange,
  SalaryRangeInput,
  StatusTimeline,
  VerifiedScoreBar,
} from '@/shared/ui';
import classes from './DesignSystemPage.module.css';

const PALETTE = [
  {
    name: 'Фирменный фиолетовый',
    hex: '#520978',
    role: 'Основные кнопки, ссылки, активные состояния',
  },
  { name: 'Глубокий фиолетовый', hex: '#310F53', role: 'Тёмные поверхности, градиенты' },
  { name: 'Лавандовый', hex: '#8A83D1', role: 'Вторичные акценты, графики' },
  { name: 'Сигнальный', hex: '#FF0053', role: 'Крупные акценты на тёмном фоне' },
  { name: 'Сигнальный AA', hex: '#D90047', role: 'Сигнальные кнопки с белым текстом' },
  { name: 'Розовый мягкий', hex: '#FFD6E4', role: 'Подложки и выделение' },
  { name: 'Графит', hex: '#1C1D22', role: 'Основной текст' },
];

const SCORE_EXAMPLE = [
  { key: 'test', label: 'Адаптивный тест', value: 0.91, weight: 0.55 },
  {
    key: 'tasks',
    label: 'Микрозадачи',
    value: 0.6,
    weight: 0.2,
    hint: 'Последняя — 12 дней назад',
  },
  { key: 'fsp', label: 'Достижения ФСП', value: 0.8, weight: 0.15 },
  { key: 'profile', label: 'Подтверждённость профиля', value: 1, weight: 0.1 },
];

function Swatch({ name, hex, role }: { name: string; hex: string; role: string }) {
  // Для каждого цвета показываем контраст с белым и с графитом. Так видно, какой
  // текст на нём допустим по WCAG, без проверки на глаз.
  const onWhite = contrastRatio(hex, '#FFFFFF');
  const withInk = contrastRatio(hex, '#1C1D22');
  const textColor = onWhite >= withInk ? '#FFFFFF' : '#1C1D22';
  return (
    <div className={classes.swatch}>
      <div className={classes.swatchColor} style={{ background: hex, color: textColor }}>
        <Text fw={700} size="sm">
          Аа
        </Text>
        <Text size="xs" ff="monospace">
          {hex}
        </Text>
      </div>
      <Stack gap={2} p="sm">
        <Text fw={700} size="sm">
          {name}
        </Text>
        <Text size="xs" c="dimmed" lh={1.4}>
          {role}
        </Text>
        <Text size="xs" ff="monospace" mt={4}>
          белый {onWhite.toFixed(1)}:1 · {contrastLevel(onWhite)}
        </Text>
        <Text size="xs" ff="monospace">
          графит {withInk.toFixed(1)}:1 · {contrastLevel(withInk)}
        </Text>
      </Stack>
    </div>
  );
}

export function DesignSystemPage() {
  const [salary, setSalary] = useState<SalaryRangeValue>({ from: 180000, to: 240000 });
  return (
    <div className={classes.page}>
      <Container size="xl" py={56}>
        <PageHeader
          kicker="Дизайн-система"
          title="Скаут · компоненты и токены"
          description="Палитра ФСП, типографика и универсальные виджеты, из которых собираются кабинеты кандидата и работодателя."
        />

        <Title order={3} mb="md">
          Палитра
        </Title>
        <SimpleGrid cols={{ base: 2, sm: 3, lg: 7 }} spacing="md" mb={48}>
          {PALETTE.map((color) => (
            <Swatch key={color.hex} {...color} />
          ))}
        </SimpleGrid>

        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" mb={48}>
          <Card>
            <Title order={4} mb="md">
              Типографика · Montserrat
            </Title>
            <Stack gap="xs">
              <Title order={1}>Заголовок H1</Title>
              <Title order={2}>Заголовок H2</Title>
              <Title order={3}>Заголовок H3</Title>
              <Text>Основной текст: понятные формулировки, короткие абзацы.</Text>
              <Text size="sm" c="dimmed">
                Вторичный текст, контраст не ниже 4,5:1
              </Text>
              <Text ff="monospace">JetBrains Mono · #A7F3 · θ = 0.84</Text>
            </Stack>
          </Card>
          <Card>
            <Title order={4} mb="md">
              Кнопки, рубрики и поля
            </Title>
            <Stack gap="md">
              <Group gap="sm">
                <Button>Основная</Button>
                <Button color="signal">Сигнальная</Button>
                <Button variant="light">Вторичная</Button>
                <Button variant="default">Нейтральная</Button>
              </Group>
              <Group gap="sm">
                <Kicker>Рубрика</Kicker>
                <Kicker variant="signal">Сигнал</Kicker>
                <Badge color="lilac" variant="light">
                  Бейдж
                </Badge>
              </Group>
              <TextInput label="Поле ввода" placeholder="Плейсхолдер" />
            </Stack>
          </Card>
        </SimpleGrid>

        <Title order={3} mb="md">
          Виджеты подбора
        </Title>
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg" mb="lg">
          <Card>
            <Title order={4} mb="xs">
              Бейдж категории
            </Title>
            <Text size="sm" c="dimmed" mb="md">
              Специализация × грейд. Шкала слева показывает уровень грейда.
            </Text>
            <Stack gap="sm" align="flex-start">
              {GRADE_ORDER.map((grade) => (
                <CategoryBadge key={grade} specialization="Backend-разработка" grade={grade} />
              ))}
              <CategoryBadge specialization="Аналитика данных" grade="junior" size="sm" />
            </Stack>
          </Card>
          <Card>
            <Title order={4} mb="xs">
              Вилка зарплаты
            </Title>
            <Text size="sm" c="dimmed" mb="md">
              Обязательна в приглашении и вакансии, всегда в рублях «от–до».
            </Text>
            <Stack gap="lg">
              <Group gap={40} wrap="wrap">
                <SalaryRange from={220000} to={300000} size="lg" caption="до вычета НДФЛ" />
                <SalaryRange from={90000} to={120000} size="sm" label="Компактно" compact />
              </Group>
              <SalaryRangeInput
                value={salary}
                onChange={setSalary}
                error={salaryRangeError(salary)}
              />
            </Stack>
          </Card>
          <Card>
            <Title order={4} mb="xs">
              Индекс подтверждённого профиля
            </Title>
            <Text size="sm" c="dimmed" mb="md">
              Ширина сегмента — вклад фактора (значение × вес). Подсказка раскрывает расчёт.
            </Text>
            <VerifiedScoreBar factors={SCORE_EXAMPLE} />
          </Card>
          <Card>
            <Title order={4} mb="xs">
              Таймлайн статусов приглашения
            </Title>
            <Text size="sm" c="dimmed" mb="md">
              Одинаковый для кандидата и работодателя: обе стороны видят актуальный статус.
            </Text>
            <Stack gap="lg">
              {INVITATION_STATUSES.map((status) => (
                <Stack key={status} gap={8}>
                  <InvitationStatusBadge status={status} />
                  <StatusTimeline
                    steps={buildInvitationTimeline(status, {
                      sentAt: '2026-10-06T10:15:00+03:00',
                      viewedAt: status === 'sent' ? null : '2026-10-06T12:40:00+03:00',
                      respondedAt: ['accepted', 'declined', 'withdrawn', 'expired'].includes(status)
                        ? '2026-10-07T09:05:00+03:00'
                        : null,
                    })}
                    orientation="horizontal"
                  />
                </Stack>
              ))}
            </Stack>
          </Card>
        </SimpleGrid>
      </Container>
    </div>
  );
}
