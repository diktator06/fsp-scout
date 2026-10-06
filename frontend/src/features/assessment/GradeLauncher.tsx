import {
  Alert,
  Badge,
  Button,
  Group,
  Radio,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
} from '@mantine/core';
import { IconBolt, IconClockHour4, IconListCheck, IconLock } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useStartSession } from '@/api/assessment';
import { errorMessage } from '@/api/errors';
import type { AssessmentMode, Eligibility } from '@/api/types';
import { formatDate, joinSentences } from '@/shared/lib/format';
import classes from './GradeLauncher.module.css';

interface GradeLauncherProps {
  eligibility: Eligibility;
}

const MODES: Array<{ value: AssessmentMode; label: string; text: string }> = [
  {
    value: 'full',
    label: 'Полный тест',
    text: '12–20 заданий, около 25 минут. Результат — категория в банке кандидатов.',
  },
  {
    value: 'express',
    label: 'Экспресс',
    text: '6–8 заданий, около 10 минут. Для знакомства с платформой, точность ниже.',
  },
];

function defaultGrade(eligibility: Eligibility): number | null {
  // По умолчанию предлагаем заявленный в опросе грейд, если он доступен,
  // иначе — самый высокий из доступных.
  const allowed = eligibility.options.filter((option) => option.allowed);
  const claimed = allowed.find(
    (option) => option.grade.id === eligibility.survey?.claimed_grade.id,
  );
  return (claimed ?? allowed.at(-1))?.grade.id ?? null;
}

export function GradeLauncher({ eligibility }: GradeLauncherProps) {
  // Выбор уровня и режима перед стартом. Недоступные уровни видны вместе с
  // причиной и датой, когда откроются: правила пересдачи не должны быть сюрпризом.
  const navigate = useNavigate();
  const start = useStartSession();
  const [gradeId, setGradeId] = useState<number | null>(() => defaultGrade(eligibility));
  const [mode, setMode] = useState<AssessmentMode>('full');
  const modes = eligibility.express_available ? MODES : MODES.slice(0, 1);
  const currentMode = modes.find((item) => item.value === mode) ?? MODES[0]!;

  const handleStart = async () => {
    if (gradeId === null) return;
    try {
      const session = await start.mutateAsync({ target_grade_id: gradeId, mode });
      navigate(`/c/assessment/sessions/${session.id}`);
    } catch {
      // Ошибку показывает блок под кнопкой из состояния мутации.
    }
  };

  if (eligibility.active_session_id) {
    return (
      <Alert color="fsp" variant="light" icon={<IconClockHour4 size={18} />} title="Тест уже идёт">
        <Stack gap="sm" align="flex-start">
          <Text size="sm">
            Незавершённый тест можно продолжить с того задания, где вы остановились.
          </Text>
          <Button
            onClick={() => navigate(`/c/assessment/sessions/${eligibility.active_session_id}`)}
          >
            Продолжить тест
          </Button>
        </Stack>
      </Alert>
    );
  }

  const nextOpening = eligibility.options
    .map((option) => option.available_at)
    .filter((value): value is string => Boolean(value))
    .sort()[0];
  if (!eligibility.options.some((option) => option.allowed)) {
    // Все уровни закрыты правилами пересдачи: вместо неактивной формы говорим
    // прямо, когда появится следующая попытка.
    return (
      <Alert
        color="lilac"
        variant="light"
        icon={<IconClockHour4 size={18} />}
        title="Сейчас тесты закрыты"
      >
        {joinSentences(
          eligibility.options[0]?.reason,
          nextOpening && `Ближайшая попытка откроется ${formatDate(nextOpening)}`,
        )}
      </Alert>
    );
  }

  return (
    <Stack gap="lg">
      <Radio.Group
        value={gradeId ? String(gradeId) : null}
        onChange={(value) => setGradeId(Number(value))}
        label="Уровень, который подтверждаем"
        labelProps={{ mb: 'xs', fw: 700 }}
      >
        <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="sm">
          {eligibility.options.map((option) => {
            const claimed = option.grade.id === eligibility.survey?.claimed_grade.id;
            const current = option.grade.id === eligibility.current_category?.grade.id;
            return (
              <Radio.Card
                key={option.grade.id}
                value={String(option.grade.id)}
                disabled={!option.allowed}
                className={classes.option}
              >
                <Stack gap={6}>
                  <Group justify="space-between" wrap="nowrap" gap={6}>
                    <Text fw={800}>{option.grade.name}</Text>
                    {option.allowed ? (
                      <Radio.Indicator color="fsp" />
                    ) : (
                      <IconLock size={16} aria-label="Недоступно" />
                    )}
                  </Group>
                  <Group gap={4}>
                    {current && (
                      <Badge size="xs" color="teal" variant="light">
                        ваш грейд
                      </Badge>
                    )}
                    {claimed && !current && (
                      <Badge size="xs" color="lilac" variant="light">
                        заявлен
                      </Badge>
                    )}
                  </Group>
                  {!option.allowed && (
                    <Text size="xs" c="dimmed" lh={1.45}>
                      {joinSentences(
                        option.reason,
                        option.available_at && `Откроется ${formatDate(option.available_at)}`,
                      )}
                    </Text>
                  )}
                </Stack>
              </Radio.Card>
            );
          })}
        </SimpleGrid>
      </Radio.Group>

      {modes.length > 1 && (
        <Stack gap={6}>
          <Text fw={700} size="sm">
            Режим
          </Text>
          <SegmentedControl<AssessmentMode>
            value={mode}
            onChange={setMode}
            data={modes.map((item) => ({ value: item.value, label: item.label }))}
            className={classes.modes}
          />
          <Group gap={8} wrap="nowrap" align="flex-start">
            <ThemeIcon
              size={22}
              radius="xl"
              variant="light"
              color={mode === 'express' ? 'signal' : 'fsp'}
            >
              {mode === 'express' ? <IconBolt size={14} /> : <IconListCheck size={14} />}
            </ThemeIcon>
            <Text size="sm" c="dimmed">
              {currentMode.text}
            </Text>
          </Group>
        </Stack>
      )}

      {start.isError && (
        <Alert color="signal" variant="light">
          {errorMessage(start.error)}
        </Alert>
      )}
      <Group gap="md">
        <Button
          size="md"
          onClick={handleStart}
          loading={start.isPending}
          disabled={gradeId === null}
        >
          Начать тест
        </Button>
        <Text size="xs" c="dimmed" maw={420}>
          На каждое задание отводится своё время. Уход со вкладки фиксируется, но тест не прерывает.
        </Text>
      </Group>
    </Stack>
  );
}
