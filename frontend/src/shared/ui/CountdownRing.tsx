import { formatCountdown, timerTone } from '@/shared/lib/assessment';
import classes from './CountdownRing.module.css';

interface CountdownRingProps {
  secondsLeft: number;
  limit: number;
  size?: number;
}

const STROKE = 6;

export function CountdownRing({ secondsLeft, limit, size = 76 }: CountdownRingProps) {
  // Кольцо убывает вместе со временем задания. Озвучивать каждую секунду
  // скринридером бессмысленно, поэтому живой регион не используется: текущее
  // значение доступно через role="timer" и подпись.
  const radius = (size - STROKE) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = limit > 0 ? Math.min(1, Math.max(0, secondsLeft / limit)) : 0;
  const tone = timerTone(secondsLeft, limit);

  return (
    <div
      className={classes.root}
      style={{ width: size, height: size }}
      role="timer"
      aria-label={`Осталось ${formatCountdown(secondsLeft)}`}
      data-tone={tone}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          className={classes.track}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={STROKE}
        />
        <circle
          className={classes.progress}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={STROKE}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - fraction)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className={classes.value}>{formatCountdown(secondsLeft)}</span>
    </div>
  );
}
