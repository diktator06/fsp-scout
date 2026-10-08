import { Alert, Button, Checkbox, Group, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useCreateWebhook, useWebhookEvents } from '@/api/integrations';
import type { WebhookEndpointWithSecret, WebhookEventType } from '@/api/types';

interface EndpointFormValues {
  url: string;
  events: WebhookEventType[];
  description: string;
}

export function EndpointForm({
  onCreated,
}: {
  onCreated: (endpoint: WebhookEndpointWithSecret) => void;
}) {
  // Адрес проверяет сервер: внутренние сети и служебные адреса облака запрещены.
  const catalog = useWebhookEvents();
  const create = useCreateWebhook();
  const [failure, setFailure] = useState<string | null>(null);
  const form = useForm<EndpointFormValues>({
    initialValues: {
      url: '',
      events: ['invitation.accepted', 'application.created'],
      description: '',
    },
    validate: {
      url: (value) =>
        /^https?:\/\/\S+$/.test(value.trim()) ? null : 'Нужен адрес вида https://ats.example.com',
      events: (value) => (value.length ? null : 'Выберите хотя бы одно событие'),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    setFailure(null);
    try {
      const endpoint = await create.mutateAsync({
        url: values.url.trim(),
        events: values.events,
        description: values.description.trim(),
      });
      form.reset();
      onCreated(endpoint);
    } catch (error) {
      setFailure(errorMessage(error));
    }
  });

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="md">
        <TextInput
          label="Адрес приёма вебхуков"
          placeholder="https://ats.example.com/hooks/scout"
          required
          {...form.getInputProps('url')}
        />
        <Checkbox.Group label="События" required {...form.getInputProps('events')}>
          <Stack gap="xs" mt="xs">
            {(catalog.data ?? []).map((item) => (
              <Checkbox
                key={item.type}
                value={item.type}
                label={item.title}
                description={`${item.description}${item.contains_contacts ? ' · с контактами' : ''}`}
              />
            ))}
          </Stack>
        </Checkbox.Group>
        <TextInput
          label="Описание"
          placeholder="Например, «Хантфлоу, воронка разработки»"
          maxLength={200}
          {...form.getInputProps('description')}
        />
        <Text size="xs" c="dimmed">
          События с контактами уходят только по кандидатам, которые сами их открыли: приняли
          приглашение или откликнулись.
        </Text>
        {failure && (
          <Alert color="signal" variant="light">
            {failure}
          </Alert>
        )}
        <Group>
          <Button type="submit" loading={create.isPending}>
            Подключить
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
