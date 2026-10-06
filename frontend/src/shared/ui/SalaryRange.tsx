import { formatSalaryRange } from '@/shared/lib/format';
import classes from './SalaryRange.module.css';

interface SalaryRangeProps {
  from: number;
  to: number;
  label?: string;
  caption?: string;
  size?: 'sm' | 'md' | 'lg';
  tone?: 'light' | 'dark';
  compact?: boolean;
}

export function SalaryRange({
  from,
  to,
  label = 'Вилка',
  caption,
  size = 'md',
  tone = 'light',
  compact = false,
}: SalaryRangeProps) {
  // Зарплата — главный факт приглашения, кандидат видит её до начала общения.
  // Поэтому сумма набрана крупнее остального текста карточки и моноширинными цифрами:
  // при сравнении нескольких предложений столбцы чисел не «пляшут».
  const value = formatSalaryRange(from, to, { compact, withCurrency: false });
  return (
    <div className={classes.root} data-size={size} data-tone={tone}>
      {label && <span className={classes.label}>{label}</span>}
      <span className={classes.value}>
        <span className="tabular">{value}</span>
        <span className={classes.currency}>₽</span>
      </span>
      {caption && <span className={classes.caption}>{caption}</span>}
    </div>
  );
}
