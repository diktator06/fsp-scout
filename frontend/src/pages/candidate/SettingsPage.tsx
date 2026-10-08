import {
  Alert,
  Button,
  Card,
  Checkbox,
  Group,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconBuildingBank, IconEyeOff } from '@tabler/icons-react';
import { Link } from 'react-router';
import {
  useBankPublication,
  useCandidateProfile,
  useConsents,
  usePrivacySettings,
  useUpdatePrivacy,
} from '@/api/candidate';
import { errorMessage } from '@/api/errors';
import type { CandidateProfile, ContactChannel, PrivacySettings } from '@/api/types';
import { CONTACT_CHANNEL_LABELS, WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import { formatDateTime, formatRub, pluralizeRu } from '@/shared/lib/format';
import { CategoryBadge, ErrorState, LoadingState, PageHeader } from '@/shared/ui';
import classes from './SettingsPage.module.css';

const VISIBILITY_FIELDS: Array<{
  key: keyof Omit<PrivacySettings, 'revealed_channels'>;
  label: string;
  hint: string;
}> = [
  {
    key: 'show_salary_expectation',
    label: 'Зарплатные ожидания',
    hint: 'Компания поймёт, укладывается ли в вашу планку, ещё до приглашения',
  },
  { key: 'show_city', label: 'Город', hint: 'Важно для офиса и гибрида' },
  {
    key: 'show_company_names',
    label: 'Названия компаний в опыте',
    hint: 'Если выключено, видны только должности и сроки',
  },
  {
    key: 'show_fsp_achievements',
    label: 'Достижения ФСП',
    hint: 'Участия и результаты соревнований после привязки ФСП ID',
  },
];

function CardPreview({
  profile,
  settings,
}: {
  profile: CandidateProfile;
  settings: PrivacySettings;
}) {
  // Живое превью: переключатели сразу меняют то, что увидит работодатель.
  const years = profile.experience_years;
  const experience =
    years === null
      ? 'не указан'
      : Number.isInteger(years)
        ? `${years} ${pluralizeRu(years, ['год', 'года', 'лет'])}`
        : `${String(years).replace('.', ',')} года`;
  const formats = profile.work_formats
    .map((item) => WORK_FORMAT_LABELS[item as keyof typeof WORK_FORMAT_LABELS])
    .join(', ');
  return (
    <div className={classes.preview} aria-label="Как вас видит работодатель">
      <Text size="xs" fw={700} tt="uppercase" c="dimmed" className={classes.previewKicker}>
        Карточка в банке кандидатов
      </Text>
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={6}>
          <Text fw={800} size="lg">
            Кандидат {profile.public_alias}
          </Text>
          {profile.category ? (
            <CategoryBadge
              specialization={profile.category.specialization.name}
              grade={profile.category.grade.code}
              gradeLabel={profile.category.grade.name}
              size="sm"
            />
          ) : (
            <Text size="sm" c="dimmed">
              Категория появится после теста
            </Text>
          )}
        </Stack>
        <IconEyeOff size={20} color="#8f8aa1" aria-hidden="true" />
      </Group>
      <Stack gap={4} mt="md">
        <Text size="sm">
          Опыт: {experience} {formats && `· ${formats}`}
        </Text>
        {settings.show_city && profile.city && <Text size="sm">Город: {profile.city}</Text>}
        {settings.show_salary_expectation && profile.salary_expectation_from && (
          <Text size="sm">
            Ожидания: от {formatRub(profile.salary_expectation_from)} ₽{' '}
            {profile.salary_expectation_gross ? 'до вычета НДФЛ' : 'на руки'}
          </Text>
        )}
        <Text size="sm" c="dimmed">
          Имя, телефон и email — скрыты до принятия приглашения
        </Text>
      </Stack>
    </div>
  );
}

function PrivacyForm({
  profile,
  settings,
}: {
  profile: CandidateProfile;
  settings: PrivacySettings;
}) {
  const update = useUpdatePrivacy();
  const form = useForm<PrivacySettings>({
    initialValues: settings,
    validate: {
      revealed_channels: (value) => (value.length > 0 ? null : 'Нужен хотя бы один способ связи'),
    },
  });

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      const saved = await update.mutateAsync(values);
      form.resetDirty(saved);
      notifications.show({ color: 'teal', message: 'Настройки приватности сохранены' });
    } catch (error) {
      notifications.show({ color: 'signal', message: errorMessage(error) });
    }
  });

  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
      <Card>
        <form onSubmit={handleSubmit} noValidate>
          <Stack gap="lg">
            <Title order={4}>Что видно до приглашения</Title>
            {VISIBILITY_FIELDS.map((field) => (
              <Switch
                key={field.key}
                label={field.label}
                description={field.hint}
                color="fsp"
                {...form.getInputProps(field.key, { type: 'checkbox' })}
              />
            ))}
            <Checkbox.Group<ContactChannel>
              label="Какие контакты открыть после принятия приглашения"
              {...form.getInputProps('revealed_channels')}
            >
              <Group gap="lg" mt="xs">
                {(Object.keys(CONTACT_CHANNEL_LABELS) as ContactChannel[]).map((channel) => (
                  <Checkbox key={channel} value={channel} label={CONTACT_CHANNEL_LABELS[channel]} />
                ))}
              </Group>
            </Checkbox.Group>
            <Group>
              <Button type="submit" loading={update.isPending} disabled={!form.isDirty()}>
                Сохранить
              </Button>
            </Group>
          </Stack>
        </form>
      </Card>
      <CardPreview profile={profile} settings={form.values} />
    </SimpleGrid>
  );
}

function BankPublication() {
  // Отдельное согласие на публикацию в банке кандидатов — требование ТЗ к ПДн.
  // Отзыв действует сразу: карточка пропадает из поиска работодателей.
  const consents = useConsents();
  const publication = useBankPublication();
  if (!consents.data) return null;
  const granted = consents.data.bank_publication;

  return (
    <Card>
      <Group justify="space-between" align="flex-start" wrap="wrap" gap="lg">
        <Group gap="md" align="flex-start" wrap="nowrap" maw={640}>
          <IconBuildingBank size={28} color="#520978" />
          <Stack gap={4}>
            <Title order={4}>Публикация в банке кандидатов</Title>
            <Text size="sm" c="dimmed" lh={1.6}>
              Пока согласие не дано, работодатели не найдут вас в поиске — даже с подтверждённой
              категорией. Отозвать согласие можно в любой момент.
            </Text>
            {granted && consents.data.bank_publication_granted_at && (
              <Text size="xs" c="dimmed">
                Согласие дано {formatDateTime(consents.data.bank_publication_granted_at)}
              </Text>
            )}
          </Stack>
        </Group>
        <Switch
          size="lg"
          color="teal"
          checked={granted}
          onChange={(event) => publication.mutate(event.currentTarget.checked)}
          disabled={publication.isPending}
          label={granted ? 'Опубликован' : 'Скрыт'}
          aria-label="Согласие на публикацию в банке кандидатов"
        />
      </Group>
      {publication.isError && (
        <Alert color="signal" variant="light" mt="md">
          {errorMessage(publication.error)}
        </Alert>
      )}
    </Card>
  );
}

export function SettingsPage() {
  const profile = useCandidateProfile();
  const privacy = usePrivacySettings();
  const header = (
    <PageHeader
      kicker="Приватность"
      title="Кто и что видит"
      description="Работодатель сначала видит обезличенную карточку. Здесь вы решаете, что в неё попадёт и какие контакты откроются."
    />
  );

  if (profile.isPending || privacy.isPending) {
    return (
      <>
        {header}
        <LoadingState />
      </>
    );
  }
  const failed = profile.error ?? privacy.error;
  if (failed || !profile.data || !privacy.data) {
    return (
      <>
        {header}
        <ErrorState message={errorMessage(failed)} onRetry={() => void privacy.refetch()} />
      </>
    );
  }
  return (
    <>
      {header}
      <Stack gap="lg">
        <BankPublication />
        <PrivacyForm profile={profile.data} settings={privacy.data} />
        <Card padding="lg">
          <Group justify="space-between" wrap="wrap" gap="sm">
            <Stack gap={4}>
              <Title order={4}>Мои данные</Title>
              <Text size="sm" c="dimmed">
                Копия всего, что хранит платформа, и удаление аккаунта вместе с данными.
              </Text>
            </Stack>
            <Button component={Link} to="/c/account" variant="light">
              Открыть
            </Button>
          </Group>
        </Card>
      </Stack>
    </>
  );
}
