import {
  Alert,
  Button,
  Group,
  Input,
  Modal,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useEmployerProfile } from '@/api/employer';
import { errorMessage, fieldErrors } from '@/api/errors';
import { useSendInvitation } from '@/api/invitations';
import type { CandidateCard, Need, WorkFormat } from '@/api/types';
import { WORK_FORMAT_LABELS, toOptions } from '@/shared/lib/candidate';
import { salaryWarning } from '@/shared/lib/matching';
import { salaryRangeError } from '@/shared/lib/salary';
import { SalaryRangeInput } from '@/shared/ui';

interface InviteModalProps {
  opened: boolean;
  onClose: () => void;
  card: CandidateCard | null;
  need?: Need | null;
}

interface InviteValues {
  title: string;
  offer_description: string;
  salary_from: number | null;
  salary_to: number | null;
  salary_gross: boolean;
  work_format: WorkFormat;
  contact_method: string;
}

function initial(need: Need | null | undefined, contact: string): InviteValues {
  // Приглашение по потребности наследует её название, вилку и формат.
  return {
    title: need?.title ?? '',
    offer_description: need?.team_description ?? '',
    salary_from: need?.salary_from ?? null,
    salary_to: need?.salary_to ?? null,
    salary_gross: need?.salary_gross ?? true,
    work_format: need?.work_formats[0] ?? 'remote',
    contact_method: contact,
  };
}

export function InviteModal({ opened, onClose, card, need }: InviteModalProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="Приглашение" size="lg" centered>
      {card && <InviteForm key={card.candidate_id} card={card} need={need} onDone={onClose} />}
    </Modal>
  );
}

function InviteForm({
  card,
  need,
  onDone,
}: {
  card: CandidateCard;
  need?: Need | null;
  onDone: () => void;
}) {
  // Форма монтируется заново для каждого кандидата: значения не «протекают» между ними.
  const profile = useEmployerProfile();
  const send = useSendInvitation();
  const company = profile.data?.company;
  const contact = company?.contact_telegram
    ? `Telegram ${company.contact_telegram}`
    : (company?.contact_email ?? '');
  const form = useForm<InviteValues>({
    initialValues: initial(need, contact),
    validate: {
      title: (value) => (value.trim().length >= 3 ? null : 'Как называется позиция?'),
      offer_description: (value) =>
        value.trim().length >= 20 ? null : 'Опишите задачи и команду хотя бы в паре предложений',
      salary_to: (_, values) =>
        salaryRangeError({ from: values.salary_from, to: values.salary_to }),
      contact_method: (value) =>
        value.trim().length >= 5 ? null : 'Как кандидату с вами связаться?',
    },
  });
  const warning = salaryWarning(
    card.salary_expectation,
    card.salary_gross,
    form.values.salary_to,
    form.values.salary_gross,
  );
  const quota = profile.data?.quota;

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      await send.mutateAsync({
        candidate_id: card.candidate_id,
        need_id: need?.id ?? null,
        title: values.title.trim(),
        offer_description: values.offer_description.trim(),
        salary_from: values.salary_from ?? 0,
        salary_to: values.salary_to ?? 0,
        salary_gross: values.salary_gross,
        work_format: values.work_format,
        contact_method: values.contact_method.trim(),
      });
      notifications.show({
        color: 'teal',
        message: `Приглашение отправлено кандидату ${card.alias}`,
      });
      onDone();
    } catch (error) {
      const byField = fieldErrors(error);
      if (Object.keys(byField).length > 0) form.setErrors(byField);
    }
  });

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          Кандидат {card.alias} увидит компанию, вилку и описание сразу. Его контакты откроются вам,
          только если он примет приглашение.
        </Text>
        <TextInput label="Позиция" required {...form.getInputProps('title')} />
        <Textarea
          label="Предложение"
          description="Задачи, команда, что даёте"
          autosize
          minRows={3}
          maxLength={3000}
          required
          {...form.getInputProps('offer_description')}
        />
        <SalaryRangeInput
          value={{ from: form.values.salary_from, to: form.values.salary_to }}
          onChange={(value) => form.setValues({ salary_from: value.from, salary_to: value.to })}
          description="Обязательна. Не шире чем вдвое"
          error={form.errors.salary_to as string | undefined}
        />
        <Group grow align="flex-start">
          <Input.Wrapper label="Сумма указана">
            <SegmentedControl
              mt={6}
              fullWidth
              data={[
                { value: 'gross', label: 'до НДФЛ' },
                { value: 'net', label: 'на руки' },
              ]}
              value={form.values.salary_gross ? 'gross' : 'net'}
              onChange={(value) => form.setFieldValue('salary_gross', value === 'gross')}
            />
          </Input.Wrapper>
          <Input.Wrapper label="Формат">
            <SegmentedControl<WorkFormat>
              mt={6}
              fullWidth
              data={toOptions(WORK_FORMAT_LABELS)}
              value={form.values.work_format}
              onChange={(value) => form.setFieldValue('work_format', value)}
            />
          </Input.Wrapper>
        </Group>
        {warning && (
          <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />}>
            {warning}. Отказ вероятен — возможно, стоит поднять верхнюю границу.
          </Alert>
        )}
        <TextInput
          label="Способ связи"
          description="Видит кандидат: как и где вам ответить"
          required
          {...form.getInputProps('contact_method')}
        />
        {send.isError && (
          <Alert color="signal" variant="light">
            {errorMessage(send.error)}
          </Alert>
        )}
        <Group justify="space-between" wrap="wrap">
          {quota && (
            <Text size="xs" c="dimmed">
              Осталось приглашений на сутки: {quota.remaining} из {quota.daily_limit}
            </Text>
          )}
          <Button type="submit" loading={send.isPending} ml="auto">
            Отправить приглашение
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
