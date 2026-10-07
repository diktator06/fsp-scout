import { Alert } from '@mantine/core';
import { IconShieldExclamation } from '@tabler/icons-react';
import { useEmployerProfile } from '@/api/employer';
import { formatDate } from '@/shared/lib/format';

export function RestrictionBanner() {
  // Пока компания на проверке, сервер не даёт приглашать, публиковать вакансии и
  // создавать задачи — баннер объясняет это заранее, а не после отказа формы.
  const profile = useEmployerProfile();
  const company = profile.data?.company;
  if (!company?.restricted_at) return null;
  return (
    <Alert
      color="signal"
      variant="light"
      mb="lg"
      icon={<IconShieldExclamation size={20} />}
      title="Компания на проверке модератора"
    >
      С {formatDate(company.restricted_at)} приглашения, публикация вакансий и новые микрозадачи
      приостановлены. Причина: {company.restriction_reason || 'жалобы кандидатов'}. Уже отправленные
      приглашения и отклики остаются в силе. Модератор разберёт жалобы и снимет ограничение, если
      они не подтвердятся.
    </Alert>
  );
}
