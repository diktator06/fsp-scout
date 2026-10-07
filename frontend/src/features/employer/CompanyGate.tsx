import { Button, Card, Group, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconBuildingSkyscraper } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { useEmployerProfile } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import { ErrorState, LoadingState } from '@/shared/ui';

export function CompanyGate({ children }: { children: ReactNode }) {
  // Подбор и приглашения идут от имени компании. Пока её профиль не заполнен,
  // вместо раздела показываем понятный следующий шаг, а не ошибку 409 от API.
  const profile = useEmployerProfile();
  if (profile.isPending) return <LoadingState />;
  if (profile.isError) {
    return (
      <ErrorState message={errorMessage(profile.error)} onRetry={() => void profile.refetch()} />
    );
  }
  if (profile.data.company) return <>{children}</>;
  return (
    <Card>
      <Group align="flex-start" gap="lg" wrap="nowrap">
        <ThemeIcon size={48} radius="md" variant="light" color="fsp">
          <IconBuildingSkyscraper size={26} />
        </ThemeIcon>
        <Stack gap="sm" align="flex-start">
          <Title order={3}>Сначала — профиль компании</Title>
          <Text c="dimmed" maw={560}>
            Кандидат видит в приглашении название компании, отрасль и вилку. Заполнение займёт пару
            минут.
          </Text>
          <Button component={Link} to="/e/company">
            Заполнить профиль компании
          </Button>
        </Stack>
      </Group>
    </Card>
  );
}
