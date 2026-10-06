import { Group, Text } from '@mantine/core';
import classes from './ScoutLogo.module.css';

interface ScoutLogoProps {
  tone?: 'dark' | 'light';
  size?: 'sm' | 'md' | 'lg';
  withWordmark?: boolean;
}

const MARK_SIZE = { sm: 26, md: 32, lg: 40 } as const;

export function ScoutMark({ size = 32 }: { size?: number }) {
  // Знак «Скаута» — созвездие из узлов, как в логотипе ФСП, где один узел подсвечен
  // сигнальным цветом: работодатель «замечает» конкретного человека в базе.
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-hidden="true"
      className={classes.mark}
    >
      <rect width="32" height="32" rx="9" fill="#520978" />
      <g stroke="#ffffff" strokeOpacity="0.55" strokeWidth="1.6" strokeLinecap="round">
        <line x1="8.5" y1="22.5" x2="13.5" y2="11.5" />
        <line x1="13.5" y1="11.5" x2="22.5" y2="9" />
        <line x1="13.5" y1="11.5" x2="21.5" y2="21.5" />
        <line x1="8.5" y1="22.5" x2="21.5" y2="21.5" />
      </g>
      <circle cx="8.5" cy="22.5" r="2.3" fill="#ffffff" />
      <circle cx="13.5" cy="11.5" r="2.3" fill="#ffffff" />
      <circle cx="21.5" cy="21.5" r="2.3" fill="#ffffff" />
      <circle cx="22.5" cy="9" r="3.6" fill="#ff0053" stroke="#ffffff" strokeWidth="1.4" />
    </svg>
  );
}

export function ScoutLogo({ tone = 'dark', size = 'md', withWordmark = true }: ScoutLogoProps) {
  return (
    <Group gap={10} wrap="nowrap" className={classes.root} data-tone={tone} data-size={size}>
      <ScoutMark size={MARK_SIZE[size]} />
      {withWordmark && (
        <Text component="span" className={classes.wordmark}>
          Скаут
        </Text>
      )}
    </Group>
  );
}
