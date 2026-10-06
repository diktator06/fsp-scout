import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';
import type { Skill, SkillKind } from './types';

const DICTIONARY_STALE_TIME = 10 * 60_000;

export const dictionaryKeys = {
  specializations: ['dictionaries', 'specializations'] as const,
  grades: ['dictionaries', 'grades'] as const,
  categories: ['dictionaries', 'categories'] as const,
  industries: ['dictionaries', 'industries'] as const,
  skills: (params: SkillSearchParams) => ['dictionaries', 'skills', params] as const,
  skillCatalog: ['dictionaries', 'skills', 'catalog'] as const,
};

export interface SkillSearchParams {
  query?: string;
  kind?: SkillKind;
  specializationId?: number;
  limit?: number;
  offset?: number;
}

export function useSpecializations() {
  return useQuery({
    queryKey: dictionaryKeys.specializations,
    queryFn: () => unwrap(api.GET('/api/v1/dictionaries/specializations')),
    staleTime: DICTIONARY_STALE_TIME,
  });
}

export function useGrades() {
  return useQuery({
    queryKey: dictionaryKeys.grades,
    queryFn: () => unwrap(api.GET('/api/v1/dictionaries/grades')),
    staleTime: DICTIONARY_STALE_TIME,
  });
}

export function useCategories() {
  return useQuery({
    queryKey: dictionaryKeys.categories,
    queryFn: () => unwrap(api.GET('/api/v1/dictionaries/categories')),
    staleTime: DICTIONARY_STALE_TIME,
  });
}

export function useIndustries() {
  return useQuery({
    queryKey: dictionaryKeys.industries,
    queryFn: () => unwrap(api.GET('/api/v1/dictionaries/industries')),
    staleTime: DICTIONARY_STALE_TIME,
  });
}

export function useSkillSearch(params: SkillSearchParams) {
  // Предыдущая страница остаётся на экране, пока грузится новая: таблица
  // не мигает пустым состоянием на каждый введённый символ.
  return useQuery({
    queryKey: dictionaryKeys.skills(params),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/dictionaries/skills', {
          params: {
            query: {
              query: params.query || undefined,
              kind: params.kind,
              specialization_id: params.specializationId,
              limit: params.limit ?? 20,
              offset: params.offset ?? 0,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
    staleTime: DICTIONARY_STALE_TIME,
  });
}

async function fetchSkillCatalog(): Promise<Skill[]> {
  // Справочник навыков — пара сотен записей: забираем его целиком постранично
  // и дальше ищем на клиенте. Поиск мгновенный, а выбор с клавиатуры
  // не спотыкается о результаты, пришедшие позже введённого текста.
  const pageSize = 100;
  const skills: Skill[] = [];
  for (let offset = 0; ; offset += pageSize) {
    const page = await unwrap(
      api.GET('/api/v1/dictionaries/skills', { params: { query: { limit: pageSize, offset } } }),
    );
    skills.push(...page.items);
    if (page.items.length < pageSize || skills.length >= page.total) return skills;
  }
}

export function useSkillCatalog() {
  return useQuery({
    queryKey: dictionaryKeys.skillCatalog,
    queryFn: fetchSkillCatalog,
    staleTime: DICTIONARY_STALE_TIME,
  });
}
