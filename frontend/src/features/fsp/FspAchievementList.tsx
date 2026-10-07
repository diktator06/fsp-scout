import { Anchor, Badge, Text } from '@mantine/core';
import { IconExternalLink } from '@tabler/icons-react';
import type { FspAchievement } from '@/api/types';
import {
  FSP_LEVEL_LABELS,
  FSP_RESULT_COLORS,
  FSP_RESULT_LABELS,
  isSafeProtocolUrl,
  placePercentile,
  placeText,
} from '@/shared/lib/fsp';
import classes from './FspAchievementList.module.css';

interface FspAchievementListProps {
  items: FspAchievement[];
  limit?: number;
}

function eventMonth(value: string): { month: string; year: number } {
  // Месяц и год отдельными строками: «июнь» над «2026» помещаются в узкую колонку.
  const date = new Date(value);
  return {
    month: new Intl.DateTimeFormat('ru-RU', { month: 'long' }).format(date),
    year: date.getFullYear(),
  };
}

function details(item: FspAchievement): string {
  // Уровень и дисциплина — справка: на балл они не влияют, но помогают понять контекст.
  const team =
    item.participation_format === 'team'
      ? `команда${item.team_name ? ` «${item.team_name}»` : ''}${item.team_role ? `, ${item.team_role}` : ''}`
      : 'личное участие';
  return [
    FSP_LEVEL_LABELS[item.event_level],
    item.discipline,
    item.is_online ? 'онлайн' : 'очно',
    team,
  ].join(' · ');
}

export function FspAchievementList({ items, limit }: FspAchievementListProps) {
  // Лента участий из реестра ФСП: результат, место среди участников и ссылка на протокол,
  // по которой работодатель может сам проверить запись.
  const shown = limit ? items.slice(0, limit) : items;
  return (
    <ul className={classes.list}>
      {shown.map((item) => {
        const place = placeText(item.place, item.participants_total);
        const percentile = placePercentile(item.place, item.participants_total);
        const { month, year } = eventMonth(item.event_date);
        return (
          <li key={item.external_event_id} className={classes.item}>
            <span className={classes.date}>
              <span>{month}</span> <span>{year}</span>
            </span>
            <div>
              <Text className={classes.name}>{item.event_name}</Text>
              <Text className={classes.meta}>{details(item)}</Text>
              {isSafeProtocolUrl(item.protocol_url) && (
                <Anchor
                  href={item.protocol_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  size="xs"
                  fw={600}
                >
                  Протокол <IconExternalLink size={12} style={{ verticalAlign: '-1px' }} />
                </Anchor>
              )}
            </div>
            <div className={classes.result}>
              <Badge color={FSP_RESULT_COLORS[item.result_status]} variant="light" tt="none">
                {FSP_RESULT_LABELS[item.result_status]}
              </Badge>
              {place && <span className={classes.place}>{place}</span>}
              {percentile !== null && percentile > 0 && percentile < 100 && (
                <Text size="xs" c="dimmed">
                  выше {percentile}% участников
                </Text>
              )}
            </div>
          </li>
        );
      })}
      {limit && items.length > limit && (
        <li className={classes.item}>
          <span />
          <Text size="sm" c="dimmed">
            И ещё {items.length - limit} в реестре ФСП
          </Text>
        </li>
      )}
    </ul>
  );
}
