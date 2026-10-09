import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';
import type { ApplicationDecision, VacancyCreate, WorkFormat } from './types';

export const vacancyKeys = {
  employerList: ['employer', 'vacancies'] as const,
  employerOne: (id: string) => ['employer', 'vacancies', id] as const,
  applications: (id: string) => ['employer', 'vacancies', id, 'applications'] as const,
  test: (id: string) => ['employer', 'vacancies', id, 'test'] as const,
  board: (query: BoardQuery) => ['vacancies', 'board', query] as const,
  publicOne: (id: string) => ['vacancies', id] as const,
  myApplications: ['candidate', 'applications'] as const,
};

export interface BoardQuery {
  specializationId?: number | null;
  gradeId?: number | null;
  workFormat?: WorkFormat | null;
  salaryMin?: number | null;
  text?: string;
  limit?: number;
  offset?: number;
}

export function useEmployerVacancies() {
  return useQuery({
    queryKey: vacancyKeys.employerList,
    queryFn: () => unwrap(api.GET('/api/v1/employer/vacancies')),
  });
}

export function useEmployerVacancy(vacancyId: string) {
  return useQuery({
    queryKey: vacancyKeys.employerOne(vacancyId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/vacancies/{vacancy_id}', {
          params: { path: { vacancy_id: vacancyId } },
        }),
      ),
    enabled: Boolean(vacancyId),
  });
}

export function useEmployerVacancyTest(vacancyId: string) {
  return useQuery({
    queryKey: vacancyKeys.test(vacancyId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/vacancies/{vacancy_id}/test', {
          params: { path: { vacancy_id: vacancyId } },
        }),
      ),
    enabled: Boolean(vacancyId),
  });
}

export function useCreateVacancy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, publish }: { body: VacancyCreate; publish: boolean }) =>
      unwrap(api.POST('/api/v1/employer/vacancies', { body, params: { query: { publish } } })),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: vacancyKeys.employerList }),
  });
}

export function useSaveVacancy(vacancyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: VacancyCreate) =>
      unwrap(
        api.PUT('/api/v1/employer/vacancies/{vacancy_id}', {
          params: { path: { vacancy_id: vacancyId } },
          body,
        }),
      ),
    onSuccess: (vacancy) => {
      queryClient.setQueryData(vacancyKeys.employerOne(vacancyId), vacancy);
      void queryClient.invalidateQueries({ queryKey: vacancyKeys.employerList });
    },
  });
}

export function useVacancyPublication(vacancyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: 'publish' | 'close') =>
      unwrap(
        action === 'publish'
          ? api.POST('/api/v1/employer/vacancies/{vacancy_id}/publish', {
              params: { path: { vacancy_id: vacancyId } },
            })
          : api.POST('/api/v1/employer/vacancies/{vacancy_id}/close', {
              params: { path: { vacancy_id: vacancyId } },
            }),
      ),
    onSuccess: (vacancy) => {
      queryClient.setQueryData(vacancyKeys.employerOne(vacancyId), vacancy);
      void queryClient.invalidateQueries({ queryKey: vacancyKeys.employerList });
    },
  });
}

export function useVacancyApplications(vacancyId: string) {
  return useQuery({
    queryKey: vacancyKeys.applications(vacancyId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/vacancies/{vacancy_id}/applications', {
          params: { path: { vacancy_id: vacancyId } },
        }),
      ),
    enabled: Boolean(vacancyId),
  });
}

export function useApplicationActions(vacancyId: string) {
  // Открытие отклика отмечает его просмотренным, решение меняет статус. После обоих
  // перечитываем список и воронку вакансии.
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: vacancyKeys.applications(vacancyId) });
    void queryClient.invalidateQueries({ queryKey: vacancyKeys.employerOne(vacancyId) });
    void queryClient.invalidateQueries({ queryKey: vacancyKeys.employerList });
  };
  const open = useMutation({
    mutationFn: (applicationId: string) =>
      unwrap(
        api.GET('/api/v1/employer/applications/{application_id}', {
          params: { path: { application_id: applicationId } },
        }),
      ),
    onSuccess: refresh,
  });
  const decide = useMutation({
    mutationFn: ({ applicationId, body }: { applicationId: string; body: ApplicationDecision }) =>
      unwrap(
        api.POST('/api/v1/employer/applications/{application_id}/decision', {
          params: { path: { application_id: applicationId } },
          body,
        }),
      ),
    onSuccess: refresh,
  });
  return { open, decide };
}

export function useVacancyBoard(query: BoardQuery) {
  return useQuery({
    queryKey: vacancyKeys.board(query),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/vacancies', {
          params: {
            query: {
              specialization_id: query.specializationId ?? undefined,
              grade_id: query.gradeId ?? undefined,
              work_format: query.workFormat ?? undefined,
              salary_min: query.salaryMin ?? undefined,
              text: query.text?.trim() || undefined,
              limit: query.limit ?? 20,
              offset: query.offset ?? 0,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function usePublicVacancy(vacancyId: string) {
  return useQuery({
    queryKey: vacancyKeys.publicOne(vacancyId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/vacancies/{vacancy_id}', {
          params: { path: { vacancy_id: vacancyId } },
        }),
      ),
    enabled: Boolean(vacancyId),
  });
}

export function useApply(vacancyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { cover_letter: string; share_contacts: boolean }) =>
      unwrap(
        api.POST('/api/v1/vacancies/{vacancy_id}/applications', {
          params: { path: { vacancy_id: vacancyId } },
          body,
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: vacancyKeys.publicOne(vacancyId) });
      void queryClient.invalidateQueries({ queryKey: ['vacancies', 'board'] });
      void queryClient.invalidateQueries({ queryKey: vacancyKeys.myApplications });
    },
  });
}

export function useMyApplications() {
  return useQuery({
    queryKey: vacancyKeys.myApplications,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/applications')),
  });
}

export function useWithdrawApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (applicationId: string) =>
      unwrap(
        api.POST('/api/v1/candidates/me/applications/{application_id}/withdraw', {
          params: { path: { application_id: applicationId } },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: vacancyKeys.myApplications });
      void queryClient.invalidateQueries({ queryKey: ['vacancies'] });
    },
  });
}
