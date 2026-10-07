import { Badge, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconWorld } from '@tabler/icons-react';
import type { CandidateInvitation } from '@/api/types';
import { COMPANY_SIZE_LABELS, TRUST_LEVEL_COPY } from '@/shared/lib/matching';

type CompanyBrief = CandidateInvitation['company'];

export function CompanyCard({ company }: { company: CompanyBrief }) {
  // Компания глазами кандидата: видна сразу, до ответа на приглашение или отклика.
  // Уровень доверия рядом с названием — часть защиты от фиктивных работодателей.
  const trust = TRUST_LEVEL_COPY[company.trust_level];
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="nowrap" gap="sm">
          <Title order={4}>{company.name}</Title>
          <Badge color={trust.color} variant="light">
            {trust.label}
          </Badge>
        </Group>
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
      </Stack>
    </Card>
  );
}
