import {
  ActionIcon,
  Alert,
  Button,
  Group,
  NumberInput,
  Radio,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useMediaQuery } from '@mantine/hooks';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useSpecializations } from '@/api/dictionaries';
import { errorMessage } from '@/api/errors';
import { useCreateTask } from '@/api/tasks';
import type { MicroTaskKind } from '@/api/types';
import { groupByDirection } from '@/shared/lib/assessment';

interface TaskFormValues {
  kind: MicroTaskKind;
  answerType: 'number' | 'choice';
  title: string;
  statement: string;
  specialization_id: string | null;
  answer_value: number | '';
  answer_tolerance: number | '';
  options: string[];
  correct_option: string | null;
  rubric: string;
  time_limit_minutes: number | '';
}

const INITIAL: TaskFormValues = {
  kind: 'solve',
  answerType: 'number',
  title: '',
  statement: '',
  specialization_id: null,
  answer_value: '',
  answer_tolerance: 0,
  options: ['', ''],
  correct_option: null,
  rubric: '',
  time_limit_minutes: 20,
};

export function TaskForm({ onCreated }: { onCreated: () => void }) {
  // «Решить» требует эталон — система проверит ответ сама. «Предложить подход» требует
  // рубрику — по ней оценит компания, и кандидат видит её заранее.
  const specializations = useSpecializations();
  const create = useCreateTask();
  const compact = useMediaQuery('(max-width: 36em)');
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<TaskFormValues>({
    initialValues: INITIAL,
    validate: {
      title: (value) => (value.trim().length >= 3 ? null : 'Назовите задачу'),
      statement: (value) => (value.trim().length >= 20 ? null : 'Опишите условие подробнее'),
      specialization_id: (value) => (value ? null : 'Выберите специализацию'),
      answer_value: (value, values) =>
        values.kind === 'solve' && values.answerType === 'number' && value === ''
          ? 'Укажите эталонное число'
          : null,
      correct_option: (value, values) =>
        values.kind === 'solve' && values.answerType === 'choice' && value === null
          ? 'Отметьте верный вариант'
          : null,
      rubric: (value, values) =>
        values.kind === 'approach' && value.trim().length < 10
          ? 'Опишите, по каким критериям оцените подход'
          : null,
    },
  });
  const values = form.values;

  const handleSubmit = form.onSubmit(async (data) => {
    setFailure(null);
    const choice = data.kind === 'solve' && data.answerType === 'choice';
    try {
      await create.mutateAsync({
        kind: data.kind,
        title: data.title.trim(),
        statement: data.statement.trim(),
        specialization_id: Number(data.specialization_id),
        options: choice ? data.options.filter((item) => item.trim()) : [],
        answer_value:
          data.kind === 'solve' && !choice && data.answer_value !== ''
            ? Number(data.answer_value)
            : null,
        answer_tolerance: data.answer_tolerance === '' ? 0 : Number(data.answer_tolerance),
        correct_option: choice && data.correct_option !== null ? Number(data.correct_option) : null,
        rubric: data.kind === 'approach' ? data.rubric.trim() : '',
        time_limit_minutes: data.time_limit_minutes === '' ? 20 : Number(data.time_limit_minutes),
      });
      form.reset();
      onCreated();
    } catch (error) {
      setFailure(errorMessage(error));
    }
  });

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="md">
        <SegmentedControl
          fullWidth
          orientation={compact ? 'vertical' : 'horizontal'}
          data={[
            { value: 'solve', label: 'Решить — проверит система' },
            { value: 'approach', label: 'Предложить подход — оцените вы' },
          ]}
          {...form.getInputProps('kind')}
        />
        <TextInput label="Название" required {...form.getInputProps('title')} />
        <Select
          label="Специализация"
          description="Задачу получат кандидаты этой специализации"
          required
          data={groupByDirection(specializations.data ?? []).map((group) => ({
            group: group.name,
            items: group.items.map((item) => ({ value: String(item.id), label: item.name })),
          }))}
          {...form.getInputProps('specialization_id')}
        />
        <Textarea
          label="Условие"
          required
          autosize
          minRows={4}
          maxLength={5000}
          {...form.getInputProps('statement')}
        />
        {values.kind === 'solve' ? (
          <Stack gap="sm">
            <SegmentedControl
              size="xs"
              data={[
                { value: 'number', label: 'Ответ — число' },
                { value: 'choice', label: 'Ответ — вариант' },
              ]}
              {...form.getInputProps('answerType')}
            />
            {values.answerType === 'number' ? (
              <Group grow>
                <NumberInput
                  label="Эталон"
                  decimalSeparator=","
                  required
                  {...form.getInputProps('answer_value')}
                />
                <NumberInput
                  label="Допуск ±"
                  decimalSeparator=","
                  min={0}
                  {...form.getInputProps('answer_tolerance')}
                />
              </Group>
            ) : (
              <Radio.Group
                label="Варианты — отметьте верный"
                error={form.errors.correct_option}
                {...form.getInputProps('correct_option')}
              >
                <Stack gap="xs" mt="xs">
                  {values.options.map((option, index) => (
                    <Group key={index} gap="xs" wrap="nowrap">
                      <Radio value={String(index)} aria-label={`Вариант ${index + 1} верный`} />
                      <TextInput
                        style={{ flex: 1 }}
                        placeholder={`Вариант ${index + 1}`}
                        value={option}
                        onChange={(event) =>
                          form.setFieldValue(`options.${index}`, event.currentTarget.value)
                        }
                      />
                      {values.options.length > 2 && (
                        <ActionIcon
                          variant="subtle"
                          color="gray"
                          aria-label="Удалить вариант"
                          onClick={() => form.removeListItem('options', index)}
                        >
                          <IconTrash size={16} />
                        </ActionIcon>
                      )}
                    </Group>
                  ))}
                  {values.options.length < 6 && (
                    <Button
                      variant="subtle"
                      size="xs"
                      leftSection={<IconPlus size={14} />}
                      onClick={() => form.insertListItem('options', '')}
                      style={{ alignSelf: 'flex-start' }}
                    >
                      Добавить вариант
                    </Button>
                  )}
                </Stack>
              </Radio.Group>
            )}
            <Text size="xs" c="dimmed">
              Эталон хранится только на сервере: кандидат его не увидит.
            </Text>
          </Stack>
        ) : (
          <Textarea
            label="Рубрика оценки"
            description="Кандидат увидит её до ответа — так оценка прозрачна"
            required
            autosize
            minRows={3}
            maxLength={2000}
            {...form.getInputProps('rubric')}
          />
        )}
        <NumberInput
          label="Примерное время, минут"
          min={5}
          max={240}
          {...form.getInputProps('time_limit_minutes')}
        />
        {failure && (
          <Alert color="signal" variant="light">
            {failure}
          </Alert>
        )}
        <Group>
          <Button type="submit" loading={create.isPending}>
            Создать задачу
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
