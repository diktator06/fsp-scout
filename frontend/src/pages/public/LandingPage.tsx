import { Box, Button, Container, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import {
  IconArrowRight,
  IconCircleCheckFilled,
  IconCurrencyRubel,
  IconEyeOff,
  IconLock,
  IconTargetArrow,
  IconTrophy,
  type Icon,
} from '@tabler/icons-react';
import { Link } from 'react-router';
import { buildInvitationTimeline } from '@/shared/lib/invitationStatus';
import { type ScoreFactor } from '@/shared/lib/score';
import {
  CategoryBadge,
  ConstellationBackdrop,
  FspLogo,
  Kicker,
  SalaryRange,
  StatusTimeline,
  VerifiedScoreBar,
} from '@/shared/ui';
import classes from './LandingPage.module.css';

const PREVIEW_FACTORS: ScoreFactor[] = [
  { key: 'test', label: 'Адаптивный тест', value: 0.86, weight: 0.55 },
  { key: 'tasks', label: 'Микрозадачи', value: 0, weight: 0.2 },
  { key: 'fsp', label: 'Достижения ФСП', value: 0.8, weight: 0.15 },
  { key: 'profile', label: 'Подтверждённость профиля', value: 0.9, weight: 0.1 },
];

const PREVIEW_SKILLS: Array<{ name: string; verified: boolean }> = [
  { name: 'Python', verified: true },
  { name: 'FastAPI', verified: true },
  { name: 'PostgreSQL', verified: true },
  { name: 'Docker', verified: false },
  { name: 'Kafka', verified: false },
];

const PRINCIPLES: Array<{ icon: Icon; title: string; text: string }> = [
  {
    icon: IconTargetArrow,
    title: 'Категория по результату, а не по резюме',
    text: 'Опрос, выбор грейда и адаптивный тест определяют категорию, в которой вас видят работодатели. Задания у каждого свои, а сложность сопоставима.',
  },
  {
    icon: IconCurrencyRubel,
    title: 'Вилка зарплаты — обязательное поле',
    text: 'В каждом приглашении и вакансии указана зарплата «от–до». Условия известны до первого сообщения, торговаться вслепую не придётся.',
  },
  {
    icon: IconEyeOff,
    title: 'Контакты — только по вашему решению',
    text: 'До вашего согласия работодатель видит обезличенную карточку: категорию, подтверждённые навыки и результаты. Имя и телефон открываются после ответа.',
  },
  {
    icon: IconTrophy,
    title: 'Достижения ФСП в профиле',
    text: 'Результаты соревнований подтягиваются из реестра Федерации и поднимают вас внутри категории. Нет истории ФСП — профиль оценивается по тестам и задачам.',
  },
];

const CANDIDATE_TRACK = [
  ['Профиль', 'Заполните форму или загрузите PDF-резюме: поля распознаются автоматически.'],
  ['Опрос', 'Отрасль, специализация, стек и опыт — из этого собирается ваш тест.'],
  ['Грейд', 'Выберите уровень, на который претендуете: Intern, Junior, Middle или Senior.'],
  ['Тест', 'Задания подстраиваются под ответы, каждый экземпляр уникален.'],
  ['Категория', 'Вас находят компании, которым нужна именно такая команда.'],
] as const;

const EMPLOYER_TRACK = [
  ['Компания', 'Коротко о себе: чем занимаетесь и как с вами связаться.'],
  ['Потребность', 'Опишите задачу и стек обычным текстом — система разберёт его на требования.'],
  ['Подборка', 'Рекомендованные категории и кандидаты с объяснением, почему они подходят.'],
  ['Приглашение', 'Описание предложения и вилка зарплаты конкретному человеку.'],
  ['Контакт', 'Кандидат принял приглашение — вы получаете его контакты.'],
] as const;

function Assurance({ icon: IconComponent, children }: { icon: Icon; children: string }) {
  return (
    <Group gap={8} wrap="nowrap" className={classes.assurance}>
      <IconComponent size={18} stroke={1.8} />
      <Text size="sm">{children}</Text>
    </Group>
  );
}

function HeroPreview() {
  // Превью собрано из тех же виджетов, что и кабинеты, а не из картинки: лендинг
  // заодно показывает дизайн-систему продукта в работе.
  return (
    <div className={classes.preview} aria-label="Пример карточки кандидата и приглашения">
      <div className={classes.previewCard}>
        <Group justify="space-between" align="flex-start" gap="sm" wrap="nowrap">
          <Group gap={12} wrap="nowrap">
            <span className={classes.anonymousAvatar} aria-hidden="true">
              A7
            </span>
            <Stack gap={2}>
              <Text fw={700} c="white" className={classes.mono}>
                Кандидат #A7F3
              </Text>
              <Text size="xs" c="rgba(255,255,255,0.7)">
                Казань · удалённо · опыт 3 года
              </Text>
            </Stack>
          </Group>
          <Kicker variant="ghost">Пример</Kicker>
        </Group>
        <Box mt="md">
          <CategoryBadge specialization="Backend-разработка" grade="middle" tone="dark" size="sm" />
        </Box>
        <Group gap={6} mt="md">
          {PREVIEW_SKILLS.map((skill) => (
            <span
              key={skill.name}
              className={classes.skill}
              data-verified={skill.verified || undefined}
            >
              {skill.verified && <IconCircleCheckFilled size={13} />}
              {skill.name}
            </span>
          ))}
        </Group>
        <Box mt="lg">
          <VerifiedScoreBar factors={PREVIEW_FACTORS} tone="dark" compact />
        </Box>
        <Group gap={8} mt="md" wrap="nowrap" className={classes.fspLine}>
          <IconTrophy size={16} />
          <Text size="xs">
            Призёр всероссийских соревнований по продуктовому программированию, 2025
          </Text>
        </Group>
      </div>

      <div className={classes.ticket}>
        <Group justify="space-between" align="center" gap="xs">
          <Text size="xs" fw={700} tt="uppercase" className={classes.ticketLabel}>
            Приглашение
          </Text>
          <Text size="xs" c="rgba(255,255,255,0.7)">
            Кедр Технологии
          </Text>
        </Group>
        <Text fw={700} c="white" mt={6} lh={1.35}>
          Python-разработчик в команду платежей
        </Text>
        <Box mt="sm">
          <SalaryRange from={260000} to={320000} tone="dark" size="md" label="Вилка до НДФЛ" />
        </Box>
        <Box mt="md">
          <StatusTimeline
            steps={buildInvitationTimeline('viewed')}
            orientation="horizontal"
            tone="dark"
          />
        </Box>
      </div>
    </div>
  );
}

function Track({
  kicker,
  title,
  steps,
  cta,
}: {
  kicker: string;
  title: string;
  steps: ReadonlyArray<readonly [string, string]>;
  cta: { to: string; label: string };
}) {
  return (
    <div className={classes.track}>
      <Kicker>{kicker}</Kicker>
      <Title order={3} mt="sm" mb="lg">
        {title}
      </Title>
      <ol className={classes.trackList}>
        {steps.map(([stepTitle, text], index) => (
          <li key={stepTitle} className={classes.trackStep}>
            <span className={classes.trackNumber}>{String(index + 1).padStart(2, '0')}</span>
            <div>
              <Text fw={700}>{stepTitle}</Text>
              <Text size="sm" c="dimmed" lh={1.55}>
                {text}
              </Text>
            </div>
          </li>
        ))}
      </ol>
      <Button
        component={Link}
        to={cta.to}
        mt="lg"
        variant="light"
        rightSection={<IconArrowRight size={16} />}
      >
        {cta.label}
      </Button>
    </div>
  );
}

export function LandingPage() {
  return (
    <>
      <section className={classes.hero}>
        <ConstellationBackdrop seed={7} nodes={40} highlight={3} fade="left" />
        <Container size="xl" className={classes.heroInner}>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={56} verticalSpacing={48}>
            <Stack gap="xl" justify="center">
              <Kicker variant="ghost">Подбор ИТ-специалистов · ФСП</Kicker>
              <Title order={1} c="white" className={classes.heroTitle}>
                Компании приходят к вам — <span className={classes.accent}>сразу с зарплатой</span>
              </Title>
              <Text className={classes.lead}>
                Скаут распределяет специалистов по категориям на основе теста и подтверждённых
                достижений в спортивном программировании. Работодатель находит нужную категорию и
                приглашает конкретного человека — вилка указана с первой строки.
              </Text>
              <Group gap="sm">
                <Button
                  size="lg"
                  color="signal"
                  component={Link}
                  to="/auth/register?role=candidate"
                  rightSection={<IconArrowRight size={18} />}
                >
                  Я специалист
                </Button>
                <Button
                  size="lg"
                  variant="white"
                  component={Link}
                  to="/auth/register?role=employer"
                >
                  Я ищу в команду
                </Button>
              </Group>
              <Group gap="xl">
                <Assurance icon={IconLock}>Контакты — после вашего согласия</Assurance>
                <Assurance icon={IconCurrencyRubel}>Вилка в каждом приглашении</Assurance>
              </Group>
            </Stack>
            <HeroPreview />
          </SimpleGrid>
        </Container>
      </section>

      <section id="principles" className={classes.section}>
        <Container size="xl">
          <Stack gap="xs" mb={40} maw={720}>
            <Kicker>Принципы</Kicker>
            <Title order={2}>Обратная механика: инициатива у работодателя, решение — у вас</Title>
          </Stack>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="lg">
            {PRINCIPLES.map((principle) => (
              <div key={principle.title} className={classes.principle}>
                <span className={classes.principleIcon}>
                  <principle.icon size={22} stroke={1.8} />
                </span>
                <Text fw={700} size="lg" lh={1.3} mt="md">
                  {principle.title}
                </Text>
                <Text size="sm" c="dimmed" mt="xs" lh={1.6}>
                  {principle.text}
                </Text>
              </div>
            ))}
          </SimpleGrid>
        </Container>
      </section>

      <section id="tracks" className={classes.sectionMuted}>
        <Container size="xl">
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={32}>
            <Track
              kicker="Путь специалиста"
              title="Пять шагов до категории"
              steps={CANDIDATE_TRACK}
              cta={{ to: '/auth/register?role=candidate', label: 'Создать профиль' }}
            />
            <Track
              kicker="Путь работодателя"
              title="От описания задачи до контакта"
              steps={EMPLOYER_TRACK}
              cta={{ to: '/auth/register?role=employer', label: 'Найти специалистов' }}
            />
          </SimpleGrid>
        </Container>
      </section>

      <section id="fsp" className={classes.fspBand}>
        <ConstellationBackdrop seed={41} nodes={28} highlight={2} fade="left" />
        <Container size="xl" className={classes.fspInner}>
          <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48}>
            <Stack gap="lg">
              <FspLogo tone="light" height={34} />
              <Title order={2} c="white">
                Спортивный опыт — карьерное преимущество
              </Title>
              <Text c="rgba(255,255,255,0.8)" lh={1.65}>
                Привяжите ФСП ID, и результаты соревнований появятся в профиле с отметкой реестра
                Федерации: уровень соревнования, место, дисциплина и роль в команде. Работодатель
                получает объективный ориентир, вы — заметное место в категории.
              </Text>
              <Text size="sm" c="rgba(255,255,255,0.7)">
                Ещё не участвовали в соревнованиях? Ничего страшного: категория и индекс профиля
                строятся по тесту и решённым задачам.
              </Text>
            </Stack>
            <div className={classes.achievements}>
              {[
                ['Всероссийские соревнования', 'Продуктовое программирование · призёр', '2025'],
                ['Региональный хакатон', 'Алгоритмическое программирование · 1 место', '2024'],
                ['Кубок вузов', 'Командный зачёт · капитан', '2024'],
              ].map(([event, result, year]) => (
                <div key={event} className={classes.achievement}>
                  <IconTrophy size={20} />
                  <div>
                    <Text fw={700} c="white" size="sm">
                      {event}
                    </Text>
                    <Text size="xs" c="rgba(255,255,255,0.72)">
                      {result}
                    </Text>
                  </div>
                  <Text size="xs" c="rgba(255,255,255,0.72)" className={classes.mono}>
                    {year}
                  </Text>
                </div>
              ))}
              <Group gap={6} mt="xs">
                <IconCircleCheckFilled size={14} color="#19c39a" />
                <Text size="xs" c="rgba(255,255,255,0.75)">
                  Подтверждено реестром ФСП
                </Text>
              </Group>
            </div>
          </SimpleGrid>
        </Container>
      </section>

      <section className={classes.section}>
        <Container size="md">
          <Stack align="center" gap="lg" ta="center">
            <Title order={2}>Начните с категории — остальное сделает подбор</Title>
            <Text c="dimmed" maw={560}>
              Регистрация занимает минуту. Подтвердите email, пройдите опрос и тест — и вы в базе,
              где работодатели ищут людей по результатам.
            </Text>
            <Group gap="sm" justify="center">
              <Button size="lg" component={Link} to="/auth/register?role=candidate">
                Зарегистрироваться
              </Button>
              <Button size="lg" variant="default" component={Link} to="/auth/login">
                У меня есть аккаунт
              </Button>
            </Group>
          </Stack>
        </Container>
      </section>
    </>
  );
}
