import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { candidateKeys } from './candidate';
import { api } from './client';
import { unwrap } from './errors';
import type { FspProfile } from './types';

export const fspKeys = {
  profile: ['candidate', 'fsp'] as const,
};

export function useFspProfile() {
  return useQuery({
    queryKey: fspKeys.profile,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/fsp')),
  });
}

function useFspProfileUpdate() {
  const queryClient = useQueryClient();
  return (profile: FspProfile) => {
    // Ответ привязки и синхронизации — уже готовое состояние ФСП. Статус кандидата
    // и согласия тоже изменились, их перечитываем.
    queryClient.setQueryData(fspKeys.profile, profile);
    void queryClient.invalidateQueries({ queryKey: candidateKeys.consents });
    void queryClient.invalidateQueries({ queryKey: candidateKeys.status });
  };
}

export function useStartFspLink() {
  return useMutation({
    mutationFn: (consent: boolean) =>
      unwrap(api.POST('/api/v1/candidates/me/fsp/link', { body: { consent } })),
  });
}

export function useCompleteFspLink() {
  const update = useFspProfileUpdate();
  return useMutation({
    mutationFn: (body: { code: string; state: string }) =>
      unwrap(api.POST('/api/v1/candidates/me/fsp/link/callback', { body })),
    onSuccess: update,
  });
}

export function useSyncFsp() {
  const update = useFspProfileUpdate();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/candidates/me/fsp/sync')),
    onSuccess: update,
  });
}

export function useUnlinkFsp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/v1/candidates/me/fsp')),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: fspKeys.profile });
      void queryClient.invalidateQueries({ queryKey: candidateKeys.consents });
    },
  });
}

export async function startFspLogin(): Promise<string> {
  const authorization = await unwrap(api.POST('/api/v1/auth/fsp/start'));
  return authorization.authorization_url;
}
