import { Button, Group, RingProgress, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconFileTypePdf } from '@tabler/icons-react';
import { useState } from 'react';
import { downloadProfilePdf, useCandidateProfile } from '@/api/candidate';
import { errorMessage } from '@/api/errors';
import { ProfileForm } from '@/features/candidate/ProfileForm';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

export function ProfilePage() {
  const profile = useCandidateProfile();
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async (alias: string) => {
    setDownloading(true);
    try {
      await downloadProfilePdf(alias);
    } catch (error) {
      notifications.show({
        color: 'signal',
        title: 'PDF не скачался',
        message: errorMessage(error),
      });
    } finally {
      setDownloading(false);
    }
  };

  if (profile.isPending) {
    return (
      <>
        <PageHeader kicker="Профиль" title="Анкета специалиста" />
        <LoadingState blocks={3} />
      </>
    );
  }
  if (profile.isError) {
    return (
      <ErrorState message={errorMessage(profile.error)} onRetry={() => void profile.refetch()} />
    );
  }

  const data = profile.data;
  return (
    <>
      <PageHeader
        kicker={`Профиль · ${data.public_alias}`}
        title="Анкета специалиста"
        description="Работодатели видят обезличенную карточку под псевдонимом. Имя и контакты открываются, когда вы примете приглашение."
        actions={
          <Group gap="md" wrap="nowrap">
            <Group gap={8} wrap="nowrap">
              <RingProgress
                size={52}
                thickness={5}
                roundCaps
                sections={[{ value: data.completeness, color: 'fsp' }]}
                label={
                  <Text ta="center" size="xs" fw={700} className="tabular">
                    {data.completeness}%
                  </Text>
                }
                aria-label={`Профиль заполнен на ${data.completeness}%`}
              />
              <Stack gap={0} visibleFrom="sm">
                <Text size="xs" c="dimmed">
                  Заполнено
                </Text>
                <Text size="sm" fw={700}>
                  {data.completeness < 100 ? 'Можно лучше' : 'Полностью'}
                </Text>
              </Stack>
            </Group>
            <Button
              variant="default"
              leftSection={<IconFileTypePdf size={18} />}
              loading={downloading}
              onClick={() => handleDownload(data.public_alias)}
            >
              Скачать PDF
            </Button>
          </Group>
        }
      />
      <ProfileForm key={data.updated_at} profile={data} variant="full" />
    </>
  );
}
