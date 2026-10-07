import {
  Alert,
  Button,
  Card,
  Chip,
  Group,
  Input,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconAlertCircle, IconSparkles } from '@tabler/icons-react';
import { useMemo, useState, type ReactNode } from 'react';
import { useGrades, useSpecializations } from '@/api/dictionaries';
import { errorMessage, fieldErrors } from '@/api/errors';
import type { WorkFormat } from '@/api/types';
import { SkillPicker } from '@/features/candidate/SkillPicker';
import { groupByDirection } from '@/shared/lib/assessment';
import { WORK_FORMAT_LABELS, toOptions } from '@/shared/lib/candidate';
import { salaryRangeError } from '@/shared/lib/salary';
import { SalaryRangeInput } from '@/shared/ui';
import type { NeedFormValues } from './needValues';

interface NeedFormProps {
  initial: NeedFormValues;
  evidence?: Record<string, string>;
  submitLabel: string;
  variant?: 'need' | 'vacancy';
  footer?: ReactNode;
  onSubmit: (values: NeedFormValues) => Promise<void>;
}

const MIN_VACANCY_DESCRIPTION = 20;

function Evidence({ text }: { text: string | undefined }) {
  // Фрагмент исходного текста, по которому разбор заполнил поле.
  if (!text) return null;
  return (
    <Text size="xs" c="lilac.8" mt={4}>
      <IconSparkles size={12} style={{ verticalAlign: '-1px' }} /> найдено в тексте: «{text}»
    </Text>
  );
}

function Field({ children, evidence }: { children: ReactNode; evidence?: string }) {
  return (
    <div>
      {children}
      <Evidence text={evidence} />
    </div>
  );
}

export function NeedForm({
  initial,
  evidence = {},
  submitLabel,
  variant = 'need',
  footer,
  onSubmit,
}: NeedFormProps) {
  // Одна форма для потребности и для вакансии: требования у них общие. Специализация
  // и грейды задают жёсткий фильтр, навыки и описание — балл соответствия, вилка —
  // условия. У вакансии описание и формат работы обязательны: кандидат читает их сам.
  const vacancy = variant === 'vacancy';
  const specializations = useSpecializations();
  const grades = useGrades();
  const [failure, setFailure] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const form = useForm<NeedFormValues>({
    initialValues: initial,
    validate: {
      title: (value) => (value.trim().length >= 3 ? null : 'Назовите потребность'),
      specialization_id: (value) => (value ? null : 'Выберите специализацию'),
      grade_ids: (value) => (value.length ? null : 'Выберите хотя бы один грейд'),
      salary_to: (_, values) =>
        salaryRangeError({ from: values.salary_from, to: values.salary_to }),
      team_description: (value) =>
        vacancy && value.trim().length < MIN_VACANCY_DESCRIPTION
          ? 'Опишите задачи, команду и условия — хотя бы пару предложений'
          : null,
      work_formats: (value) =>
        vacancy && value.length === 0 ? 'Выберите хотя бы один формат' : null,
    },
  });

  const specializationOptions = useMemo(
    () =>
      groupByDirection(specializations.data ?? []).map((group) => ({
        group: group.name,
        items: group.items.map((item) => ({ value: String(item.id), label: item.name })),
      })),
    [specializations.data],
  );
  const must = form.values.skills.filter((item) => item.importance === 'must');
  const nice = form.values.skills.filter((item) => item.importance === 'nice');

  const handleSubmit = form.onSubmit(async (values) => {
    setFailure(null);
    setSaving(true);
    try {
      await onSubmit(values);
    } catch (error) {
      const byField = fieldErrors(error);
      if (Object.keys(byField).length > 0) form.setErrors(byField);
      setFailure(errorMessage(error));
    } finally {
      setSaving(false);
    }
  });

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="lg">
        <Card>
          <Stack gap="md">
            <Field evidence={evidence.title}>
              <TextInput
                label={vacancy ? 'Название вакансии' : 'Название'}
                placeholder="Python-разработчик в команду платежей"
                required
                {...form.getInputProps('title')}
              />
            </Field>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <Field evidence={evidence.specialization}>
                <Select
                  label="Специализация"
                  data={specializationOptions}
                  required
                  size="md"
                  allowDeselect={false}
                  {...form.getInputProps('specialization_id')}
                />
              </Field>
              <Field evidence={evidence.grades}>
                <Input.Wrapper label="Грейд" required error={form.errors.grade_ids} size="md">
                  <Chip.Group
                    multiple
                    value={form.values.grade_ids}
                    onChange={(value) => form.setFieldValue('grade_ids', value)}
                  >
                    <Group gap="xs" mt={8}>
                      {(grades.data ?? []).map((grade) => (
                        <Chip key={grade.id} value={String(grade.id)} color="fsp" variant="light">
                          {grade.name}
                        </Chip>
                      ))}
                    </Group>
                  </Chip.Group>
                </Input.Wrapper>
              </Field>
            </SimpleGrid>
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
              <SkillPicker
                label="Обязательные навыки"
                description="Весят вдвое больше желательных"
                value={must.map((item) => item.skill)}
                onChange={(skills) =>
                  form.setFieldValue('skills', [
                    ...skills.map((skill) => ({ skill, importance: 'must' as const })),
                    ...nice.filter((item) => !skills.some((skill) => skill.id === item.skill.id)),
                  ])
                }
                maxValues={12}
              />
              <SkillPicker
                label="Желательные навыки"
                description="«Будет плюсом»"
                value={nice.map((item) => item.skill)}
                onChange={(skills) =>
                  form.setFieldValue('skills', [
                    ...must.filter((item) => !skills.some((skill) => skill.id === item.skill.id)),
                    ...skills.map((skill) => ({ skill, importance: 'nice' as const })),
                  ])
                }
                maxValues={12}
              />
            </SimpleGrid>
          </Stack>
        </Card>
        <Card>
          <Stack gap="md">
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
              <Field evidence={evidence.salary}>
                <SalaryRangeInput
                  value={{ from: form.values.salary_from, to: form.values.salary_to }}
                  onChange={(value) =>
                    form.setValues({ salary_from: value.from, salary_to: value.to })
                  }
                  description="Обязательна: кандидат видит её ещё до начала общения"
                  error={form.errors.salary_to as string | undefined}
                />
              </Field>
              <Input.Wrapper label="Сумма указана" size="md">
                <SegmentedControl
                  mt={6}
                  fullWidth
                  data={[
                    { value: 'gross', label: 'до вычета НДФЛ' },
                    { value: 'net', label: 'на руки' },
                  ]}
                  value={form.values.salary_gross ? 'gross' : 'net'}
                  onChange={(value) => form.setFieldValue('salary_gross', value === 'gross')}
                />
              </Input.Wrapper>
              <Field evidence={evidence.work_formats}>
                <Input.Wrapper
                  label="Формат работы"
                  description={vacancy ? undefined : 'Пусто — любой'}
                  required={vacancy}
                  error={form.errors.work_formats}
                  size="md"
                >
                  <Chip.Group<true, WorkFormat>
                    multiple
                    value={form.values.work_formats}
                    onChange={(value) => form.setFieldValue('work_formats', value)}
                  >
                    <Group gap="xs" mt={8}>
                      {toOptions(WORK_FORMAT_LABELS).map((option) => (
                        <Chip key={option.value} value={option.value} color="fsp" variant="light">
                          {option.label}
                        </Chip>
                      ))}
                    </Group>
                  </Chip.Group>
                </Input.Wrapper>
              </Field>
              <Field evidence={evidence.city}>
                <TextInput
                  label="Город офиса"
                  description="Важен для офиса и гибрида"
                  placeholder="Москва"
                  {...form.getInputProps('city')}
                />
              </Field>
            </SimpleGrid>
            <Textarea
              label={vacancy ? 'Описание вакансии' : 'Чем занимается команда'}
              description={
                vacancy
                  ? 'Задачи, команда и условия — кандидат читает это вместе с вилкой'
                  : 'По этому тексту ищутся кандидаты с близким опытом: платежи, геоданные, highload…'
              }
              required={vacancy}
              autosize
              minRows={vacancy ? 5 : 3}
              maxLength={vacancy ? 8000 : 3000}
              {...form.getInputProps('team_description')}
            />
          </Stack>
        </Card>
        {failure && (
          <Alert color="signal" variant="light" icon={<IconAlertCircle size={18} />}>
            {failure}
          </Alert>
        )}
        <Group>
          <Button type="submit" size="md" loading={saving}>
            {submitLabel}
          </Button>
          {footer}
        </Group>
      </Stack>
    </form>
  );
}
