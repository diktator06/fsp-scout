import { GRADE_LABELS, GRADE_ORDER, gradeRank, isGradeCode } from '@/shared/lib/grades';
import classes from './CategoryBadge.module.css';

interface CategoryBadgeProps {
  specialization: string;
  grade: string;
  gradeLabel?: string;
  size?: 'sm' | 'md';
  tone?: 'light' | 'dark';
  unconfirmed?: boolean;
}

export function GradeMeter({ grade, tone = 'light' }: { grade: string; tone?: 'light' | 'dark' }) {
  // Шкала уровня — четыре столбика растущей высоты. Закрашены столбики до текущего
  // грейда включительно, поэтому Middle и Senior различимы с одного взгляда даже в плотном списке.
  const rank = gradeRank(grade);
  return (
    <span className={classes.meter} data-tone={tone} aria-hidden="true">
      {GRADE_ORDER.map((code, index) => (
        <span key={code} className={classes.bar} data-filled={index < rank || undefined} />
      ))}
    </span>
  );
}

export function CategoryBadge({
  specialization,
  grade,
  gradeLabel,
  size = 'md',
  tone = 'light',
  unconfirmed = false,
}: CategoryBadgeProps) {
  // Неподтверждённый грейд (заявлен в опросе, тест не пройден) рисуется пунктиром
  // и с пометкой: работодатель видит его, но не путает с подтверждённым.
  const label = gradeLabel ?? (isGradeCode(grade) ? GRADE_LABELS[grade] : grade);
  return (
    <span
      className={classes.badge}
      data-size={size}
      data-tone={tone}
      data-unconfirmed={unconfirmed || undefined}
      aria-label={`Категория: ${specialization}, грейд ${label}${unconfirmed ? ', не подтверждён тестом' : ''}`}
    >
      <GradeMeter grade={grade} tone={tone} />
      <span className={classes.specialization}>{specialization}</span>
      <span className={classes.separator} aria-hidden="true">
        ·
      </span>
      <span className={classes.grade}>{label}</span>
      {unconfirmed && (
        <span className={classes.pending} aria-hidden="true">
          не подтверждён
        </span>
      )}
    </span>
  );
}
