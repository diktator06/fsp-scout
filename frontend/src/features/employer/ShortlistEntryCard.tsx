import { ActionIcon, Badge, Button, Card, Group, Stack, Text, Tooltip } from '@mantine/core';
import { IconEyeOff, IconMail, IconPin, IconPinnedFilled } from '@tabler/icons-react';
import { Link } from 'react-router';
import type { ShortlistEntry, ShortlistMark } from '@/api/types';
import { PENALTY_LABELS } from '@/shared/lib/matching';
import { MatchScore, SkillMatchChips, VerifiedScoreBar, WhyInShortlist } from '@/shared/ui';
import { CandidateSummary } from './CandidateSummary';
import classes from './ShortlistEntryCard.module.css';

interface ShortlistEntryCardProps {
  entry: ShortlistEntry;
  needId: string;
  onMark: (mark: ShortlistMark | null) => void;
  onInvite: () => void;
  marking?: boolean;
}

export function ShortlistEntryCard({
  entry,
  needId,
  onMark,
  onInvite,
  marking,
}: ShortlistEntryCardProps) {
  // Строка подборки: кто это, насколько подходит и почему. Разложение балла и список
  // причин строятся из тех же чисел, по которым кандидат получил своё место.
  const { card, match } = entry;
  const pinned = entry.mark === 'pinned';
  const activeInvitation =
    entry.invitation && ['sent', 'viewed', 'accepted'].includes(entry.invitation.status);
  return (
    <Card className={classes.card} data-pinned={pinned || undefined}>
      <div className={classes.grid}>
        <Stack gap={4} align="center" className={classes.rank}>
          <Text size="xs" c="dimmed" fw={700} className="tabular">
            #{entry.rank}
          </Text>
          <MatchScore score={match.score} />
        </Stack>
        <Stack gap="md" className={classes.main}>
          <CandidateSummary
            card={card}
            invitation={entry.invitation}
            contactsDisclosed={Boolean(entry.contacts)}
          />
          {(entry.outside_filters || match.penalties.length > 0) && (
            <Group gap={6}>
              {entry.outside_filters && (
                <Badge color="lilac" variant="outline">
                  закреплён, не проходит новые фильтры
                </Badge>
              )}
              {match.penalties.map((code) => (
                <Badge key={code} color="gray" variant="light">
                  ниже в выдаче: {PENALTY_LABELS[code] ?? code}
                </Badge>
              ))}
            </Group>
          )}
          <SkillMatchChips
            skills={match.skills.map((item) => ({
              id: item.skill.id,
              name: item.skill.name,
              status: item.status as 'verified' | 'declared' | 'related' | 'missing',
              importance: item.importance,
              via: item.via?.name,
            }))}
          />
          <div className={classes.explain}>
            <VerifiedScoreBar
              title="Из чего сложился балл"
              score={Math.round(match.score)}
              factors={match.components.map((component) => ({
                key: component.key,
                label: component.label,
                value: component.value,
                weight: component.weight,
              }))}
              compact
            />
            <WhyInShortlist items={match.explanation} limit={6} />
          </div>
          {entry.contacts && (
            <Text size="sm" className={classes.contacts}>
              {entry.contacts.full_name} ·{' '}
              {[entry.contacts.telegram, entry.contacts.email, entry.contacts.phone]
                .filter(Boolean)
                .join(' · ')}
            </Text>
          )}
          <Group gap="sm" wrap="wrap">
            <Button
              size="sm"
              leftSection={<IconMail size={16} />}
              onClick={onInvite}
              disabled={Boolean(activeInvitation)}
            >
              {activeInvitation ? 'Приглашение отправлено' : 'Пригласить'}
            </Button>
            <Button
              size="sm"
              variant="default"
              component={Link}
              to={`/e/candidates/${card.candidate_id}?need=${needId}`}
            >
              Открыть карточку
            </Button>
            <Group gap={4} ml="auto">
              <Tooltip label={pinned ? 'Открепить' : 'Закрепить: останется при уточнении фильтров'}>
                <ActionIcon
                  variant={pinned ? 'filled' : 'subtle'}
                  color="fsp"
                  loading={marking}
                  onClick={() => onMark(pinned ? null : 'pinned')}
                  aria-label={pinned ? 'Открепить' : 'Закрепить'}
                >
                  {pinned ? <IconPinnedFilled size={18} /> : <IconPin size={18} />}
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Скрыть из следующих версий подборки">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  loading={marking}
                  onClick={() => onMark('hidden')}
                  aria-label="Скрыть"
                >
                  <IconEyeOff size={18} />
                </ActionIcon>
              </Tooltip>
            </Group>
          </Group>
        </Stack>
      </div>
    </Card>
  );
}
