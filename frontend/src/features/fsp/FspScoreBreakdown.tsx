import { Stack, Text } from '@mantine/core';
import type { FspScore } from '@/api/types';
import classes from './FspScoreBreakdown.module.css';

interface FspScoreBreakdownProps {
  score: FspScore;
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function FspScoreBreakdown({ score }: FspScoreBreakdownProps) {
  // Балл ФСП раскладывается на две понятные части: результативность и активность.
  // Кандидат видит, что именно его поднимает и сколько это даёт индексу.
  return (
    <Stack gap="sm">
      <div className={classes.grid}>
        <div className={classes.cell}>
          <div className={classes.label}>Балл ФСП · F</div>
          <div className={classes.value}>{percent(score.value)}</div>
          <Text size="xs" c="dimmed">
            +{score.vps_points.toLocaleString('ru-RU')} к индексу из 15
          </Text>
        </div>
        <div className={classes.cell}>
          <div className={classes.label}>Результативность · R</div>
          <div className={classes.value}>{percent(score.results)}</div>
          <Text size="xs" c="dimmed">
            победы и призы — 1, финал — 0,5
          </Text>
        </div>
        <div className={classes.cell}>
          <div className={classes.label}>Активность · N</div>
          <div className={classes.value}>{percent(score.activity)}</div>
          <Text size="xs" c="dimmed">
            {score.effective_events.toLocaleString('ru-RU')} взвешенных участий
          </Text>
        </div>
      </div>
      <Text size="xs" c="dimmed" lh={1.6}>
        <span className={classes.formula}>F = min(1; 0,6·R + 0,4·N)</span>. Все соревнования
        равноценны: уровень и дисциплина на балл не влияют. Свежие участия весят больше (полураспад
        2 года), онлайн-участия без результата добавляют всё меньше с каждым следующим.
      </Text>
    </Stack>
  );
}
