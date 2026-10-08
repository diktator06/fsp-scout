import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { dictionaryKeys } from './dictionaries';
import { unwrap } from './errors';
import type { FamilyStatusUpdate } from './types';

export const methodistKeys = {
  all: ['methodist'] as const,
  bank: (specializationId: number | null) => ['methodist', 'bank', specializationId] as const,
  samples: (familyId: number, round: number) => ['methodist', 'samples', familyId, round] as const,
  vacancies: ['methodist', 'vacancies'] as const,
  vacancyTest: (vacancyId: string) => ['methodist', 'vacancy-test', vacancyId] as const,
  settings: ['methodist', 'settings'] as const,
};

export function useItemBank(specializationId: number | null) {
  return useQuery({
    queryKey: methodistKeys.bank(specializationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/methodist/item-bank', {
          params: { query: specializationId ? { specialization_id: specializationId } : {} },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useFamilySamples(familyId: number | null, round: number) {
  // Каждый «раунд» — новые случайные seed на сервере. Ключ с номером раунда не
  // даёт кешу вернуть старые экземпляры при повторной генерации.
  return useQuery({
    queryKey: methodistKeys.samples(familyId ?? 0, round),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/methodist/item-bank/{family_id}/samples', {
          params: { path: { family_id: familyId ?? 0 }, query: { count: 3 } },
        }),
      ),
    enabled: familyId !== null,
    staleTime: Infinity,
    placeholderData: keepPreviousData,
  });
}

export function useFamilyStatus(familyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: FamilyStatusUpdate) =>
      unwrap(
        api.PUT('/api/v1/methodist/item-bank/{family_id}/status', {
          params: { path: { family_id: familyId } },
          body,
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: methodistKeys.all }),
  });
}

export function useMethodistVacancies() {
  return useQuery({
    queryKey: methodistKeys.vacancies,
    queryFn: () => unwrap(api.GET('/api/v1/methodist/vacancies')),
  });
}

export function useVacancyTest(vacancyId: string | null) {
  return useQuery({
    queryKey: methodistKeys.vacancyTest(vacancyId ?? ''),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/methodist/vacancies/{vacancy_id}/test', {
          params: { path: { vacancy_id: vacancyId ?? '' } },
        }),
      ),
    enabled: vacancyId !== null,
  });
}

export function useAssessmentSettings() {
  return useQuery({
    queryKey: methodistKeys.settings,
    queryFn: () => unwrap(api.GET('/api/v1/methodist/assessment-settings')),
  });
}

export function useThetaCut(categoryId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { theta_cut: number; reason: string }) =>
      unwrap(
        api.PUT('/api/v1/methodist/categories/{category_id}/theta-cut', {
          params: { path: { category_id: categoryId } },
          body,
        }),
      ),
    onSuccess: () => {
      // Порог виден и в справочнике категорий, поэтому сбрасываем оба кеша.
      void queryClient.invalidateQueries({ queryKey: methodistKeys.all });
      void queryClient.invalidateQueries({ queryKey: dictionaryKeys.categories });
    },
  });
}
