import { Badge, Button, Card, Group, Modal, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useEmployerTasks } from '@/api/tasks';
import type { MicroTask } from '@/api/types';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { TaskForm } from '@/features/tasks/TaskForm';
import { TASK_KIND_LABELS } from '@/shared/lib/tasks';
import { ErrorState, LoadingState, PageHeader } from '@/shared/ui';

function TaskCard({ task }: { task: MicroTask }) {
  const { stats } = task;
  return (
    <Card component={Link} to={`/e/tasks/${task.id}`}>
      <Stack gap="sm">
        <Stack gap={6} align="flex-start">
          <Badge color={task.kind === 'solve' ? 'fsp' : 'lilac'} variant="light">
            {TASK_KIND_LABELS[task.kind]}
          </Badge>
          <Title order={4}>{task.title}</Title>
        </Stack>
        <Text size="sm" c="dimmed">
          {task.specialization_name}
          {task.status === 'archived' ? ' · в архиве' : ''}
        </Text>
        <Group gap="xs">
          <Badge variant="dot" color="gray">
            Выдана: {stats.assigned}
          </Badge>
          <Badge variant="dot" color="teal">
            Ответов: {stats.answered}
          </Badge>
          {stats.awaiting_review > 0 && (
            <Badge variant="dot" color="signal">
              Ждут оценки: {stats.awaiting_review}
            </Badge>
          )}
          {stats.average_score !== null && (
            <Badge variant="dot" color="lilac">
              Средний балл: {Math.round(stats.average_score * 100)}%
            </Badge>
          )}
        </Group>
      </Stack>
    </Card>
  );
}

export function EmployerTasksPage() {
  const tasks = useEmployerTasks();
  const [opened, modal] = useDisclosure(false);
  return (
    <>
      <PageHeader
        kicker="Микрозадачи"
        title="Короткие задачи для кандидатов"
        description="Система раз в неделю предлагает кандидатам задачу их специализации. Сильное решение — свежий сигнал о человеке и повод пригласить его с вилкой."
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={modal.open}>
            Новая задача
          </Button>
        }
      />
      <CompanyGate>
        {tasks.isPending ? (
          <LoadingState />
        ) : tasks.isError ? (
          <ErrorState message={errorMessage(tasks.error)} onRetry={() => void tasks.refetch()} />
        ) : tasks.data.length === 0 ? (
          <Card>
            <Text c="dimmed">
              Задач пока нет. Хорошая задача решается за 15–30 минут и похожа на реальную работу
              команды.
            </Text>
          </Card>
        ) : (
          <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="lg">
            {tasks.data.map((task) => (
              <TaskCard key={task.id} task={task} />
            ))}
          </SimpleGrid>
        )}
      </CompanyGate>
      <Modal opened={opened} onClose={modal.close} title="Новая микрозадача" size="lg" centered>
        <TaskForm onCreated={modal.close} />
      </Modal>
    </>
  );
}
