import {
  Alert,
  Button,
  Card,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle } from '@tabler/icons-react';
import { useState } from 'react';
import { useIndustries } from '@/api/dictionaries';
import { useSaveCompany } from '@/api/employer';
import { errorMessage, fieldErrors } from '@/api/errors';
import type { CompanySize, EmployerProfile } from '@/api/types';
import { toOptions } from '@/shared/lib/candidate';
import { COMPANY_SIZE_LABELS } from '@/shared/lib/matching';

interface CompanyValues {
  name: string;
  inn: string;
  website: string;
  industry_id: string | null;
  description: string;
  size: CompanySize | null;
  city: string;
  contact_email: string;
  contact_phone: string;
  contact_telegram: string;
  recruiter_full_name: string;
  recruiter_position: string;
}

function initialValues(profile: EmployerProfile | undefined): CompanyValues {
  const company = profile?.company;
  return {
    name: company?.name ?? '',
    inn: company?.inn ?? '',
    website: company?.website ?? '',
    industry_id: company?.industry ? String(company.industry.id) : null,
    description: company?.description ?? '',
    size: company?.size ?? null,
    city: company?.city ?? '',
    contact_email: company?.contact_email ?? '',
    contact_phone: company?.contact_phone ?? '',
    contact_telegram: company?.contact_telegram ?? '',
    recruiter_full_name: profile?.recruiter?.full_name ?? '',
    recruiter_position: profile?.recruiter?.position ?? '',
  };
}

export function CompanyForm({
  profile,
  onSaved,
}: {
  profile: EmployerProfile | undefined;
  onSaved?: () => void;
}) {
  // Кандидат видит название, отрасль и описание компании в приглашении сразу, а её
  // контакты — после того как примет приглашение. Поэтому контакты здесь же.
  const save = useSaveCompany();
  const industries = useIndustries();
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<CompanyValues>({
    initialValues: initialValues(profile),
    validate: {
      name: (value) => (value.trim().length >= 2 ? null : 'Укажите название компании'),
      recruiter_full_name: (value) => (value.trim().length >= 2 ? null : 'Как к вам обращаться?'),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setFailure(null);
    const optional = (value: string) => value.trim() || null;
    try {
      await save.mutateAsync({
        name: values.name.trim(),
        inn: optional(values.inn),
        website: optional(values.website),
        industry_id: values.industry_id ? Number(values.industry_id) : null,
        description: values.description.trim(),
        size: values.size,
        city: optional(values.city),
        contact_email: optional(values.contact_email),
        contact_phone: optional(values.contact_phone),
        contact_telegram: optional(values.contact_telegram),
        recruiter_full_name: values.recruiter_full_name.trim(),
        recruiter_position: values.recruiter_position.trim(),
      });
      form.resetDirty();
      notifications.show({ color: 'teal', message: 'Профиль компании сохранён' });
      onSaved?.();
    } catch (error) {
      const byField = fieldErrors(error);
      if (Object.keys(byField).length > 0) {
        form.setErrors(byField);
        setFailure('Проверьте отмеченные поля');
        return;
      }
      setFailure(errorMessage(error));
    }
  });

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="lg">
        <Card>
          <Stack gap="md">
            <Title order={4}>Компания</Title>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <TextInput label="Название" required {...form.getInputProps('name')} />
              <Select
                label="Отрасль"
                placeholder="Финтех, e-commerce…"
                data={(industries.data ?? []).map((item) => ({
                  value: String(item.id),
                  label: item.name,
                }))}
                clearable
                searchable
                size="md"
                {...form.getInputProps('industry_id')}
              />
              <TextInput
                label="Сайт"
                placeholder="kedr.example"
                {...form.getInputProps('website')}
              />
              <TextInput
                label="ИНН"
                description="Нужен для проверки компании платформой"
                inputMode="numeric"
                {...form.getInputProps('inn')}
              />
              <Select<CompanySize>
                label="Размер"
                data={toOptions(COMPANY_SIZE_LABELS)}
                clearable
                size="md"
                {...form.getInputProps('size')}
              />
              <TextInput label="Город" placeholder="Москва" {...form.getInputProps('city')} />
            </SimpleGrid>
            <Textarea
              label="Чем занимается компания"
              description="Кандидат увидит это в приглашении"
              autosize
              minRows={3}
              maxLength={3000}
              {...form.getInputProps('description')}
            />
          </Stack>
        </Card>
        <Card>
          <Stack gap="md">
            <div>
              <Title order={4}>Контакты и рекрутер</Title>
              <Text size="sm" c="dimmed">
                Кандидат увидит их после того, как примет приглашение
              </Text>
            </div>
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <TextInput label="Ваше имя" required {...form.getInputProps('recruiter_full_name')} />
              <TextInput
                label="Должность"
                placeholder="HR-партнёр"
                {...form.getInputProps('recruiter_position')}
              />
              <TextInput
                label="Email для кандидатов"
                type="email"
                {...form.getInputProps('contact_email')}
              />
              <TextInput
                label="Telegram"
                placeholder="@company_hr"
                {...form.getInputProps('contact_telegram')}
              />
              <TextInput label="Телефон" inputMode="tel" {...form.getInputProps('contact_phone')} />
            </SimpleGrid>
          </Stack>
        </Card>
        {failure && (
          <Alert color="signal" variant="light" icon={<IconAlertCircle size={18} />}>
            {failure}
          </Alert>
        )}
        <Group>
          <Button type="submit" size="md" loading={save.isPending}>
            Сохранить
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
