import {
  ActionIcon,
  Alert,
  Button,
  Card,
  Chip,
  Group,
  Input,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  TagsInput,
  Text,
  TextInput,
  Textarea,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle, IconPlus, IconTrash } from '@tabler/icons-react';
import { useState, type ReactNode } from 'react';
import { useUpdateProfile } from '@/api/candidate';
import { errorMessage, fieldErrors } from '@/api/errors';
import type { CandidateProfile, SearchStatus, TeamRole, WorkFormat } from '@/api/types';
import {
  SEARCH_STATUS_LABELS,
  TEAM_ROLE_LABELS,
  WORK_FORMAT_LABELS,
  toOptions,
} from '@/shared/lib/candidate';
import { SkillPicker } from './SkillPicker';
import {
  profileToValues,
  validateExperience,
  valuesToPayload,
  type ProfileFormValues,
} from './profileValues';
import classes from './ProfileForm.module.css';

interface ProfileFormProps {
  profile: CandidateProfile;
  variant: 'onboarding' | 'full';
  submitLabel?: string;
  onSaved?: (profile: CandidateProfile) => void;
}

const SKILL_LEVELS = ['1', '2', '3', '4', '5'];

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <Card>
      <Stack gap="lg">
        <Stack gap={4}>
          <Title order={4}>{title}</Title>
          {hint && (
            <Text size="sm" c="dimmed">
              {hint}
            </Text>
          )}
        </Stack>
        {children}
      </Stack>
    </Card>
  );
}

export function ProfileForm({ profile, variant, submitLabel, onSaved }: ProfileFormProps) {
  // Одна форма на два сценария. В онбординге — минимум для перехода к опросу
  // (имя, опыт, формат работы) и ожидания. На странице профиля — анкета целиком
  // с навыками, местами работы и образованием.
  const update = useUpdateProfile();
  const [failure, setFailure] = useState<string | null>(null);
  const full = variant === 'full';

  const form = useForm<ProfileFormValues>({
    initialValues: profileToValues(profile),
    validate: {
      full_name: (value) => (value.trim().length >= 2 ? null : 'Как к вам обращаться?'),
      experience_years: (value) => (value === '' ? 'Укажите стаж, можно 0' : null),
      work_formats: (value) => (value.length > 0 ? null : 'Выберите хотя бы один формат'),
      experiences: { started_on: (_, values, path) => experienceError(values, path) },
      educations: {
        institution: (value) => (value.trim().length >= 2 ? null : 'Укажите учебное заведение'),
      },
    },
  });

  function experienceError(values: ProfileFormValues, path: string): string | null {
    // Ошибка периода показывается под полем начала: так её видно рядом с датами.
    const index = Number(path.split('.')[1]);
    const job = values.experiences[index];
    return job ? validateExperience(job) : null;
  }

  const handleSubmit = form.onSubmit(async (values) => {
    setFailure(null);
    try {
      const saved = await update.mutateAsync(valuesToPayload(values));
      form.resetDirty(profileToValues(saved));
      notifications.show({ color: 'teal', message: 'Профиль сохранён' });
      onSaved?.(saved);
    } catch (error) {
      // Ошибки полей с сервера раскладываем по форме. Пути вида experiences.0
      // совпадают с путями @mantine/form, поэтому ставим их как есть.
      const byField = fieldErrors(error);
      if (Object.keys(byField).length > 0) {
        form.setErrors(byField);
        setFailure('Проверьте отмеченные поля');
        return;
      }
      setFailure(errorMessage(error));
    }
  });

  const basics = (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
      <TextInput
        label="Имя и фамилия"
        placeholder="Иван Петров"
        autoComplete="name"
        required
        {...form.getInputProps('full_name')}
      />
      <TextInput
        label="Город"
        placeholder="Казань"
        autoComplete="address-level2"
        {...form.getInputProps('city')}
      />
      <NumberInput
        label="Коммерческий опыт, лет"
        description="Можно дробное: 1,5 года"
        min={0}
        max={60}
        step={0.5}
        decimalScale={1}
        decimalSeparator=","
        allowNegative={false}
        required
        {...form.getInputProps('experience_years')}
      />
      <Select<SearchStatus>
        label="Статус поиска"
        data={toOptions(SEARCH_STATUS_LABELS)}
        allowDeselect={false}
        size="md"
        {...form.getInputProps('search_status')}
      />
    </SimpleGrid>
  );

  const workSetup = (
    <Stack gap="md">
      <Input.Wrapper label="Формат работы" required error={form.errors.work_formats}>
        <Chip.Group<true, WorkFormat>
          multiple
          value={form.values.work_formats}
          onChange={(value) => form.setFieldValue('work_formats', value)}
        >
          <Group gap="xs" mt={8}>
            {toOptions(WORK_FORMAT_LABELS).map((option) => (
              <Chip key={option.value} value={option.value} color="fsp" variant="light">
                {option.label}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </Input.Wrapper>
      <Input.Wrapper label="Роли в команде" description="Чем вы готовы заниматься помимо задач">
        <Chip.Group<true, TeamRole>
          multiple
          value={form.values.team_roles}
          onChange={(value) => form.setFieldValue('team_roles', value)}
        >
          <Group gap="xs" mt={8}>
            {toOptions(TEAM_ROLE_LABELS).map((option) => (
              <Chip key={option.value} value={option.value} color="lilac" variant="light">
                {option.label}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </Input.Wrapper>
      <Switch
        label="Готов к переезду"
        color="fsp"
        {...form.getInputProps('relocation_ready', { type: 'checkbox' })}
      />
    </Stack>
  );

  const expectations = (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
      <NumberInput
        label="Зарплата от, ₽ в месяц"
        description="Работодатель увидит её, только если вы разрешите в настройках приватности"
        thousandSeparator=" "
        min={0}
        step={5000}
        allowNegative={false}
        allowDecimal={false}
        hideControls
        {...form.getInputProps('salary_expectation_from')}
      />
      <Input.Wrapper
        size="md"
        label="Сумма указана"
        description="Компании пишут вилки по-разному, поэтому уточняем базу"
      >
        <SegmentedControl
          mt={6}
          fullWidth
          data={[
            { value: 'gross', label: 'до вычета НДФЛ' },
            { value: 'net', label: 'на руки' },
          ]}
          value={form.values.salary_expectation_gross ? 'gross' : 'net'}
          onChange={(value) => form.setFieldValue('salary_expectation_gross', value === 'gross')}
        />
      </Input.Wrapper>
    </SimpleGrid>
  );

  const contacts = (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
      <TextInput
        label="Telegram"
        placeholder="@nickname"
        autoComplete="off"
        {...form.getInputProps('telegram')}
      />
      <TextInput
        label="Телефон"
        placeholder="+7 999 123-45-67"
        autoComplete="tel"
        inputMode="tel"
        {...form.getInputProps('phone')}
      />
    </SimpleGrid>
  );

  return (
    <form onSubmit={handleSubmit} noValidate>
      <Stack gap="lg">
        {full ? (
          <>
            <Section title="Основное" hint="Имя и контакты скрыты, пока вы не примете приглашение">
              {basics}
              {contacts}
              <Textarea
                label="О себе"
                description="Пара предложений о том, что вы делаете лучше всего"
                autosize
                minRows={3}
                maxRows={8}
                maxLength={3000}
                {...form.getInputProps('about')}
              />
            </Section>
            <Section title="Формат и ожидания">
              {workSetup}
              {expectations}
            </Section>
            <Section
              title="Навыки"
              hint="Отметки «подтверждён» навыки получают после теста — их нельзя поставить вручную"
            >
              <SkillPicker
                label="Языки, фреймворки, базы данных и инструменты"
                value={form.values.skills.map((item) => item.skill)}
                onChange={(skills) =>
                  form.setFieldValue(
                    'skills',
                    skills.map(
                      (skill) =>
                        form.values.skills.find((item) => item.skill.id === skill.id) ?? {
                          skill,
                          self_level: null,
                        },
                    ),
                  )
                }
                maxValues={40}
              />
              {form.values.skills.length > 0 && (
                <Stack gap={6}>
                  <Text size="sm" fw={600}>
                    Самооценка уровня
                  </Text>
                  {form.values.skills.map((item, index) => (
                    <Group
                      key={item.skill.id}
                      justify="space-between"
                      wrap="wrap"
                      gap="xs"
                      className={classes.skillRow}
                    >
                      <Text size="sm" fw={600}>
                        {item.skill.name}
                        {profile.skills.find((own) => own.skill.id === item.skill.id)
                          ?.is_verified && (
                          <Text span size="xs" c="teal.8" fw={700} ml={8}>
                            подтверждён тестом
                          </Text>
                        )}
                      </Text>
                      <SegmentedControl
                        size="xs"
                        data={SKILL_LEVELS}
                        value={item.self_level ? String(item.self_level) : ''}
                        onChange={(value) =>
                          form.setFieldValue(`skills.${index}.self_level`, Number(value))
                        }
                        aria-label={`Уровень владения: ${item.skill.name}`}
                      />
                    </Group>
                  ))}
                  <Text size="xs" c="dimmed">
                    1 — знаком по учебным задачам, 5 — могу научить других и разобрать сложный
                    случай
                  </Text>
                </Stack>
              )}
              <TagsInput
                label="Софт-скиллы"
                placeholder="Например, менторство — Enter, чтобы добавить"
                maxTags={10}
                size="md"
                {...form.getInputProps('soft_skills')}
              />
            </Section>
            <Section title="Опыт работы">
              {form.values.experiences.length === 0 && (
                <Text size="sm" c="dimmed">
                  Пока пусто. Названия компаний работодатель увидит, только если вы это разрешите.
                </Text>
              )}
              {form.values.experiences.map((_, index) => (
                <div key={index} className={classes.entry}>
                  <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                    <TextInput
                      label="Компания"
                      required
                      {...form.getInputProps(`experiences.${index}.company_name`)}
                    />
                    <TextInput
                      label="Должность"
                      required
                      {...form.getInputProps(`experiences.${index}.position`)}
                    />
                    <TextInput
                      label="Начало"
                      type="month"
                      placeholder="ГГГГ-ММ"
                      required
                      {...form.getInputProps(`experiences.${index}.started_on`)}
                    />
                    <TextInput
                      label="Окончание"
                      type="month"
                      placeholder="ГГГГ-ММ"
                      description="Пусто — работаю сейчас"
                      {...form.getInputProps(`experiences.${index}.ended_on`)}
                    />
                  </SimpleGrid>
                  <Textarea
                    mt="sm"
                    label="Чем занимались"
                    autosize
                    minRows={2}
                    maxLength={2000}
                    {...form.getInputProps(`experiences.${index}.description`)}
                  />
                  <ActionIcon
                    variant="subtle"
                    color="signal"
                    className={classes.remove}
                    onClick={() => form.removeListItem('experiences', index)}
                    aria-label="Удалить место работы"
                  >
                    <IconTrash size={18} />
                  </ActionIcon>
                </div>
              ))}
              <Button
                variant="light"
                leftSection={<IconPlus size={16} />}
                onClick={() =>
                  form.insertListItem('experiences', {
                    company_name: '',
                    position: '',
                    started_on: '',
                    ended_on: '',
                    description: '',
                  })
                }
                disabled={form.values.experiences.length >= 20}
                className={classes.addButton}
              >
                Добавить место работы
              </Button>
            </Section>
            <Section title="Образование">
              {form.values.educations.map((_, index) => (
                <div key={index} className={classes.entry}>
                  <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                    <TextInput
                      label="Учебное заведение"
                      required
                      {...form.getInputProps(`educations.${index}.institution`)}
                    />
                    <TextInput
                      label="Степень или программа"
                      {...form.getInputProps(`educations.${index}.degree`)}
                    />
                    <NumberInput
                      label="Год окончания"
                      min={1950}
                      max={2035}
                      allowDecimal={false}
                      hideControls
                      {...form.getInputProps(`educations.${index}.graduated_year`)}
                    />
                  </SimpleGrid>
                  <ActionIcon
                    variant="subtle"
                    color="signal"
                    className={classes.remove}
                    onClick={() => form.removeListItem('educations', index)}
                    aria-label="Удалить запись об образовании"
                  >
                    <IconTrash size={18} />
                  </ActionIcon>
                </div>
              ))}
              <Button
                variant="light"
                leftSection={<IconPlus size={16} />}
                onClick={() =>
                  form.insertListItem('educations', {
                    institution: '',
                    degree: '',
                    graduated_year: '',
                  })
                }
                disabled={form.values.educations.length >= 10}
                className={classes.addButton}
              >
                Добавить образование
              </Button>
            </Section>
          </>
        ) : (
          <Card>
            <Stack gap="lg">
              {basics}
              {workSetup}
              {expectations}
              <Text size="sm" c="dimmed">
                Навыки, места работы и образование можно добавить позже в разделе «Профиль». Для
                теста стек спросим на следующем шаге.
              </Text>
            </Stack>
          </Card>
        )}

        {failure && (
          <Alert color="signal" variant="light" icon={<IconAlertCircle size={18} />}>
            {failure}
          </Alert>
        )}

        <div className={classes.actions} data-sticky={full || undefined}>
          {full && (
            <Text size="sm" c="dimmed">
              {form.isDirty() ? 'Есть несохранённые изменения' : 'Все изменения сохранены'}
            </Text>
          )}
          <Button type="submit" size="md" loading={update.isPending}>
            {submitLabel ?? 'Сохранить'}
          </Button>
        </div>
      </Stack>
    </form>
  );
}
