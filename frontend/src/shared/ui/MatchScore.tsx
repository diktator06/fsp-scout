import { RingProgress, Text } from '@mantine/core';
import { scoreTone } from '@/shared/lib/matching';

const TONE_COLORS = { strong: '#0c8a6b', medium: '#8a83d1', weak: '#d90047' } as const;

export function MatchScore({ score, size = 64 }: { score: number; size?: number }) {
  // Балл соответствия кольцом: цвет показывает силу совпадения, число — точное значение.
  const tone = scoreTone(score);
  return (
    <RingProgress
      size={size}
      thickness={size / 11}
      roundCaps
      sections={[{ value: Math.max(2, Math.min(100, score)), color: TONE_COLORS[tone] }]}
      label={
        <Text ta="center" fw={800} size={size > 56 ? 'md' : 'sm'} className="tabular">
          {Math.round(score)}
        </Text>
      }
      aria-label={`Соответствие потребности: ${Math.round(score)} из 100`}
    />
  );
}
