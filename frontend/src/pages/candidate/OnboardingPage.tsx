import { Alert, Button, Card, Stack, Stepper, Text } from '@mantine/core';
import { IconCircleCheck } from '@tabler/icons-react';
import { useMediaQuery } from '@mantine/hooks';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useEligibility, useLatestSurvey } from '@/api/assessment';
import { useCandidateProfile, useCandidateStatus } from '@/api/candidate';
import { errorMessage } from '@/api/errors';
import type { CandidateStatus } from '@/api/types';
import { GradeLauncher } from '@/features/assessment/GradeLauncher';
import { SurveyForm } from '@/features/assessment/SurveyForm';
import { ProfileForm } from '@/features/candidate/ProfileForm';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

const STEP_BY_NAME: Record<string, number> = { profile: 0, survey: 1, grade: 2 };

function stepFromStatus(status: CandidateStatus): number {
  // Тест и «готово» тоже ведут на последний шаг: там либо кнопка «продолжить
  // тест», либо выбор следующего уровня.
  if (status.onboarding_step === 'profile') return 0;
  if (status.onboarding_step === 'survey') return 1;
  return 2;
}

function LaunchStep() {
  const eligibility = useEligibility();
  if (eligibility.isPending) return <LoadingState blocks={1} />;
  if (eligibility.isError) {
    return (
      <ErrorState message={errorMessage(eligibility.error)} onRetry={() => eligibility.refetch()} />
    );
  }
  return (
    <Card>
      <GradeLauncher eligibility={eligibility.data} />
    </Card>
  );
}

export function OnboardingPage() {
  // Мастер из трёх шагов. Начальный шаг берётся из статуса на сервере, поэтому
  // кандидат, вернувшийся через день, продолжает с того же места. Ссылка
  // ?step=survey открывает нужный шаг напрямую (например, «изменить опрос»).
  const [searchParams] = useSearchParams();
  const status = useCandidateStatus();
  const profile = useCandidateProfile();
  const compact = useMediaQuery('(max-width: 36em)');
  const survey = useLatestSurvey();
  const [active, setActive] = useState<number | null>(() => {
    const requested = searchParams.get('step');
    return requested !== null ? (STEP_BY_NAME[requested] ?? null) : null;
  });

  const goTo = (step: number) => {
    // Новый шаг начинается сверху страницы, а не там, где была кнопка «Дальше».
    setActive(step);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const loading = status.isPending || profile.isPending || survey.isPending;
  const failed = status.error ?? profile.error ?? survey.error;

  if (loading) {
    return (
      <>
        <PageHeader kicker="Онбординг" title="Путь к категории" />
        <LoadingState />
      </>
    );
  }
  if (failed || !status.data || !profile.data) {
    return <ErrorState message={errorMessage(failed)} onRetry={() => void status.refetch()} />;
  }

  const current = active ?? stepFromStatus(status.data);
  const maxReachable = stepFromStatus(status.data);

  return (
    <>
      <PageHeader
        kicker="Онбординг"
        title="Путь к категории"
        description="Три шага: коротко о себе, опрос о стеке и тест. Категория появляется только после теста — резюме её не присваивает."
      />
      {status.data.onboarding_step === 'done' && status.data.category && (
        <Alert color="teal" variant="light" icon={<IconCircleCheck size={18} />} mb="lg">
          Категория {status.data.category.title} уже подтверждена. Здесь можно обновить опрос или
          пройти тест на следующий уровень.
        </Alert>
      )}
      <Stepper
        active={current}
        onStepClick={(step) => step <= Math.max(maxReachable, current) && goTo(step)}
        color="fsp"
        size="sm"
        allowNextStepsSelect={false}
      >
        <Stepper.Step label="О себе" description={compact ? undefined : 'Имя, опыт, формат'}>
          <Stack mt="xl">
            <ProfileForm
              profile={profile.data}
              variant="onboarding"
              submitLabel="Дальше — опрос"
              onSaved={() => goTo(1)}
            />
          </Stack>
        </Stepper.Step>
        <Stepper.Step label="Опрос" description={compact ? undefined : 'Специализация и стек'}>
          <Stack mt="xl">
            <SurveyForm profile={profile.data} survey={survey.data} onSubmitted={() => goTo(2)} />
          </Stack>
        </Stepper.Step>
        <Stepper.Step label="Тест" description={compact ? undefined : 'Уровень и режим'}>
          <Stack mt="xl" gap="lg">
            <Text c="dimmed" maw={720}>
              Тест адаптивный: задания подстраиваются под ваши ответы, поэтому он короче обычного
              экзамена. Провал не сжигает попытку — уровень ниже можно пройти сразу.
            </Text>
            <LaunchStep />
          </Stack>
        </Stepper.Step>
      </Stepper>
      <Text size="sm" c="dimmed" mt="lg">
        Подробности о методике — в разделе <Link to="/c/assessment">«Категория и тест»</Link>.
      </Text>
      {current === 2 && (
        <Button variant="subtle" mt="sm" onClick={() => goTo(1)}>
          Изменить ответы опроса
        </Button>
      )}
    </>
  );
}
