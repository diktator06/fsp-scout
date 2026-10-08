import { Card, Code, List, Stack, Text, Title } from '@mantine/core';
import { CodeBlock } from '@/shared/ui/CodeBlock';

const VERIFY_SNIPPET = `import hashlib, hmac, time

def verify(secret: str, headers: dict, body: bytes) -> bool:
    timestamp = headers["X-Scout-Timestamp"]
    if abs(time.time() - int(timestamp)) > 300:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, headers["X-Scout-Signature"])`;

export function SignatureGuide() {
  return (
    <Card>
      <Stack gap="sm">
        <Title order={4}>Как ATS принимает события</Title>
        <List size="sm" spacing={4}>
          <List.Item>
            POST с JSON: <Code>id</Code>, <Code>type</Code>, <Code>created_at</Code>,{' '}
            <Code>data</Code>.
          </List.Item>
          <List.Item>
            Подпись <Code>X-Scout-Signature</Code> — HMAC-SHA256 от «метка времени.тело».
          </List.Item>
          <List.Item>
            Повтор с тем же <Code>X-Scout-Event-Id</Code> — дубль, его нужно пропустить.
          </List.Item>
          <List.Item>
            Ответ 2xx — доставлено; иначе повторы через 1, 5, 30 минут, 2 и 6 часов.
          </List.Item>
        </List>
        <CodeBlock code={VERIFY_SNIPPET} language="python" label="Проверка подписи на Python" />
        <Text size="xs" c="dimmed">
          Подписи старше пяти минут отвергайте: так перехваченный запрос нельзя повторить.
        </Text>
      </Stack>
    </Card>
  );
}
