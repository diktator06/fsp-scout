import { Tooltip } from '@mantine/core';
import { clamp01, computeScore, type ScoreFactor } from '@/shared/lib/score';
import classes from './VerifiedScoreBar.module.css';

interface VerifiedScoreBarProps {
  factors: ScoreFactor[];
  score?: number;
  title?: string;
  tone?: 'light' | 'dark';
  compact?: boolean;
}

const FACTOR_COLORS = ['#520978', '#8a83d1', '#ff0053', '#c493e1', '#310f53'];

export function VerifiedScoreBar({
  factors,
  score,
  title = 'Индекс подтверждённого профиля',
  tone = 'light',
  compact = false,
}: VerifiedScoreBarProps) {
  // Полоса составная: ширина сегмента — вклад фактора в итог (вес × значение).
  // Работодатель видит не только число, но и из чего оно сложилось. Это и есть
  // объяснимость выдачи, которой требует ТЗ.
  const resolved = score ?? computeScore(factors);
  const colored = factors.map((factor, index) => ({
    ...factor,
    color: factor.color ?? FACTOR_COLORS[index % FACTOR_COLORS.length],
    contribution: clamp01(factor.value) * factor.weight * 100,
  }));

  return (
    <div className={classes.root} data-tone={tone} data-compact={compact || undefined}>
      <div className={classes.header}>
        <span className={classes.title}>{title}</span>
        <span className={classes.score}>
          <span className="tabular">{resolved}</span>
          <span className={classes.outOf}>/100</span>
        </span>
      </div>
      <div
        className={classes.track}
        role="meter"
        aria-label={title}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={resolved}
      >
        {colored.map((factor) => (
          <Tooltip
            key={factor.key}
            label={`${factor.label}: ${Math.round(factor.value * 100)}% × вес ${Math.round(
              factor.weight * 100,
            )}%`}
          >
            <span
              className={classes.segment}
              style={{ width: `${factor.contribution}%`, background: factor.color }}
            />
          </Tooltip>
        ))}
      </div>
      {!compact && (
        <ul className={classes.legend}>
          {colored.map((factor) => (
            <li key={factor.key} className={classes.legendItem}>
              <span className={classes.dot} style={{ background: factor.color }} />
              <span className={classes.legendLabel}>{factor.label}</span>
              <span className={`${classes.legendValue} tabular`}>
                {Math.round(factor.value * 100)}%
              </span>
              <span className={classes.legendWeight}>вес {Math.round(factor.weight * 100)}%</span>
              {factor.hint && <span className={classes.legendHint}>{factor.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
