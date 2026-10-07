import { Alert, Badge, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconShieldCheck, IconWorld } from '@tabler/icons-react';
import type { CandidateInvitation, ComplaintTarget } from '@/api/types';
import { ComplaintButton } from '@/features/trust/ComplaintButton';
import { formatDate } from '@/shared/lib/format';
import { COMPANY_SIZE_LABELS, TRUST_LEVEL_COPY } from '@/shared/lib/matching';

type CompanyBrief = CandidateInvitation['company'];

interface CompanyCardProps {
  company: CompanyBrief;
  complaint?: { targetType: ComplaintTarget; targetId: string };
}

export function CompanyCard({ company, complaint }: CompanyCardProps) {
  // Компания глазами кандидата: видна сразу, до ответа на приглашение или отклика.
  // Уровень доверия, репутация из фактов и отметка «на проверке» — часть защиты
  // от фиктивных работодателей; там же — кнопка жалобы.
  const trust = TRUST_LEVEL_COPY[company.trust_level];
  const { reputation } = company;
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" gap="sm" align="flex-start">
          <Title order={4}>{company.name}</Title>
          <Badge color={trust.color} variant="light" style={{ flexShrink: 0 }}>
            {trust.label}
          </Badge>
        </Group>
        {company.under_review && (
          <Alert color="signal" variant="light" p="xs">
            Компания на проверке модератора после жалоб кандидатов. Будьте внимательны и не
            переводите деньги работодателю.
          </Alert>
        )}
        {company.industry && <Text size="sm">{company.industry}</Text>}
        {company.size && (
          <Text size="sm" c="dimmed">
            {COMPANY_SIZE_LABELS[company.size]}
            {company.city ? ` · ${company.city}` : ''}
          </Text>
        )}
        {company.description && (
          <Text size="sm" lh={1.6}>
            {company.description}
          </Text>
        )}
        {company.website && (
          <Text size="sm">
            <IconWorld size={14} style={{ verticalAlign: '-2px' }} />{' '}
            <a
              href={
                /^https?:\/\//.test(company.website)
                  ? company.website
                  : `https://${company.website}`
              }
              target="_blank"
              rel="noreferrer noopener"
            >
              {company.website.replace(/^https?:\/\//, '')}
            </a>
          </Text>
        )}
        {reputation && (
          <Group gap={8} wrap="nowrap" align="flex-start">
            <IconShieldCheck
              size={16}
              color="var(--mantine-color-teal-7)"
              style={{ flexShrink: 0, marginTop: 2 }}
            />
            <Text size="sm" c="dimmed">
              {reputation.summary}. На платформе с {formatDate(reputation.on_platform_since)}
            </Text>
          </Group>
        )}
        {complaint && <ComplaintButton {...complaint} />}
      </Stack>
    </Card>
  );
}
