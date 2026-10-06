import { Group, Input, NumberInput, Text } from '@mantine/core';
import { formatSalaryRange } from '@/shared/lib/format';
import { salaryRangeError, type SalaryRangeValue } from '@/shared/lib/salary';

interface SalaryRangeInputProps {
  value: SalaryRangeValue;
  onChange: (value: SalaryRangeValue) => void;
  label?: string;
  description?: string;
  error?: string | null;
  required?: boolean;
  disabled?: boolean;
}

function toAmount(raw: string | number): number | null {
  // NumberInput отдаёт пустую строку для пустого поля: превращаем её в null.
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
}

export function SalaryRangeInput({
  value,
  onChange,
  label = 'Вилка зарплаты',
  description = 'Сумма в рублях до вычета НДФЛ. Кандидат увидит её до начала общения',
  error,
  required = true,
  disabled = false,
}: SalaryRangeInputProps) {
  const preview =
    value.from != null && value.to != null && !salaryRangeError(value)
      ? formatSalaryRange(value.from, value.to)
      : null;

  return (
    <Input.Wrapper label={label} description={description} error={error} required={required}>
      <Group gap="sm" mt={6} wrap="nowrap" align="flex-start">
        <NumberInput
          aria-label="Зарплата от"
          placeholder="от"
          value={value.from ?? ''}
          onChange={(raw) => onChange({ ...value, from: toAmount(raw) })}
          thousandSeparator=" "
          suffix=" ₽"
          min={0}
          step={5000}
          allowNegative={false}
          allowDecimal={false}
          hideControls
          disabled={disabled}
          error={Boolean(error)}
          style={{ flex: 1 }}
        />
        <Text c="dimmed" pt={10} aria-hidden="true">
          –
        </Text>
        <NumberInput
          aria-label="Зарплата до"
          placeholder="до"
          value={value.to ?? ''}
          onChange={(raw) => onChange({ ...value, to: toAmount(raw) })}
          thousandSeparator=" "
          suffix=" ₽"
          min={0}
          step={5000}
          allowNegative={false}
          allowDecimal={false}
          hideControls
          disabled={disabled}
          error={Boolean(error)}
          style={{ flex: 1 }}
        />
      </Group>
      {preview && (
        <Text size="xs" c="dimmed" mt={6}>
          Кандидат увидит: <b className="tabular">{preview}</b>
        </Text>
      )}
    </Input.Wrapper>
  );
}
