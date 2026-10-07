import { Badge, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconLock, IconLockOpen, IconMail } from '@tabler/icons-react';
import type { CandidateCardView, FspState } from '@/api/types';
import { FspCardBlock } from '@/features/fsp/FspCardBlock';
import { competencyShare } from '@/shared/lib/assessment';
import { formatDateTime } from '@/shared/lib/format';
import { MatchScore, SkillMatchChips, VerifiedScoreBar, WhyInShortlist } from '@/shared/ui';
import { CandidateSummary } from './CandidateSummary';
import classes from './CandidateProfileView.module.css';

interface CandidateProfileViewProps {
  view: CandidateCardView;
  onInvite: () => void;
}

const FSP_HINTS: Record<FspState, string | undefined> = {
  not_linked: 'ФСП ID не привязан',
  linked_empty: 'Привязан, участий пока нет',
  hidden: 'Скрыто кандидатом',
  linked: undefined,
};

function monthYear(value: string | null | undefined): string {
  // «сен 2024» для периодов работы.
  if (!value) return 'по настоящее время';
  return new Intl.DateTimeFormat('ru-RU', { month: 'short', year: 'numeric' }).format(
    new Date(value),
  );
}

export function CandidateProfileView({ view, onInvite }: CandidateProfileViewProps) {
  // Полная обезличенная карточка. Контакты — отдельным блоком и только после согласия
  // кандидата: до этого на их месте объяснение, как их получить.
  const { card, contacts, match, invitation } = view;
  const activeInvitation = invitation && ['sent', 'viewed', 'accepted'].includes(invitation.status);
  return (
    <Stack gap="lg">
      <Card>
        <Stack gap="lg">
          <CandidateSummary
            card={card}
            invitation={invitation}
            contactsDisclosed={Boolean(contacts)}
          />
          {contacts ? (
            <div className={classes.contacts}>
              <Group gap={8} mb={6}>
                <IconLockOpen size={18} />
                <Text fw={700}>Контакты открыты {formatDateTime(contacts.disclosed_at)}</Text>
              </Group>
              <Text fw={700} size="lg">
                {contacts.full_name}
              </Text>
              <Group gap="lg" mt={4}>
                {contacts.telegram && <Text>Telegram: {contacts.telegram}</Text>}
                {contacts.email && <Text>Email: {contacts.email}</Text>}
                {contacts.phone && <Text>Телефон: {contacts.phone}</Text>}
              </Group>
            </div>
          ) : (
            <Group gap="sm" className={classes.locked} wrap="nowrap" align="flex-start">
              <IconLock size={20} />
              <Text size="sm">
                Имя и контакты скрыты. Они откроются, когда кандидат примет ваше приглашение, — с
                вилкой зарплаты и описанием предложения.
              </Text>
            </Group>
          )}
          <Group>
            <Button
              leftSection={<IconMail size={16} />}
              onClick={onInvite}
              disabled={Boolean(activeInvitation)}
            >
              {activeInvitation ? 'Приглашение уже отправлено' : 'Пригласить'}
            </Button>
          </Group>
        </Stack>
      </Card>

      {match && (
        <Card>
          <Stack gap="md">
            <Group gap="md">
              <MatchScore score={match.score} size={72} />
              <div>
                <Title order={4}>Соответствие потребности</Title>
                <Text size="sm" c="dimmed">
                  Навыки, подтверждённость, близость опыта к задачам и условия
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
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
              <VerifiedScoreBar
                title="Из чего сложился балл"
                score={Math.round(match.score)}
                factors={match.components.map((item) => ({
                  key: item.key,
                  label: item.label,
                  value: item.value,
                  weight: item.weight,
                }))}
              />
              <WhyInShortlist items={match.explanation} />
            </SimpleGrid>
          </Stack>
        </Card>
      )}

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Card>
          <Stack gap="md">
            <VerifiedScoreBar
              score={Math.round(card.verified_score.total)}
              factors={card.verified_score.components.map((item) => ({
                key: item.key,
                label: item.label,
                value: item.value,
                weight: item.weight,
                hint:
                  item.key === 'fsp'
                    ? FSP_HINTS[card.fsp.state]
                    : item.key === 'micro_tasks' && item.value === 0
                      ? 'Микрозадач пока не было'
                      : undefined,
              }))}
            />
          </Stack>
        </Card>
        <Card>
          <Stack gap="md">
            <Group justify="space-between">
              <Title order={4}>Тест</Title>
              {card.test && (
                <Text size="sm" c="dimmed">
                  {formatDateTime(card.test.finished_at)} · {card.test.items} заданий
                  {card.test.mode === 'express' ? ' · экспресс' : ''}
                </Text>
              )}
            </Group>
            {card.test ? (
              <>
                {card.test.percentile != null && (
                  <Text size="sm">
                    <b>{card.test.percentile}-й перцентиль</b> среди подтверждённых в категории
                  </Text>
                )}
                <ul className={classes.competencies}>
                  {card.test.competencies.map((item) => {
                    const share = competencyShare(item.correct, item.answered);
                    return (
                      <li key={item.code}>
                        <span>{item.name}</span>
                        <span className="tabular">
                          {Math.round(item.correct)} из {item.answered}
                        </span>
                        <span className={classes.bar} aria-hidden="true">
                          <span style={{ width: `${share}%` }} />
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </>
            ) : (
              <Text size="sm" c="dimmed">
                Грейд заявлен, но тест ещё не пройден — категория не подтверждена.
              </Text>
            )}
          </Stack>
        </Card>
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Card>
          <Stack gap="md">
            <Title order={4}>Навыки</Title>
            <Group gap={6}>
              {card.skills.map((skill) => (
                <Badge
                  key={skill.id}
                  variant={skill.verified ? 'filled' : 'light'}
                  color={skill.verified ? 'teal' : 'fsp'}
                  tt="none"
                >
                  {skill.verified ? '✓ ' : ''}
                  {skill.name}
                </Badge>
              ))}
            </Group>
            {card.about && (
              <Text size="sm" lh={1.6} className={classes.about}>
                {card.about}
              </Text>
            )}
          </Stack>
        </Card>
        <Card>
          <Stack gap="md">
            <Title order={4}>Опыт</Title>
            {card.experiences.length === 0 && (
              <Text size="sm" c="dimmed">
                Места работы не указаны
              </Text>
            )}
            {card.experiences.map((job, index) => (
              <div key={`${job.position}-${index}`}>
                <Text fw={700}>{job.position}</Text>
                <Text size="sm" c="dimmed">
                  {job.company_name ?? 'Название компании скрыто'} · {monthYear(job.started_on)} —{' '}
                  {monthYear(job.ended_on)}
                </Text>
                {job.description && (
                  <Text size="sm" mt={4}>
                    {job.description}
                  </Text>
                )}
              </div>
            ))}
          </Stack>
        </Card>
      </SimpleGrid>

      <FspCardBlock fsp={card.fsp} />
    </Stack>
  );
}
