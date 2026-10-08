import { Alert, Button, Code, CopyButton, Group, Modal, Stack, Text } from '@mantine/core';
import type { WebhookEndpointWithSecret } from '@/api/types';

interface SecretModalProps {
  endpoint: WebhookEndpointWithSecret | null;
  onClose: () => void;
}

export function SecretModal({ endpoint, onClose }: SecretModalProps) {
  // Полный секрет сервер отдаёт один раз — при подключении или смене. Дальше в
  // кабинете видна только подсказка, поэтому просим сразу сохранить его в ATS.
  return (
    <Modal opened={endpoint !== null} onClose={onClose} title="Секрет подписи" size="lg">
      {endpoint && (
        <Stack gap="md">
          <Text size="sm">
            Им ATS проверяет заголовок <Code>X-Scout-Signature</Code> у каждого события для{' '}
            <Text span fw={600} style={{ wordBreak: 'break-all' }}>
              {endpoint.url}
            </Text>
            .
          </Text>
          <Code block style={{ wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}>
            {endpoint.secret}
          </Code>
          <Alert color="lilac" variant="light">
            Секрет показывается один раз. Потеряли — смените его в карточке получателя.
          </Alert>
          <Group>
            <CopyButton value={endpoint.secret}>
              {({ copied, copy }) => (
                <Button variant={copied ? 'light' : 'filled'} onClick={copy}>
                  {copied ? 'Скопировано' : 'Скопировать'}
                </Button>
              )}
            </CopyButton>
            <Button variant="default" onClick={onClose}>
              Готово
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
