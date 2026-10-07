import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useCompanyModeration } from '@/api/trust';
import type { ModerationCompany, TrustLevel } from '@/api/types';
import { formatDate } from '@/shared/lib/format';
import { TRUST_LEVEL_COPY } from '@/shared/lib/matching';

const TRUST_OPTIONS = Object.entries(TRUST_LEVEL_COPY).map(([value, copy]) => ({
  value,
  label: copy.label,
}));

export function CompanyModerationCard({ company }: { company: ModerationCompany }) {
  // Ограничение приостанавливает приглашения, вакансии и задачи компании; уровень
  // доверия задаёт квоты. Оба решения пишутся в журнал аудита на сервере.
  const moderation = useCompanyModeration(company.id);
  const [reason, setReason] = useState('');
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="wrap" gap="sm" align="flex-start">
          <Stack gap={2}>
            <Text fw={700}>{company.name}</Text>
            <Text size="sm" c="dimmed">
              {company.inn ? `ИНН ${company.inn} · ` : ''}на платформе с{' '}
              {formatDate(company.created_at)}
            </Text>
          </Stack>
          <Select
            aria-label="Уровень доверия"
            size="xs"
            w={180}
            allowDeselect={false}
            data={TRUST_OPTIONS}
            value={company.trust_level}
            disabled={moderation.isPending}
            onChange={(value) =>
              value &&
              value !== company.trust_level &&
              moderation.mutate({ kind: 'trust', trustLevel: value as TrustLevel })
            }
          />
        </Group>
        <Group gap="xs" wrap="wrap">
          <Badge color={company.complaints_open ? 'signal' : 'gray'} variant="light">
            Открытых жалоб: {company.complaints_open}
          </Badge>
          <Badge color={company.complaints_confirmed ? 'signal' : 'gray'} variant="outline">
            Подтверждённых: {company.complaints_confirmed}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          {company.reputation.summary}
        </Text>
        {company.suspicious_vacancies.length > 0 && (
          <Alert color="signal" variant="light" title="Вилка в разы выше рынка" p="sm">
            <List size="sm" spacing={2}>
              {company.suspicious_vacancies.map((title) => (
                <List.Item key={title}>{title}</List.Item>
              ))}
            </List>
          </Alert>
        )}
        {moderation.isError && (
          <Alert color="signal" variant="light">
            {errorMessage(moderation.error)}
          </Alert>
        )}
        {company.restricted_at ? (
          <Alert color="signal" variant="outline" p="sm">
            <Stack gap="xs">
              <Text size="sm">
                Ограничена с {formatDate(company.restricted_at)}. Причина:{' '}
                {company.restriction_reason}
              </Text>
              <Button
                size="xs"
                variant="default"
                loading={moderation.isPending}
                onClick={() => moderation.mutate({ kind: 'lift' })}
                style={{ alignSelf: 'flex-start' }}
              >
                Снять ограничение
              </Button>
            </Stack>
          </Alert>
        ) : (
          <Group gap="xs" wrap="nowrap" align="flex-end">
            <TextInput
              size="xs"
              style={{ flex: 1 }}
              placeholder="Причина ограничения"
              value={reason}
              onChange={(event) => setReason(event.currentTarget.value)}
            />
            <Button
              size="xs"
              color="signal"
              variant="light"
              disabled={reason.trim().length < 5}
              loading={moderation.isPending}
              onClick={() => moderation.mutate({ kind: 'restrict', reason: reason.trim() })}
            >
              Ограничить
            </Button>
          </Group>
        )}
      </Stack>
    </Card>
  );
}
