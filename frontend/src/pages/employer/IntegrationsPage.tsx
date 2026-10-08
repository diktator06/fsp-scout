import { Alert, Button, Card, Group, Modal, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDownload, IconFlask, IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import {
  downloadCandidatesExport,
  useConnectSandbox,
  useDeliveries,
  useWebhookEvents,
  useWebhooks,
} from '@/api/integrations';
import type { WebhookEndpointWithSecret } from '@/api/types';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { DeliveryLog } from '@/features/integrations/DeliveryLog';
import { EndpointCard } from '@/features/integrations/EndpointCard';
import { EndpointForm } from '@/features/integrations/EndpointForm';
import { SecretModal } from '@/features/integrations/SecretModal';
import { SignatureGuide } from '@/features/integrations/SignatureGuide';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

function ExportCard() {
  // Выгрузка — для ATS без вебхуков: файл импортируется вручную или по расписанию.
  const [pending, setPending] = useState<'csv' | 'json' | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const download = async (format: 'csv' | 'json') => {
    setPending(format);
    setFailure(null);
    try {
      await downloadCandidatesExport(format);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setPending(null);
    }
  };
  return (
    <Card>
      <Stack gap="sm">
        <Title order={4}>Выгрузка кандидатов</Title>
        <Text size="sm" c="dimmed">
          Все, кто принял ваше приглашение или откликнулся на вакансию: контакты, категория,
          подтверждённость грейда, индекс и навыки. Каждая выгрузка записывается в журнал аудита.
        </Text>
        {failure && (
          <Alert color="signal" variant="light">
            {failure}
          </Alert>
        )}
        <Group gap="xs">
          <Button
            leftSection={<IconDownload size={16} />}
            loading={pending === 'csv'}
            disabled={pending !== null}
            onClick={() => void download('csv')}
          >
            CSV для Excel
          </Button>
          <Button
            variant="default"
            leftSection={<IconDownload size={16} />}
            loading={pending === 'json'}
            disabled={pending !== null}
            onClick={() => void download('json')}
          >
            JSON
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function Integrations() {
  const webhooks = useWebhooks();
  const deliveries = useDeliveries();
  const catalog = useWebhookEvents();
  const sandbox = useConnectSandbox();
  const [formOpened, form] = useDisclosure(false);
  const [revealed, setRevealed] = useState<WebhookEndpointWithSecret | null>(null);

  if (webhooks.isPending || catalog.isPending) return <LoadingState />;
  if (webhooks.isError || catalog.isError) {
    return (
      <ErrorState
        message={errorMessage(webhooks.error ?? catalog.error)}
        onRetry={() => void webhooks.refetch()}
      />
    );
  }
  const hasSandbox = webhooks.data.some((item) => item.is_sandbox);
  return (
    <Stack gap="lg">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Title order={3}>Вебхуки</Title>
        <Group gap="xs">
          {!hasSandbox && (
            <Button
              variant="light"
              leftSection={<IconFlask size={16} />}
              loading={sandbox.isPending}
              onClick={() => sandbox.mutate(undefined, { onSuccess: setRevealed })}
            >
              Подключить песочницу
            </Button>
          )}
          <Button leftSection={<IconPlus size={16} />} onClick={form.open}>
            Подключить ATS
          </Button>
        </Group>
      </Group>
      {sandbox.isError && (
        <Alert color="signal" variant="light">
          {errorMessage(sandbox.error)}
        </Alert>
      )}
      {webhooks.data.length === 0 ? (
        <Card>
          <Stack gap="xs">
            <Text fw={700}>ATS ещё не подключена</Text>
            <Text size="sm" c="dimmed">
              Укажите адрес, на который ваша ATS принимает вебхуки, — или подключите песочницу,
              чтобы посмотреть события и подпись без своей системы.
            </Text>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
          {webhooks.data.map((item) => (
            <EndpointCard
              key={item.id}
              endpoint={item}
              catalog={catalog.data}
              onSecret={setRevealed}
            />
          ))}
        </SimpleGrid>
      )}
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
        <Stack gap="sm">
          <Title order={3}>Журнал доставок</Title>
          {deliveries.isPending ? (
            <LoadingState blocks={2} height={120} />
          ) : deliveries.isError ? (
            <ErrorState
              message={errorMessage(deliveries.error)}
              onRetry={() => void deliveries.refetch()}
            />
          ) : (
            <DeliveryLog deliveries={deliveries.data} catalog={catalog.data} />
          )}
        </Stack>
        <Stack gap="lg">
          <ExportCard />
          <SignatureGuide />
        </Stack>
      </SimpleGrid>
      <Modal opened={formOpened} onClose={form.close} title="Подключить ATS" size="lg">
        <EndpointForm
          onCreated={(endpoint) => {
            form.close();
            setRevealed(endpoint);
          }}
        />
      </Modal>
      <SecretModal endpoint={revealed} onClose={() => setRevealed(null)} />
    </Stack>
  );
}

export function IntegrationsPage() {
  return (
    <>
      <PageHeader
        kicker="Интеграции"
        title="Связь с вашей ATS"
        description="«Скаут» не заменяет ATS компании, а дополняет её: события о кандидатах приходят подписанными вебхуками, а всех, кто открыл контакты, можно выгрузить файлом."
      />
      <CompanyGate>
        <Integrations />
      </CompanyGate>
    </>
  );
}
