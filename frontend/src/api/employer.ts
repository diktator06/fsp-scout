import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';
import type { BankSort, CompanyUpdate, NeedCreate, ShortlistFilters, ShortlistMark } from './types';

export const employerKeys = {
  all: ['employer'] as const,
  profile: ['employer', 'profile'] as const,
  dashboard: ['employer', 'dashboard'] as const,
  needs: ['employer', 'needs'] as const,
  need: (id: string) => ['employer', 'needs', id] as const,
  categories: (id: string) => ['employer', 'needs', id, 'categories'] as const,
  shortlist: (id: string, version: number | null) =>
    ['employer', 'needs', id, 'shortlist', version ?? 'latest'] as const,
  bank: (params: BankQuery) => ['employer', 'bank', params] as const,
  card: (id: string, needId: string | null) => ['employer', 'candidate', id, needId] as const,
};

export interface BankQuery {
  specializationId?: number | null;
  gradeId?: number | null;
  skillIds?: number[];
  verifiedSkillsOnly?: boolean;
  confirmedOnly?: boolean;
  workFormat?: 'office' | 'hybrid' | 'remote' | null;
  city?: string;
  sort?: BankSort;
  limit?: number;
  offset?: number;
}

export function useEmployerProfile() {
  return useQuery({
    queryKey: employerKeys.profile,
    queryFn: () => unwrap(api.GET('/api/v1/employer/company')),
  });
}

export function useSaveCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyUpdate) => unwrap(api.PUT('/api/v1/employer/company', { body })),
    onSuccess: (profile) => {
      queryClient.setQueryData(employerKeys.profile, profile);
      void queryClient.invalidateQueries({ queryKey: employerKeys.dashboard });
    },
  });
}

export function useEmployerDashboard(enabled = true) {
  return useQuery({
    queryKey: employerKeys.dashboard,
    queryFn: () => unwrap(api.GET('/api/v1/employer/dashboard')),
    enabled,
  });
}

export function useNeeds(enabled = true) {
  return useQuery({
    queryKey: employerKeys.needs,
    queryFn: () => unwrap(api.GET('/api/v1/employer/needs')),
    enabled,
  });
}

export function useNeed(needId: string | null) {
  return useQuery({
    queryKey: employerKeys.need(needId ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/needs/{need_id}', {
          params: { path: { need_id: needId ?? '' } },
        }),
      ),
    enabled: Boolean(needId),
  });
}

export function useParseNeed() {
  return useMutation({
    mutationFn: (text: string) =>
      unwrap(api.POST('/api/v1/employer/needs/parse', { body: { text } })),
  });
}

export function useSaveNeed(needId?: string) {
  // Одна мутация на создание и редактирование: после сохранения обновляются список,
  // карточка потребности и всё, что от неё зависит (категории, подборки).
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: NeedCreate) =>
      needId
        ? unwrap(
            api.PUT('/api/v1/employer/needs/{need_id}', {
              params: { path: { need_id: needId } },
              body,
            }),
          )
        : unwrap(api.POST('/api/v1/employer/needs', { body })),
    onSuccess: (need) => {
      queryClient.setQueryData(employerKeys.need(need.id), need);
      void queryClient.invalidateQueries({ queryKey: employerKeys.needs });
      void queryClient.invalidateQueries({ queryKey: employerKeys.categories(need.id) });
      void queryClient.invalidateQueries({ queryKey: employerKeys.dashboard });
    },
  });
}

export function useSetNeedStatus(needId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: 'close' | 'reopen') =>
      unwrap(
        action === 'close'
          ? api.POST('/api/v1/employer/needs/{need_id}/close', {
              params: { path: { need_id: needId } },
            })
          : api.POST('/api/v1/employer/needs/{need_id}/reopen', {
              params: { path: { need_id: needId } },
            }),
      ),
    onSuccess: (need) => {
      queryClient.setQueryData(employerKeys.need(need.id), need);
      void queryClient.invalidateQueries({ queryKey: employerKeys.needs });
      void queryClient.invalidateQueries({ queryKey: employerKeys.dashboard });
    },
  });
}

export function useNeedCategories(needId: string) {
  return useQuery({
    queryKey: employerKeys.categories(needId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/needs/{need_id}/categories', {
          params: { path: { need_id: needId } },
        }),
      ),
  });
}

export function useShortlist(needId: string, version: number | null) {
  return useQuery({
    queryKey: employerKeys.shortlist(needId, version),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/needs/{need_id}/shortlist', {
          params: { path: { need_id: needId }, query: version ? { version } : {} },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useRefineShortlist(needId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (filters: ShortlistFilters) =>
      unwrap(
        api.POST('/api/v1/employer/needs/{need_id}/shortlists', {
          params: { path: { need_id: needId } },
          body: filters,
        }),
      ),
    onSuccess: (shortlist) => {
      queryClient.setQueryData(employerKeys.shortlist(needId, shortlist.version), shortlist);
      queryClient.setQueryData(employerKeys.shortlist(needId, null), shortlist);
      void queryClient.invalidateQueries({ queryKey: employerKeys.need(needId) });
    },
  });
}

export function useSetMark(needId: string) {
  // Отметка влияет на следующие версии подборки; в текущей выдаче её сразу видно
  // после перечитывания версии.
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ candidateId, mark }: { candidateId: string; mark: ShortlistMark | null }) =>
      mark
        ? unwrap(
            api.PUT('/api/v1/employer/needs/{need_id}/marks/{candidate_id}', {
              params: { path: { need_id: needId, candidate_id: candidateId } },
              body: { mark, note: '' },
            }),
          )
        : unwrap(
            api.DELETE('/api/v1/employer/needs/{need_id}/marks/{candidate_id}', {
              params: { path: { need_id: needId, candidate_id: candidateId } },
            }),
          ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['employer', 'needs', needId, 'shortlist'] }),
  });
}

export function useBank(params: BankQuery) {
  return useQuery({
    queryKey: employerKeys.bank(params),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/candidates', {
          params: {
            query: {
              specialization_id: params.specializationId ?? undefined,
              grade_id: params.gradeId ?? undefined,
              skill_ids: params.skillIds?.length ? params.skillIds : undefined,
              verified_skills_only: params.verifiedSkillsOnly || undefined,
              confirmed_only: params.confirmedOnly || undefined,
              work_format: params.workFormat ?? undefined,
              city: params.city?.trim() || undefined,
              sort: params.sort,
              limit: params.limit ?? 20,
              offset: params.offset ?? 0,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useCandidateCard(candidateId: string, needId: string | null) {
  return useQuery({
    queryKey: employerKeys.card(candidateId, needId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/candidates/{candidate_id}', {
          params: {
            path: { candidate_id: candidateId },
            query: needId ? { need_id: needId } : {},
          },
        }),
      ),
  });
}
