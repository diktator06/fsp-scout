import { Alert } from '@mantine/core';
import { IconChartBar } from '@tabler/icons-react';
import type { SalaryCheck } from '@/api/types';
import { formatRub } from '@/shared/lib/format';
import { SALARY_CHECK_COLORS } from '@/shared/lib/trust';

export function MarketCheckAlert({ check }: { check: SalaryCheck }) {
  // Сверка вилки с открытыми ожиданиями кандидатов той же категории. Нормальная
  // вилка не отвлекает; ниже рынка и «в разы выше» — подсвечиваются.
  if (check.status === 'ok' || check.status === 'unknown') return null;
  return (
    <Alert
      color={SALARY_CHECK_COLORS[check.status]}
      variant="light"
      mb="lg"
      icon={<IconChartBar size={20} />}
    >
      {check.message}.
      {check.median !== null &&
        ` Медиана ожиданий кандидатов категории — ${formatRub(check.median)} до вычета НДФЛ.`}
    </Alert>
  );
}
