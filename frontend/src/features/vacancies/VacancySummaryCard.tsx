import { Badge, Card, Group, Stack, Text } from '@mantine/core';
import { Link } from 'react-router';
import type { VacancyPublic } from '@/api/types';
import { WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import { ApplicationStatusBadge, MatchScore, SalaryRange } from '@/shared/ui';
import classes from './VacancySummaryCard.module.css';

export function VacancySummaryCard({ vacancy }: { vacancy: VacancyPublic }) {
  // Карточка в ленте вакансий: вилка и компания видны сразу, балл соответствия —
  // по тем же правилам, по которым работодатель видит кандидатов.
  const formats = vacancy.work_formats.map((item) => WORK_FORMAT_LABELS[item]).join(', ');
  const must = vacancy.skills.filter((item) => item.importance === 'must');
  return (
    <Card component={Link} to={`/c/vacancies/${vacancy.id}`} className={classes.card}>
      <Stack gap="sm">
        <div className={classes.head}>
          <Stack gap={4}>
            <Text className={classes.title}>{vacancy.title}</Text>
            <Text size="sm" c="dimmed">
              {vacancy.company.name} · {vacancy.specialization.name}
              {vacancy.grades.length ? ` · ${vacancy.grades.map((g) => g.name).join(', ')}` : ''}
            </Text>
            <Text size="sm">
              {formats}
              {vacancy.city ? ` · ${vacancy.city}` : ''}
            </Text>
          </Stack>
          <Group gap="md" wrap="nowrap" align="center">
            <SalaryRange
              from={vacancy.salary_from}
              to={vacancy.salary_to}
              size="sm"
              caption={vacancy.salary_gross ? 'до НДФЛ' : 'на руки'}
            />
            {vacancy.match && <MatchScore score={vacancy.match.score} size={56} />}
          </Group>
        </div>
        <Group gap={6}>
          {must.slice(0, 6).map((item) => (
            <Badge key={item.skill.id} variant="light" color="fsp" tt="none">
              {item.skill.name}
            </Badge>
          ))}
          {vacancy.application && <ApplicationStatusBadge status={vacancy.application.status} />}
        </Group>
      </Stack>
    </Card>
  );
}
