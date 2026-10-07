import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  List,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconCircleCheck,
  IconEyeOff,
  IconId,
  IconLinkOff,
  IconRefresh,
  IconTrophy,
} from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useFspProfile, useStartFspLink, useSyncFsp, useUnlinkFsp } from '@/api/fsp';
import type { FspProfile } from '@/api/types';
import { FspAchievementList } from '@/features/fsp/FspAchievementList';
import { FspScoreBreakdown } from '@/features/fsp/FspScoreBreakdown';
import { FSP_STATE_LABELS } from '@/shared/lib/fsp';
import { formatDateTime } from '@/shared/lib/format';
import { ErrorState, LoadingState, PageHeader, VerifiedScoreBar } from '@/shared/ui';

const SHARED_DATA = [
  'идентификатор участника ФСП, регион и спортивный разряд',
  'соревнования: название, уровень, дисциплина, дата, формат и команда',
  'результат: место, число участников, статус и ссылка на протокол',
];

function LinkCard({ enabled }: { enabled: boolean }) {
  // Привязка начинается с отдельного согласия (152-ФЗ): без него кнопка недоступна.
  // Дальше браузер уходит на страницу ФСП ID и возвращается с кодом авторизации.
  const [consent, setConsent] = useState(false);
  const start = useStartFspLink();
  const handleLink = () => {
    start.mutate(consent, {
      onSuccess: (authorization) => window.location.assign(authorization.authorization_url),
    });
  };
  return (
    <Card>
      <Stack gap="md">
        <Group gap="sm">
          <ThemeIcon color="fsp" variant="light" radius="md" size={40}>
            <IconId size={22} />
          </ThemeIcon>
          <div>
            <Title order={4}>Привязать ФСП ID</Title>
            <Text size="sm" c="dimmed">
              Вход через аккаунт участника Федерации спортивного программирования
            </Text>
          </div>
        </Group>
        <Text size="sm" lh={1.6}>
          Участия и места подтверждает реестр ФСП, поэтому работодатель видит их с отметкой
          «подтверждено» и ссылкой на протокол соревнования.
        </Text>
        <div>
          <Text size="sm" fw={600} mb={6}>
            Что «Скаут» получит из реестра
          </Text>
          <List size="sm" spacing={4}>
            {SHARED_DATA.map((item) => (
              <List.Item key={item}>{item}</List.Item>
            ))}
          </List>
          <Text size="xs" c="dimmed" mt={6}>
            Дату рождения и документы не запрашиваем. Отвязать ФСП ID можно в любой момент — данные
            удалятся.
          </Text>
        </div>
        <Checkbox
          checked={consent}
          onChange={(event) => setConsent(event.currentTarget.checked)}
          label={
            <>
              Согласен на получение моих данных из реестра ФСП в соответствии с{' '}
              <Anchor component={Link} to="/legal/personal-data" target="_blank">
                политикой обработки персональных данных
              </Anchor>
            </>
          }
        />
        {start.isError && (
          <Alert color="signal" variant="light" icon={<IconAlertTriangle size={18} />}>
            {errorMessage(start.error)}
          </Alert>
        )}
        <Group>
          <Button
            leftSection={<IconId size={18} />}
            onClick={handleLink}
            disabled={!consent || !enabled}
            loading={start.isPending}
          >
            Привязать ФСП ID
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

function LinkedCard({ profile }: { profile: FspProfile }) {
  // Привязанный профиль: откуда данные, когда сверялись с реестром, обновление и отвязка.
  const sync = useSyncFsp();
  const unlink = useUnlinkFsp();
  const [confirmOpened, confirm] = useDisclosure(false);
  const failed = profile.last_sync?.status === 'error';
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <ThemeIcon color="teal" variant="light" radius="md" size={40}>
              <IconCircleCheck size={22} />
            </ThemeIcon>
            <div>
              <Title order={4}>ФСП ID привязан</Title>
              <Text size="sm" c="dimmed">
                Участник {profile.participant_id}
                {profile.sport_rank ? ` · ${profile.sport_rank}` : ''}
                {profile.region ? ` · ${profile.region}` : ''}
              </Text>
            </div>
          </Group>
          <Badge color={profile.state === 'linked' ? 'teal' : 'gray'} variant="light">
            {FSP_STATE_LABELS[profile.state]}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          {profile.synced_at
            ? `Сверено с реестром ${formatDateTime(profile.synced_at)}`
            : 'Данные реестра ещё не загружены'}
        </Text>
        {failed && (
          <Alert color="signal" variant="light" icon={<IconAlertTriangle size={18} />}>
            Реестр ФСП сейчас недоступен. Показаны данные последней успешной сверки, попробуйте
            обновить позже.
          </Alert>
        )}
        {!profile.visible_to_employers && (
          <Alert color="lilac" variant="light" icon={<IconEyeOff size={18} />}>
            Достижения скрыты от работодателей и не учитываются в индексе, который они видят.{' '}
            <Anchor component={Link} to="/c/settings" fw={600}>
              Изменить в настройках приватности
            </Anchor>
          </Alert>
        )}
        {sync.isError && (
          <Alert color="signal" variant="light">
            {errorMessage(sync.error)}
          </Alert>
        )}
        <Group gap="sm">
          <Button
            variant="light"
            leftSection={<IconRefresh size={16} />}
            onClick={() => sync.mutate()}
            loading={sync.isPending}
          >
            Обновить из реестра
          </Button>
          <Button
            variant="subtle"
            color="gray"
            leftSection={<IconLinkOff size={16} />}
            onClick={confirm.open}
          >
            Отвязать
          </Button>
        </Group>
      </Stack>
      <Modal opened={confirmOpened} onClose={confirm.close} title="Отвязать ФСП ID?" centered>
        <Stack gap="md">
          <Text size="sm" lh={1.6}>
            Участия удалятся из «Скаута», согласие на получение данных ФСП будет отозвано, а индекс
            профиля пересчитается без них. Привязать снова можно в любой момент.
          </Text>
          {unlink.isError && (
            <Alert color="signal" variant="light">
              {errorMessage(unlink.error)}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={confirm.close}>
              Оставить
            </Button>
            <Button
              color="signal"
              loading={unlink.isPending}
              onClick={() => unlink.mutate(undefined, { onSuccess: confirm.close })}
            >
              Отвязать
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

export function FspPage() {
  const profile = useFspProfile();

  const header = (
    <PageHeader
      kicker="Достижения ФСП"
      title="Соревнования, которые подтверждает реестр"
      description="Привязка ФСП ID добавляет к индексу профиля до 15 баллов из 100. Без неё оценка строится по тесту и профилю — это не штраф."
    />
  );

  if (profile.isPending) {
    return (
      <>
        {header}
        <LoadingState />
      </>
    );
  }
  if (profile.isError) {
    return (
      <>
        {header}
        <ErrorState message={errorMessage(profile.error)} onRetry={() => void profile.refetch()} />
      </>
    );
  }

  const data = profile.data;
  const linked = data.state !== 'not_linked';
  return (
    <>
      {header}
      {!data.enabled && (
        <Alert color="gray" variant="light" mb="lg">
          Интеграция с ФСП на этом стенде выключена.
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg" mb="lg">
        {linked ? <LinkedCard profile={data} /> : <LinkCard enabled={data.enabled} />}
        <Card>
          <Stack gap="md">
            <Title order={4}>Индекс подтверждённого профиля</Title>
            {data.verified_score ? (
              <VerifiedScoreBar
                score={Math.round(data.verified_score.total)}
                factors={data.verified_score.components.map((item) => ({
                  key: item.key,
                  label: item.label,
                  value: item.value,
                  weight: item.weight,
                  hint:
                    item.key === 'fsp' && item.value === 0
                      ? FSP_STATE_LABELS[data.visible_to_employers ? data.state : 'hidden']
                      : undefined,
                }))}
              />
            ) : (
              <Text size="sm" c="dimmed" lh={1.6}>
                Индекс появится, когда у вас будет категория: пройдите опрос и выберите уровень
                теста.
              </Text>
            )}
          </Stack>
        </Card>
      </SimpleGrid>

      {linked && (
        <Card mb="lg">
          <Stack gap="md">
            <Group justify="space-between" wrap="wrap" gap="sm">
              <Group gap="sm">
                <ThemeIcon color="fsp" variant="light" radius="md" size={36}>
                  <IconTrophy size={20} />
                </ThemeIcon>
                <Title order={4}>Участия и результаты</Title>
              </Group>
              <Text size="sm" fw={600}>
                {data.score.summary}
              </Text>
            </Group>
            {data.achievements.length > 0 ? (
              <>
                <FspScoreBreakdown score={data.score} />
                <FspAchievementList items={data.achievements} />
              </>
            ) : (
              <Text size="sm" c="dimmed" lh={1.6}>
                В реестре ФСП пока нет ваших участий. Это штатное состояние: индекс строится по
                тесту и профилю, а после первого соревнования нажмите «Обновить из реестра».
              </Text>
            )}
          </Stack>
        </Card>
      )}
    </>
  );
}
