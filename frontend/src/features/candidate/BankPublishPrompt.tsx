import { Alert, Button, Card, Group, Stack, Text, ThemeIcon } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconBuildingBank } from '@tabler/icons-react';
import { useBankPublication, useConsents } from '@/api/candidate';
import { errorMessage } from '@/api/errors';

export function BankPublishPrompt() {
  // Подтверждённая категория без публикации никому не видна: публикация — отдельное
  // согласие по 152-ФЗ. Подсказка появляется, пока согласия нет, и исчезает сразу
  // после него. Отозвать согласие можно в разделе «Приватность».
  const consents = useConsents();
  const publication = useBankPublication();
  if (!consents.data || consents.data.bank_publication) return null;
  const publish = () =>
    publication.mutate(true, {
      onSuccess: () =>
        notifications.show({
          color: 'teal',
          title: 'Профиль опубликован',
          message: 'Работодатели видят вашу обезличенную карточку в банке кандидатов',
        }),
    });
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="wrap" gap="md">
          <Group gap="md" wrap="nowrap" align="flex-start" style={{ flex: '1 1 360px' }}>
            <ThemeIcon color="signal" variant="light" radius="md" size={40}>
              <IconBuildingBank size={22} />
            </ThemeIcon>
            <Stack gap={4}>
              <Text fw={700}>Работодатели пока не видят вас в банке кандидатов</Text>
              <Text size="sm" c="dimmed" lh={1.6}>
                Публикация — отдельное согласие. Компании увидят обезличенную карточку: категорию,
                подтверждённые навыки и индекс. Имя и контакты откроются, только если вы примете
                приглашение. Отозвать согласие можно в разделе «Приватность».
              </Text>
            </Stack>
          </Group>
          <Button onClick={publish} loading={publication.isPending}>
            Опубликовать профиль
          </Button>
        </Group>
        {publication.isError && (
          <Alert color="signal" variant="light">
            {errorMessage(publication.error)}
          </Alert>
        )}
      </Stack>
    </Card>
  );
}
