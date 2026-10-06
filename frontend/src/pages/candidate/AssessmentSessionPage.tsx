import { Button, Card, Stack, Text, Title } from '@mantine/core';
import { Link, useParams } from 'react-router';
import { useAssessmentSession } from '@/api/assessment';
import { ApiError, errorMessage } from '@/api/errors';
import { ResultView } from '@/features/assessment/ResultView';
import { TestRunner } from '@/features/assessment/TestRunner';
import { ErrorState, LoadingState } from '@/shared/ui';

export function AssessmentSessionPage() {
  // Одна страница на весь жизненный цикл попытки: пока сессия идёт — задания,
  // после — результат. Обновление страницы посреди теста ничего не ломает:
  // состояние целиком хранится на сервере.
  const { sessionId = '' } = useParams();
  const session = useAssessmentSession(sessionId);

  if (session.isPending) return <LoadingState blocks={1} height={420} />;
  if (session.isError) {
    if (session.error instanceof ApiError && session.error.status === 404) {
      return (
        <Card>
          <Stack gap="sm" align="flex-start">
            <Title order={3}>Попытка не найдена</Title>
            <Text c="dimmed">Возможно, ссылка устарела или тест проходил другой пользователь.</Text>
            <Button component={Link} to="/c/assessment">
              К разделу «Категория и тест»
            </Button>
          </Stack>
        </Card>
      );
    }
    return (
      <ErrorState message={errorMessage(session.error)} onRetry={() => void session.refetch()} />
    );
  }

  return session.data.status === 'in_progress' ? (
    <TestRunner session={session.data} receivedAt={session.dataUpdatedAt} />
  ) : (
    <ResultView session={session.data} />
  );
}
