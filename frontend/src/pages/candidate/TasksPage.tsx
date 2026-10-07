import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  Radio,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
  Title,
} from '@mantine/core';
import { IconBolt, IconClockHour4, IconPuzzle } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useTaskActions, useTasksOverview } from '@/api/tasks';
import type { TaskAssignment, TasksOverview } from '@/api/types';
import { formatDate, formatDateTime } from '@/shared/lib/format';
import { ASSIGNMENT_STATUS_COPY, TASK_KIND_LABELS, scoreOutOfFive } from '@/shared/lib/tasks';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';
import classes from './TasksPage.module.css';

function shortDate(value: string): string {
  // «21 авг.» без точки в конце: дата встаёт внутрь предложения.
  return formatDate(value).replace(/\.$/, '');
}

function FreshnessCard({ overview }: { overview: TasksOverview }) {
  // Фактор M — «актуальность профиля»: свежие результаты весят больше, без новых
  // задач он постепенно падает. Это объясняет, зачем решать задачи регулярно.
  const { freshness } = overview;
  return (
    <Card>
      <Stack gap="sm">
        <Group gap="sm">
          <ThemeIcon color="fsp" variant="light" radius="md" size={36}>
            <IconBolt size={20} />
          </ThemeIcon>
          <Title order={4}>Актуальность профиля</Title>
        </Group>
        <Group gap="xl" align="flex-end">
          <div>
            <Text fz={32} fw={800} className="tabular" c="fsp.9">
              {Math.round(freshness.value * 100)}%
            </Text>
            <Text size="xs" c="dimmed">
              фактор M
            </Text>
          </div>
          <div>
            <Text fz={24} fw={800} className="tabular">
              +{freshness.vps_points.toLocaleString('ru-RU')}
            </Text>
            <Text size="xs" c="dimmed">
              к индексу из 20
            </Text>
          </div>
        </Group>
        <Text size="sm" c="dimmed" lh={1.6}>
          {freshness.count
            ? `Оценено задач: ${freshness.count}, последняя — ${shortDate(freshness.last_graded_at ?? '')}. `
            : 'Задач пока не было. '}
          Свежие результаты весят больше: через {freshness.half_life_days} дней вклад задачи
          уменьшается вдвое. Без микрозадач индекс не штрафуется — фактор просто не добавляет
          баллов.
        </Text>
      </Stack>
    </Card>
  );
}

function AnswerInput({
  assignment,
  value,
  onChange,
}: {
  assignment: TaskAssignment;
  value: string;
  onChange: (value: string) => void;
}) {
  // Формат ответа задаёт работодатель: число, вариант или текст подхода.
  const { task } = assignment;
  if (task.answer_format === 'choice') {
    return (
      <Radio.Group label="Ваш ответ" value={value} onChange={onChange}>
        <Stack gap="xs" mt="xs">
          {task.options.map((option, index) => (
            <Radio key={option} value={String(index)} label={option} />
          ))}
        </Stack>
      </Radio.Group>
    );
  }
  if (task.answer_format === 'number') {
    return (
      <NumberInput
        label="Ваш ответ"
        description="Число, можно с десятичной частью"
        decimalSeparator=","
        value={value}
        onChange={(next) => onChange(String(next))}
        hideControls
      />
    );
  }
  return (
    <Textarea
      label="Ваш подход"
      description="Как бы вы решали задачу: шаги, решения и почему именно так"
      autosize
      minRows={5}
      maxLength={5000}
      value={value}
      onChange={(event) => onChange(event.currentTarget.value)}
    />
  );
}

function CurrentTask({ assignment }: { assignment: TaskAssignment }) {
  const { submit, skip } = useTaskActions();
  const [answer, setAnswer] = useState('');
  const { task } = assignment;
  return (
    <Card>
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <Badge color="fsp" variant="light">
              {TASK_KIND_LABELS[task.kind]}
            </Badge>
            <Text size="sm" c="dimmed">
              Задача от компании «{task.company_name}»
            </Text>
          </Group>
          <Group gap={6} c="dimmed">
            <IconClockHour4 size={16} />
            <Text size="sm">
              Ответить до {formatDateTime(assignment.due_at)} · около {task.time_limit_minutes} мин
            </Text>
          </Group>
        </Group>
        <Title order={3}>{task.title}</Title>
        <Text lh={1.65} style={{ whiteSpace: 'pre-line' }}>
          {task.statement}
        </Text>
        {task.kind === 'approach' && task.rubric && (
          <Alert color="lilac" variant="light" title="По чему оценят подход">
            {task.rubric}
          </Alert>
        )}
        <AnswerInput assignment={assignment} value={answer} onChange={setAnswer} />
        {(submit.isError || skip.isError) && (
          <Alert color="signal" variant="light">
            {errorMessage(submit.error ?? skip.error)}
          </Alert>
        )}
        <Group gap="sm">
          <Button
            disabled={!answer.trim()}
            loading={submit.isPending}
            onClick={() => submit.mutate({ assignmentId: assignment.id, answer })}
          >
            Отправить ответ
          </Button>
          <Button
            variant="subtle"
            color="gray"
            loading={skip.isPending}
            onClick={() => skip.mutate(assignment.id)}
          >
            Пропустить
          </Button>
        </Group>
        <Text size="xs" c="dimmed">
          {task.kind === 'solve'
            ? 'Ответ проверяется сразу по эталону компании. Эталон вам не показывается.'
            : 'Подход оценивает компания по шкале 1–5; оценка придёт уведомлением.'}
        </Text>
      </Stack>
    </Card>
  );
}

function HistoryItem({ assignment }: { assignment: TaskAssignment }) {
  const status = ASSIGNMENT_STATUS_COPY[assignment.status];
  const score = scoreOutOfFive(assignment.score);
  return (
    <Card padding="lg">
      <Stack gap={6}>
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Text fw={700}>{assignment.task.title}</Text>
          <Group gap="xs">
            {score && (
              <Badge color="teal" variant="filled">
                {score}
              </Badge>
            )}
            <Badge color={status.color} variant="light">
              {status.label}
            </Badge>
          </Group>
        </Group>
        <Text size="sm" c="dimmed">
          {TASK_KIND_LABELS[assignment.task.kind]} · «{assignment.task.company_name}» · выдана{' '}
          {formatDate(assignment.assigned_at)}
        </Text>
        {assignment.feedback && (
          <Text size="sm">
            <b>Комментарий компании:</b> {assignment.feedback}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

export function TasksPage() {
  const overview = useTasksOverview();
  const { request } = useTaskActions();
  const header = (
    <PageHeader
      kicker="Микрозадачи"
      title="Короткие задачи от компаний"
      description="Раз в неделю система предлагает задачу по вашей специализации: решить её или предложить подход. Свежий результат поднимает индекс профиля и даёт компаниям повод вас пригласить."
    />
  );
  if (overview.isPending) {
    return (
      <>
        {header}
        <LoadingState />
      </>
    );
  }
  if (overview.isError) {
    return (
      <>
        {header}
        <ErrorState
          message={errorMessage(overview.error)}
          onRetry={() => void overview.refetch()}
        />
      </>
    );
  }
  const data = overview.data;
  return (
    <>
      {header}
      {!data.available && (
        <Alert color="lilac" variant="light" mb="lg">
          Задачи подбираются по специализации —{' '}
          <Anchor component={Link} to="/c/onboarding" fw={600}>
            пройдите опрос о стеке
          </Anchor>
          , и первая задача появится здесь.
        </Alert>
      )}
      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="lg" mb="lg">
        <div className={classes.main}>
          {data.current ? (
            <CurrentTask key={data.current.id} assignment={data.current} />
          ) : (
            <Card>
              <Stack gap="sm" align="flex-start">
                <Group gap="sm">
                  <ThemeIcon color="lilac" variant="light" radius="md" size={36}>
                    <IconPuzzle size={20} />
                  </ThemeIcon>
                  <Title order={4}>Сейчас задач нет</Title>
                </Group>
                <Text size="sm" c="dimmed">
                  {data.next_offer_at
                    ? `Следующая задача появится ${shortDate(data.next_offer_at)}.`
                    : 'Новых задач по вашей специализации пока нет.'}{' '}
                  Можно попросить раньше: осталось {data.requests_left} на этой неделе.
                </Text>
                {request.isError && (
                  <Text size="sm" c="signal.8">
                    {errorMessage(request.error)}
                  </Text>
                )}
                <Button
                  disabled={!data.can_request}
                  loading={request.isPending}
                  onClick={() => request.mutate()}
                >
                  Попросить задачу
                </Button>
              </Stack>
            </Card>
          )}
        </div>
        <FreshnessCard overview={data} />
      </SimpleGrid>
      {data.history.length > 0 && (
        <Stack gap="sm">
          <Title order={4}>История</Title>
          {data.history.map((assignment) => (
            <HistoryItem key={assignment.id} assignment={assignment} />
          ))}
        </Stack>
      )}
    </>
  );
}
