import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconSend } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import type { VacancyPublic } from '@/api/types';
import { useApply, usePublicVacancy } from '@/api/vacancies';
import { CompanyCard } from '@/features/vacancies/CompanyCard';
import { WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import {
  ApplicationStatusBadge,
  ErrorState,
  LoadingState,
  MatchScore,
  SalaryRange,
  SkillMatchChips,
  WhyInShortlist,
} from '@/shared/ui';
import classes from './InvitationPage.module.css';

function ApplyCard({ vacancy }: { vacancy: VacancyPublic }) {
  // Отклик — собственная инициатива кандидата, поэтому он открывает компании контакты.
  // Согласие на это даётся явно, отдельной галочкой.
  const apply = useApply(vacancy.id);
  const [letter, setLetter] = useState('');
  const [consent, setConsent] = useState(false);
  if (vacancy.application) {
    return (
      <Card>
        <Stack gap="sm">
          <Group justify="space-between">
            <Title order={4}>Вы откликнулись</Title>
            <ApplicationStatusBadge status={vacancy.application.status} />
          </Group>
          <Text size="sm" c="dimmed">
            Статус отклика и ответ компании — в разделе{' '}
            <Anchor component={Link} to="/c/applications">
              «Мои отклики»
            </Anchor>
            .
          </Text>
        </Stack>
      </Card>
    );
  }
  const submit = () =>
    apply.mutate(
      { cover_letter: letter, share_contacts: consent },
      {
        onSuccess: () =>
          notifications.show({
            color: 'teal',
            title: 'Отклик отправлен',
            message: `${vacancy.company.name} видит вашу карточку и контакты`,
          }),
      },
    );
  return (
    <Card>
      <Stack gap="md">
        <Title order={4}>Откликнуться</Title>
        <Textarea
          label="Сопроводительное письмо"
          description="Необязательно: пара фраз о том, почему вам интересна эта команда"
          autosize
          minRows={3}
          maxLength={3000}
          value={letter}
          onChange={(event) => setLetter(event.currentTarget.value)}
        />
        <Checkbox
          checked={consent}
          onChange={(event) => setConsent(event.currentTarget.checked)}
          label={`Открыть компании «${vacancy.company.name}» моё имя и контакты из настроек приватности`}
          description="Без отклика компания видит только обезличенную карточку"
        />
        {apply.isError && (
          <Alert color="signal" variant="light">
            {errorMessage(apply.error)}
          </Alert>
        )}
        <Group>
          <Button
            leftSection={<IconSend size={16} />}
            disabled={!consent}
            loading={apply.isPending}
            onClick={submit}
          >
            Отправить отклик
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function MatchCard({ vacancy }: { vacancy: VacancyPublic }) {
  // Кандидат видит то же объяснение, что и работодатель, — только от своего лица.
  if (!vacancy.match) {
    return (
      <Card>
        <Text size="sm" c="dimmed">
          Соответствие появится после опроса о стеке:{' '}
          <Anchor component={Link} to="/c/onboarding">
            пройти опрос
          </Anchor>
          .
        </Text>
      </Card>
    );
  }
  const match = vacancy.match;
  return (
    <Card>
      <Stack gap="md">
        <Group gap="md">
          <MatchScore score={match.score} size={72} />
          <div>
            <Title order={4}>Насколько вам подходит</Title>
            <Text size="sm" c="dimmed">
              Те же правила, по которым компания видит кандидатов
            </Text>
          </div>
        </Group>
        <SkillMatchChips
          skills={match.skills.map((item) => ({
            id: item.skill.id,
            name: item.skill.name,
            status: item.status as 'verified' | 'declared' | 'related' | 'missing',
            importance: item.importance,
            via: item.via?.name,
          }))}
        />
        <WhyInShortlist items={match.explanation} title="Почему подходит и чего не хватает" />
      </Stack>
    </Card>
  );
}

export function VacancyPage() {
  const { vacancyId = '' } = useParams();
  const vacancy = usePublicVacancy(vacancyId);
  if (vacancy.isPending) return <LoadingState />;
  if (vacancy.isError) {
    return (
      <ErrorState message={errorMessage(vacancy.error)} onRetry={() => void vacancy.refetch()} />
    );
  }
  const data = vacancy.data;
  const formats = data.work_formats.map((item) => WORK_FORMAT_LABELS[item]).join(', ');
  return (
    <Stack gap="lg">
      <section className={classes.hero}>
        <Stack gap={6} className={classes.heroTitle}>
          <Text className={classes.company}>{data.company.name}</Text>
          <Title order={2} c="white">
            {data.title}
          </Title>
          <Text c="rgba(255,255,255,0.82)" size="sm">
            {data.specialization.name} · {data.grades.map((grade) => grade.name).join(', ')} ·{' '}
            {formats}
            {data.city ? ` · ${data.city}` : ''}
          </Text>
        </Stack>
        <SalaryRange
          from={data.salary_from}
          to={data.salary_to}
          tone="dark"
          size="lg"
          caption={data.salary_gross ? 'до вычета НДФЛ' : 'на руки'}
        />
      </section>
      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="lg">
        <Card className={classes.offer}>
          <Stack gap="md">
            <Title order={4}>О вакансии</Title>
            <Text lh={1.65} className={classes.text}>
              {data.description}
            </Text>
            <Group gap={6}>
              {data.skills.map((item) => (
                <Badge
                  key={item.skill.id}
                  variant={item.importance === 'must' ? 'light' : 'outline'}
                  color="fsp"
                  tt="none"
                >
                  {item.skill.name}
                  {item.importance === 'nice' ? ' · плюс' : ''}
                </Badge>
              ))}
            </Group>
          </Stack>
        </Card>
        <CompanyCard
          company={data.company}
          complaint={{ targetType: 'vacancy', targetId: data.id }}
        />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <MatchCard vacancy={data} />
        <ApplyCard vacancy={data} />
      </SimpleGrid>
    </Stack>
  );
}
