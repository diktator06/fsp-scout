import { Badge, Group, Stack, Text } from '@mantine/core';
import { IconLockOpen, IconMapPin } from '@tabler/icons-react';
import type { CandidateCard, InvitationBrief } from '@/api/types';
import { WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import { formatRub, pluralizeRu } from '@/shared/lib/format';
import { AnonymousAvatar, CategoryBadge, InvitationStatusBadge } from '@/shared/ui';
import classes from './CandidateSummary.module.css';

interface CandidateSummaryProps {
  card: CandidateCard;
  invitation?: InvitationBrief | null;
  contactsDisclosed?: boolean;
}

function years(value: number | null | undefined): string | null {
  // Стаж словами: «3 года», «1,5 года».
  if (value == null) return null;
  if (!Number.isInteger(value)) return `${String(value).replace('.', ',')} года`;
  return `${value} ${pluralizeRu(value, ['год', 'года', 'лет'])}`;
}

export function CandidateSummary({ card, invitation, contactsDisclosed }: CandidateSummaryProps) {
  // Шапка обезличенной карточки: псевдоним, категория со статусом грейда, индекс
  // и условия, которые кандидат разрешил показывать.
  const formats = card.work_formats
    .map((item) => WORK_FORMAT_LABELS[item as keyof typeof WORK_FORMAT_LABELS])
    .filter(Boolean)
    .join(', ');
  const facts = [years(card.experience_years), formats].filter(Boolean).join(' · ');
  return (
    <Group gap="md" wrap="nowrap" align="flex-start" className={classes.root}>
      <AnonymousAvatar alias={card.alias} />
      <Stack gap={6} className={classes.body}>
        <Group gap="xs" wrap="wrap">
          <Text fw={800}>Кандидат {card.alias}</Text>
          {contactsDisclosed && (
            <Badge color="teal" variant="light" leftSection={<IconLockOpen size={12} />}>
              контакты открыты
            </Badge>
          )}
          {invitation && <InvitationStatusBadge status={invitation.status} />}
        </Group>
        <CategoryBadge
          specialization={card.category.specialization.name}
          grade={card.category.grade.code}
          gradeLabel={card.category.grade.name}
          unconfirmed={card.grade_status !== 'confirmed'}
          size="sm"
        />
        <Group gap="md" wrap="wrap" className={classes.meta}>
          {facts && <Text size="sm">{facts}</Text>}
          {card.city && (
            <Text size="sm" c="dimmed">
              <IconMapPin size={13} style={{ verticalAlign: '-2px' }} /> {card.city}
              {card.relocation_ready ? ', готов к переезду' : ''}
            </Text>
          )}
          {card.salary_expectation && (
            <Text size="sm" c="dimmed" className="tabular">
              от {formatRub(card.salary_expectation)} ₽ {card.salary_gross ? 'до НДФЛ' : 'на руки'}
            </Text>
          )}
        </Group>
      </Stack>
      <div className={classes.vps} title="Индекс подтверждённого профиля">
        <span className={classes.vpsValue}>{Math.round(card.verified_score.total)}</span>
        <span className={classes.vpsLabel}>индекс</span>
      </div>
    </Group>
  );
}
