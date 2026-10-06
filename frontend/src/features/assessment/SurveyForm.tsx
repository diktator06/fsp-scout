import {
  Alert,
  Badge,
  Button,
  Card,
  Chip,
  Group,
  Input,
  MultiSelect,
  NumberInput,
  Radio,
  SimpleGrid,
  Skeleton,
  Stack,
  Text,
} from '@mantine/core';
import { IconAlertCircle } from '@tabler/icons-react';
import { useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useBlueprint, useSubmitSurvey } from '@/api/assessment';
import { useGrades, useIndustries, useSpecializations } from '@/api/dictionaries';
import { errorMessage } from '@/api/errors';
import type { CandidateProfile, Skill, Survey } from '@/api/types';
import { SkillPicker } from '@/features/candidate/SkillPicker';
import { groupByDirection, suggestGradeByExperience } from '@/shared/lib/assessment';
import { BlueprintPreview } from './BlueprintPreview';
import classes from './SurveyForm.module.css';

interface SurveyFormProps {
  profile: CandidateProfile;
  survey: Survey | null | undefined;
  onSubmitted: (survey: Survey) => void;
}

interface SurveyErrors {
  specialization?: string;
  skills?: string;
  experience?: string;
  grade?: string;
}

function Step({
  index,
  title,
  hint,
  children,
}: {
  index: number;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className={classes.step} aria-labelledby={`survey-step-${index}`}>
      <span className={classes.stepIndex} aria-hidden="true">
        {index}
      </span>
      <Stack gap="sm" className={classes.stepBody}>
        <div>
          <Text id={`survey-step-${index}`} fw={700} size="lg">
            {title}
          </Text>
          {hint && (
            <Text size="sm" c="dimmed">
              {hint}
            </Text>
          )}
        </div>
        {children}
      </Stack>
    </section>
  );
}

export function SurveyForm({ profile, survey, onSubmitted }: SurveyFormProps) {
  // Опрос задаёт состав теста: специализация определяет компетенции, стек
  // включает языковые темы, заявленный грейд — с какого уровня начнётся тест.
  // Повторный опрос подхватывает прошлые ответы, чтобы не вводить всё заново.
  const specializations = useSpecializations();
  const grades = useGrades();
  const industries = useIndustries();
  const submit = useSubmitSurvey();

  const initialSpecialization = survey?.specialization.id ?? null;
  const initialDirection =
    specializations.data?.find((item) => item.id === initialSpecialization)?.direction_code ?? null;

  const [direction, setDirection] = useState<string | null>(initialDirection);
  const [specializationId, setSpecializationId] = useState<number | null>(initialSpecialization);
  const [skills, setSkills] = useState<Skill[]>(() =>
    survey
      ? profile.skills
          .filter((item) => survey.primary_skill_ids.includes(item.skill.id))
          .map((item) => item.skill)
      : profile.skills.map((item) => item.skill).slice(0, 12),
  );
  const [experience, setExperience] = useState<number | ''>(
    survey?.experience_years ?? profile.experience_years ?? '',
  );
  const [gradeId, setGradeId] = useState<number | null>(survey?.claimed_grade.id ?? null);
  const [industryIds, setIndustryIds] = useState<number[]>(survey?.industry_ids ?? []);
  const [errors, setErrors] = useState<SurveyErrors>({});

  const blueprint = useBlueprint(
    specializationId,
    skills.map((skill) => skill.id),
  );
  const groups = useMemo(
    () => groupByDirection(specializations.data ?? []),
    [specializations.data],
  );
  const activeDirection = direction ?? initialDirection ?? groups[0]?.code ?? null;
  const directionGroup = groups.find((group) => group.code === activeDirection);
  const suggestedGrade = suggestGradeByExperience(experience === '' ? null : experience);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const found: SurveyErrors = {};
    if (specializationId === null) found.specialization = 'Выберите специализацию';
    if (skills.length === 0) found.skills = 'Добавьте хотя бы один навык из основного стека';
    if (experience === '') found.experience = 'Укажите стаж, можно 0';
    if (gradeId === null) found.grade = 'Выберите уровень, который хотите подтвердить';
    setErrors(found);
    if (
      Object.keys(found).length > 0 ||
      specializationId === null ||
      gradeId === null ||
      experience === ''
    ) {
      return;
    }
    try {
      const created = await submit.mutateAsync({
        specialization_id: specializationId,
        claimed_grade_id: gradeId,
        primary_skill_ids: skills.map((skill) => skill.id),
        experience_years: experience,
        industry_ids: industryIds,
      });
      onSubmitted(created);
    } catch {
      // Текст ошибки уже есть в состоянии мутации и показывается над кнопкой.
    }
  };

  if (specializations.isPending || grades.isPending) {
    return <Skeleton height={420} radius="lg" />;
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className={classes.layout}>
        <Card className={classes.formCard}>
          <Stack gap="xl">
            <Step index={1} title="Направление и специализация">
              <Chip.Group
                value={activeDirection}
                onChange={(value) => {
                  setDirection(value);
                  setSpecializationId(null);
                }}
              >
                <Group gap="xs">
                  {groups.map((group) => (
                    <Chip key={group.code} value={group.code} color="fsp" variant="filled">
                      {group.name}
                    </Chip>
                  ))}
                </Group>
              </Chip.Group>
              <Radio.Group
                value={specializationId ? String(specializationId) : null}
                onChange={(value) => setSpecializationId(Number(value))}
                error={errors.specialization}
                aria-label="Специализация"
              >
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                  {directionGroup?.items.map((item) => (
                    <Radio.Card key={item.id} value={String(item.id)} className={classes.choice}>
                      <Group wrap="nowrap" align="flex-start" gap="sm">
                        <Radio.Indicator color="fsp" mt={2} />
                        <div>
                          <Text fw={700}>{item.name}</Text>
                          <Text size="xs" c="dimmed" lh={1.45}>
                            {item.description}
                          </Text>
                        </div>
                      </Group>
                    </Radio.Card>
                  ))}
                </SimpleGrid>
              </Radio.Group>
            </Step>

            <Step
              index={2}
              title="Основной стек"
              hint="То, с чем работаете каждый день. От языка зависит, какие темы войдут в тест"
            >
              <SkillPicker
                label="Навыки"
                value={skills}
                onChange={setSkills}
                maxValues={12}
                error={errors.skills}
                required
              />
            </Step>

            <Step
              index={3}
              title="Опыт и уровень"
              hint="Заявленный уровень видят работодатели с пометкой «не подтверждён», пока вы не пройдёте тест"
            >
              <NumberInput
                label="Коммерческий опыт, лет"
                value={experience}
                onChange={(value) => setExperience(typeof value === 'number' ? value : '')}
                min={0}
                max={60}
                step={0.5}
                decimalScale={1}
                decimalSeparator=","
                allowNegative={false}
                error={errors.experience}
                maw={260}
                required
              />
              <Radio.Group
                value={gradeId ? String(gradeId) : null}
                onChange={(value) => setGradeId(Number(value))}
                error={errors.grade}
                aria-label="Заявленный грейд"
              >
                <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
                  {grades.data?.map((grade) => (
                    <Radio.Card key={grade.id} value={String(grade.id)} className={classes.choice}>
                      <Stack gap={6}>
                        <Group justify="space-between" wrap="nowrap" gap={6}>
                          <Text fw={800}>{grade.name}</Text>
                          <Radio.Indicator color="fsp" />
                        </Group>
                        <Text size="xs" fw={600} c="fsp.7">
                          {grade.experience_hint}
                        </Text>
                        <Text size="xs" c="dimmed" lh={1.45}>
                          {grade.description}
                        </Text>
                        {grade.code === suggestedGrade && (
                          <Badge size="sm" variant="light" color="lilac" className={classes.hint}>
                            по вашему опыту
                          </Badge>
                        )}
                      </Stack>
                    </Radio.Card>
                  ))}
                </SimpleGrid>
              </Radio.Group>
            </Step>

            <Step
              index={4}
              title="Предметная область"
              hint="Необязательно. Поможет с подбором вакансий, на тест не влияет"
            >
              <MultiSelect<number>
                placeholder={industryIds.length === 0 ? 'Финтех, e-commerce, GovTech…' : undefined}
                data={(industries.data ?? []).map((item) => ({ value: item.id, label: item.name }))}
                value={industryIds}
                onChange={setIndustryIds}
                maxValues={3}
                searchable
                clearable
                size="md"
                aria-label="Предметная область"
              />
            </Step>

            {submit.isError && (
              <Alert color="signal" variant="light" icon={<IconAlertCircle size={18} />}>
                {errorMessage(submit.error)}
              </Alert>
            )}
            <Input.Wrapper>
              <Button type="submit" size="md" loading={submit.isPending}>
                Сохранить и выбрать тест
              </Button>
            </Input.Wrapper>
          </Stack>
        </Card>

        <Card className={classes.preview}>
          <BlueprintPreview blueprint={blueprint.data} loading={blueprint.isFetching} />
        </Card>
      </div>
    </form>
  );
}
