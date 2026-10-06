import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { candidateKeys } from './candidate';
import { api } from './client';
import { unwrap } from './errors';
import type { AssessmentMode, AssessmentSession, IntegrityEvent, SurveyCreate } from './types';

export const assessmentKeys = {
  all: ['assessment'] as const,
  survey: ['assessment', 'survey'] as const,
  blueprint: (specializationId: number, skillIds: number[]) =>
    ['assessment', 'blueprint', specializationId, skillIds] as const,
  eligibility: ['assessment', 'eligibility'] as const,
  session: (id: string) => ['assessment', 'session', id] as const,
  history: ['assessment', 'history'] as const,
};

function useInvalidateProgress() {
  // После опроса, теста или принятия грейда меняются статус кандидата, профиль
  // (подтверждённые навыки, категория), допуск к тестам и история.
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: candidateKeys.all }),
      queryClient.invalidateQueries({ queryKey: assessmentKeys.eligibility }),
      queryClient.invalidateQueries({ queryKey: assessmentKeys.history }),
      queryClient.invalidateQueries({ queryKey: assessmentKeys.survey }),
    ]);
}

export function useLatestSurvey() {
  return useQuery({
    queryKey: assessmentKeys.survey,
    queryFn: () => unwrap(api.GET('/api/v1/assessment/surveys/latest')),
  });
}

export function useSubmitSurvey() {
  const invalidate = useInvalidateProgress();
  return useMutation({
    mutationFn: (body: SurveyCreate) => unwrap(api.POST('/api/v1/assessment/surveys', { body })),
    onSuccess: () => invalidate(),
  });
}

export function useBlueprint(specializationId: number | null, skillIds: number[]) {
  // Состав теста пересчитывается на каждое изменение стека. Предыдущий вариант
  // остаётся на экране, пока грузится новый, чтобы превью не мигало.
  const sortedSkills = [...skillIds].sort((a, b) => a - b);
  return useQuery({
    queryKey: assessmentKeys.blueprint(specializationId ?? 0, sortedSkills),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/assessment/blueprint', {
          params: { query: { specialization_id: specializationId ?? 0, skill_ids: sortedSkills } },
        }),
      ),
    enabled: specializationId !== null,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
}

export function useEligibility() {
  return useQuery({
    queryKey: assessmentKeys.eligibility,
    queryFn: () => unwrap(api.GET('/api/v1/assessment/eligibility')),
  });
}

export function useAssessmentHistory() {
  return useQuery({
    queryKey: assessmentKeys.history,
    queryFn: () => unwrap(api.GET('/api/v1/assessment/history')),
  });
}

export function useAssessmentSession(sessionId: string) {
  return useQuery({
    queryKey: assessmentKeys.session(sessionId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/assessment/sessions/{session_id}', {
          params: { path: { session_id: sessionId } },
        }),
      ),
    staleTime: 0,
  });
}

function useStoreSession() {
  // Любой ответ сервера по сессии — её актуальное состояние. Если тест закончился,
  // заодно обновляем всё, что зависит от результата.
  const queryClient = useQueryClient();
  const invalidate = useInvalidateProgress();
  return (session: AssessmentSession) => {
    queryClient.setQueryData(assessmentKeys.session(session.id), session);
    if (session.status !== 'in_progress') void invalidate();
  };
}

export function useStartSession() {
  const store = useStoreSession();
  const invalidate = useInvalidateProgress();
  return useMutation({
    mutationFn: (body: { target_grade_id: number; mode: AssessmentMode }) =>
      unwrap(api.POST('/api/v1/assessment/sessions', { body })),
    onSuccess: (session) => {
      store(session);
      void invalidate();
    },
  });
}

export function useSubmitAnswer(sessionId: string) {
  const store = useStoreSession();
  return useMutation({
    mutationFn: (body: { item_id: string; answer: string }) =>
      unwrap(
        api.POST('/api/v1/assessment/sessions/{session_id}/answers', {
          params: { path: { session_id: sessionId } },
          body,
        }),
      ),
    onSuccess: store,
  });
}

export function useAbandonSession(sessionId: string) {
  const store = useStoreSession();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/assessment/sessions/{session_id}/abandon', {
          params: { path: { session_id: sessionId } },
        }),
      ),
    onSuccess: store,
  });
}

export function useAcceptSuggestedGrade(sessionId: string) {
  const store = useStoreSession();
  const invalidate = useInvalidateProgress();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/assessment/sessions/{session_id}/accept-suggested-grade', {
          params: { path: { session_id: sessionId } },
        }),
      ),
    onSuccess: (session) => {
      store(session);
      void invalidate();
    },
  });
}

export function reportIntegrityEvent(sessionId: string, event: IntegrityEvent): void {
  // Сигнал честности отправляется «в фоне»: его потеря не должна мешать тесту,
  // поэтому ошибки сети сознательно игнорируются.
  void api
    .POST('/api/v1/assessment/sessions/{session_id}/integrity-events', {
      params: { path: { session_id: sessionId } },
      body: { event },
    })
    .catch(() => undefined);
}
