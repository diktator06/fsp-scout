import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';
import type { MicroTaskCreate, TasksOverview } from './types';

export const taskKeys = {
  overview: ['candidate', 'tasks'] as const,
  employerList: ['employer', 'tasks'] as const,
  submissions: (taskId: string) => ['employer', 'tasks', taskId, 'submissions'] as const,
};

export function useTasksOverview() {
  return useQuery({
    queryKey: taskKeys.overview,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/tasks')),
  });
}

export function useTaskActions() {
  // Ответ, пропуск и просьба о задаче меняют сводку целиком: перечитываем её.
  const queryClient = useQueryClient();
  const refresh = () => void queryClient.invalidateQueries({ queryKey: taskKeys.overview });
  const request = useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/candidates/me/tasks/request')),
    onSuccess: (overview: TasksOverview) => queryClient.setQueryData(taskKeys.overview, overview),
  });
  const submit = useMutation({
    mutationFn: ({ assignmentId, answer }: { assignmentId: string; answer: string }) =>
      unwrap(
        api.POST('/api/v1/candidates/me/tasks/{assignment_id}/submit', {
          params: { path: { assignment_id: assignmentId } },
          body: { answer },
        }),
      ),
    onSuccess: refresh,
  });
  const skip = useMutation({
    mutationFn: (assignmentId: string) =>
      unwrap(
        api.POST('/api/v1/candidates/me/tasks/{assignment_id}/skip', {
          params: { path: { assignment_id: assignmentId } },
        }),
      ),
    onSuccess: refresh,
  });
  return { request, submit, skip };
}

export function useEmployerTasks() {
  return useQuery({
    queryKey: taskKeys.employerList,
    queryFn: () => unwrap(api.GET('/api/v1/employer/tasks')),
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: MicroTaskCreate) => unwrap(api.POST('/api/v1/employer/tasks', { body })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: taskKeys.employerList }),
  });
}

export function useArchiveTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) =>
      unwrap(
        api.POST('/api/v1/employer/tasks/{task_id}/archive', {
          params: { path: { task_id: taskId } },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: taskKeys.employerList }),
  });
}

export function useTaskSubmissions(taskId: string) {
  return useQuery({
    queryKey: taskKeys.submissions(taskId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/tasks/{task_id}/submissions', {
          params: { path: { task_id: taskId } },
        }),
      ),
    enabled: Boolean(taskId),
  });
}

export function useGradeSubmission(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      assignmentId,
      rating,
      feedback,
    }: {
      assignmentId: string;
      rating: number;
      feedback: string;
    }) =>
      unwrap(
        api.POST('/api/v1/employer/task-submissions/{assignment_id}/grade', {
          params: { path: { assignment_id: assignmentId } },
          body: { rating, feedback },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: taskKeys.submissions(taskId) });
      void queryClient.invalidateQueries({ queryKey: taskKeys.employerList });
    },
  });
}
