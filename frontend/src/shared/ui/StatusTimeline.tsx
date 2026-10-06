import { IconCheck, IconX } from '@tabler/icons-react';
import { formatDateTime } from '@/shared/lib/format';
import type { TimelineStep } from '@/shared/lib/invitationStatus';
import classes from './StatusTimeline.module.css';

interface StatusTimelineProps {
  steps: TimelineStep[];
  orientation?: 'horizontal' | 'vertical' | 'auto';
  tone?: 'light' | 'dark';
}

const STATE_LABELS: Record<TimelineStep['state'], string> = {
  done: 'пройдено',
  success: 'завершено успешно',
  current: 'текущий шаг',
  upcoming: 'ожидается',
  negative: 'завершено без результата',
};

export function StatusTimeline({
  steps,
  orientation = 'auto',
  tone = 'light',
}: StatusTimelineProps) {
  // В режиме auto таймлайн горизонтальный на широких экранах и вертикальный на
  // узких: так три-пять шагов статуса читаются и в карточке, и на телефоне.
  return (
    <ol className={classes.root} data-orientation={orientation} data-tone={tone}>
      {steps.map((step) => (
        <li key={step.key} className={classes.step} data-state={step.state}>
          <span className={classes.node} aria-hidden="true">
            {(step.state === 'done' || step.state === 'success') && (
              <IconCheck size={14} stroke={3} />
            )}
            {step.state === 'negative' && <IconX size={14} stroke={3} />}
          </span>
          <span className={classes.body}>
            <span className={classes.label}>
              {step.label}
              <span className={classes.visuallyHidden}> — {STATE_LABELS[step.state]}</span>
            </span>
            {step.timestamp && (
              <time className={classes.time} dateTime={new Date(step.timestamp).toISOString()}>
                {formatDateTime(step.timestamp)}
              </time>
            )}
            {step.description && <span className={classes.description}>{step.description}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}
