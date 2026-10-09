import { confidenceBand, thetaToPercent } from '@/shared/lib/assessment';
import classes from './GradeScale.module.css';

export interface GradeCut {
  code: string;
  name: string;
  cut: number;
}

interface GradeScaleProps {
  cuts: GradeCut[];
  theta: number;
  se: number;
  targetCode?: string;
}

function formatTheta(value: number): string {
  // Знак минуса — типографский, десятичный разделитель — запятая.
  return value.toFixed(2).replace('-', '−').replace('.', ',');
}

export function GradeScale({ cuts, theta, se, targetCode }: GradeScaleProps) {
  // Шкала способностей (θ) поделена порогами грейдов на зоны. Точка — оценка
  // кандидата, полупрозрачная полоса — 90-процентный интервал, пунктир — порог
  // уровня, который проверял тест. Так видно и уровень, и точность измерения:
  // короткий экспресс-тест даёт заметно более широкую полосу.
  const ordered = [...cuts].sort((a, b) => a.cut - b.cut);
  const [low, high] = confidenceBand(theta, se);
  const reached = [...ordered].reverse().find((grade) => theta >= grade.cut);
  const target = ordered.find((grade) => grade.code === targetCode);
  const description =
    `Оценка ${formatTheta(theta)} ± ${formatTheta(1.64 * se)} по шкале способностей. ` +
    (reached ? `Это зона грейда ${reached.name}.` : 'Это ниже порога первого грейда.');

  return (
    <div className={classes.root} role="img" aria-label={description}>
      <div className={classes.track}>
        {ordered.map((grade, index) => {
          const start = thetaToPercent(grade.cut);
          const next = ordered[index + 1];
          const end = next ? thetaToPercent(next.cut) : 100;
          return (
            <div
              key={grade.code}
              className={classes.zone}
              data-rank={index + 1}
              style={{ left: `${start}%`, width: `${end - start}%` }}
            >
              <span className={classes.zoneLabel} aria-hidden="true">
                <span className={classes.fullLabel}>{grade.name}</span>
                <span className={classes.shortLabel}>{grade.name.slice(0, 1)}</span>
              </span>
            </div>
          );
        })}
        <div
          className={classes.band}
          style={{
            left: `${thetaToPercent(low)}%`,
            width: `${thetaToPercent(high) - thetaToPercent(low)}%`,
          }}
        />
        {target && (
          <div className={classes.target} style={{ left: `${thetaToPercent(target.cut)}%` }}>
            <span className={classes.targetLabel}>
              порог {target.name}: {formatTheta(target.cut)}
            </span>
          </div>
        )}
        <div className={classes.marker} style={{ left: `${thetaToPercent(theta)}%` }}>
          <span className={classes.markerLabel}>вы</span>
        </div>
      </div>
      <div className={classes.axis} aria-hidden="true">
        <span>ниже</span>
        <span>ваша оценка: {formatTheta(theta)}</span>
        <span>выше</span>
      </div>
    </div>
  );
}
