import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';
import type { CandidateProfileUpdate, PrivacySettingsUpdate, ResumeDraft } from './types';

export const candidateKeys = {
  all: ['candidate'] as const,
  status: ['candidate', 'status'] as const,
  profile: ['candidate', 'profile'] as const,
  privacy: ['candidate', 'privacy'] as const,
  consents: ['candidate', 'consents'] as const,
};

export function useCandidateStatus() {
  return useQuery({
    queryKey: candidateKeys.status,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/status')),
  });
}

export function useCandidateProfile() {
  return useQuery({
    queryKey: candidateKeys.profile,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/profile')),
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CandidateProfileUpdate) =>
      unwrap(api.PUT('/api/v1/candidates/me/profile', { body })),
    onSuccess: (profile) => {
      // Ответ PUT — уже готовый профиль: кладём его в кеш без лишнего запроса.
      // Статус онбординга зависит от анкеты, его перечитываем.
      queryClient.setQueryData(candidateKeys.profile, profile);
      void queryClient.invalidateQueries({ queryKey: candidateKeys.status });
    },
  });
}

export function usePrivacySettings() {
  return useQuery({
    queryKey: candidateKeys.privacy,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/privacy')),
  });
}

export function useUpdatePrivacy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PrivacySettingsUpdate) =>
      unwrap(api.PUT('/api/v1/candidates/me/privacy', { body })),
    onSuccess: (settings) => queryClient.setQueryData(candidateKeys.privacy, settings),
  });
}

export function useConsents() {
  return useQuery({
    queryKey: candidateKeys.consents,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/consents')),
  });
}

export function useBankPublication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (granted: boolean) =>
      unwrap(api.PUT('/api/v1/candidates/me/consents/bank-publication', { body: { granted } })),
    onSuccess: (consents) => {
      queryClient.setQueryData(candidateKeys.consents, consents);
      void queryClient.invalidateQueries({ queryKey: candidateKeys.status });
    },
  });
}

export async function downloadProfilePdf(alias: string): Promise<void> {
  // PDF отдаётся только с токеном доступа, поэтому обычная ссылка не подойдёт:
  // скачиваем файл запросом и сохраняем через временную ссылку на Blob.
  const blob = await unwrap(api.GET('/api/v1/candidates/me/profile.pdf', { parseAs: 'blob' }));
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `scout-profile-${alias}.pdf`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function parseResume(file: File): Promise<ResumeDraft> {
  // Резюме уходит multipart-формой: openapi-fetch передаёт FormData как есть, а
  // заголовок с границей частей ставит браузер.
  const body = new FormData();
  body.append('file', file);
  return unwrap(
    api.POST('/api/v1/candidates/me/resume/parse', {
      body: body as unknown as { file: string },
      bodySerializer: (value) => value as unknown as FormData,
    }),
  );
}
