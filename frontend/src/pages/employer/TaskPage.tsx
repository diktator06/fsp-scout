import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Rating,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import {
  useArchiveTask,
  useEmployerTasks,
  useGradeSubmission,
  useTaskSubmissions,
} from '@/api/tasks';
import type { MicroTask, TaskSubmission } from '@/api/types';
import { formatDateTime } from '@/shared/lib/format';
import { ASSIGNMENT_STATUS_COPY, TASK_KIND_LABELS, scoreOutOfFive } from '@/shared/lib/tasks';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

function SubmissionCard({ submission, task }: { submission: TaskSubmission; task: MicroTask }) {
  // Автор обезличен, как в банке: сильный ответ — повод открыть карточку и пригласить.
  const grade = useGradeSubmission(task.id);
  const [rating, setRating] = useState(0);
  const [feedback, setFeedback] = useState('');
  const status = ASSIGNMENT_STATUS_COPY[submission.status];
  const reviewable = task.kind === 'approach' && submission.status === 'submitted';
  return (
    <Card>
      <Stack gap="sm">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Group gap="sm">
            <Text fw={800}>Кандидат {submission.candidate.alias}</Text>
            {submission.candidate.category_title && (
              <Text size="sm" c="dimmed">
                {submission.candidate.category_title}
                {submission.candidate.grade_status === 'unconfirmed' ? ' · не подтверждён' : ''}
              </Text>
            )}
          </Group>
          <Group gap="xs">
            {scoreOutOfFive(submission.score) && (
              <Badge color="teal" variant="filled">
                {scoreOutOfFive(submission.score)}
              </Badge>
            )}
            <Badge color={status.color} variant="light">
              {status.label}
            </Badge>
          </Group>
        </Group>
        {submission.submitted_at && (
          <Text size="xs" c="dimmed">
            Ответ {formatDateTime(submission.submitted_at)}
          </Text>
        )}
        <Text size="sm" lh={1.6} style={{ whiteSpace: 'pre-line' }}>
          {task.kind === 'solve' && task.options.length
            ? (task.options[Number(submission.answer)] ?? submission.answer)
            : submission.answer}
        </Text>
        {submission.feedback && (
          <Text size="sm" c="dimmed">
            Ваш комментарий: {submission.feedback}
          </Text>
        )}
        {reviewable && (
          <Stack gap="xs">
            <Group gap="sm">
              <Text size="sm" fw={600}>
                Оценка по рубрике
              </Text>
              <Rating value={rating} onChange={setRating} color="fsp" />
            </Group>
            <Textarea
              placeholder="Комментарий кандидату — что получилось и чего не хватило"
              autosize
              minRows={2}
              maxLength={1000}
              value={feedback}
              onChange={(event) => setFeedback(event.currentTarget.value)}
            />
            {grade.isError && (
              <Text size="sm" c="signal.8">
                {errorMessage(grade.error)}
              </Text>
            )}
            <Group>
              <Button
                size="xs"
                disabled={rating === 0}
                loading={grade.isPending}
                onClick={() => grade.mutate({ assignmentId: submission.id, rating, feedback })}
              >
                Оценить
              </Button>
            </Group>
          </Stack>
        )}
        <Group>
          <Button
            size="xs"
            variant="default"
            component={Link}
            to={`/e/candidates/${submission.candidate.candidate_id}`}
          >
            Карточка и приглашение
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}

export function EmployerTaskPage() {
  const { taskId = '' } = useParams();
  const tasks = useEmployerTasks();
  const submissions = useTaskSubmissions(taskId);
  const archive = useArchiveTask();
  if (tasks.isPending) return <LoadingState />;
  if (tasks.isError) {
    return <ErrorState message={errorMessage(tasks.error)} onRetry={() => void tasks.refetch()} />;
  }
  const task = tasks.data.find((item) => item.id === taskId);
  if (!task) return <ErrorState message="Задача не найдена" />;
  return (
    <>
      <PageHeader
        kicker={TASK_KIND_LABELS[task.kind]}
        title={task.title}
        actions={
          task.status === 'active' ? (
            <Button
              variant="subtle"
              color="gray"
              loading={archive.isPending}
              onClick={() => archive.mutate(task.id)}
            >
              Убрать из выдачи
            </Button>
          ) : (
            <Badge color="gray">В архиве</Badge>
          )
        }
      />
      <Card mb="lg">
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            {task.specialization_name} · около {task.time_limit_minutes} мин
          </Text>
          <Text lh={1.65} style={{ whiteSpace: 'pre-line' }}>
            {task.statement}
          </Text>
          {task.kind === 'solve' ? (
            <Alert color="teal" variant="light" title="Эталон (виден только вам)">
              {task.options.length
                ? `Верный вариант: ${task.options[task.correct_option ?? 0]}`
                : `${task.answer_value}${task.answer_tolerance ? ` ± ${task.answer_tolerance}` : ''}`}
            </Alert>
          ) : (
            <Alert color="lilac" variant="light" title="Рубрика">
              {task.rubric}
            </Alert>
          )}
        </Stack>
      </Card>
      <Title order={4} mb="sm">
        Ответы
      </Title>
      {submissions.isPending ? (
        <LoadingState blocks={2} height={120} />
      ) : submissions.isError ? (
        <ErrorState
          message={errorMessage(submissions.error)}
          onRetry={() => void submissions.refetch()}
        />
      ) : submissions.data.length === 0 ? (
        <Card>
          <Text c="dimmed">
            Ответов пока нет. Система предлагает задачу кандидатам специализации раз в неделю.
          </Text>
        </Card>
      ) : (
        <Stack gap="md">
          {submissions.data.map((submission) => (
            <SubmissionCard key={submission.id} submission={submission} task={task} />
          ))}
        </Stack>
      )}
    </>
  );
}
