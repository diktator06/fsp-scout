import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { employerKeys } from './employer';
import { unwrap } from './errors';
import type { DeclineReason, InvitationCreate, InvitationStatusCode } from './types';

export const invitationKeys = {
  employer: (statuses: InvitationStatusCode[]) => ['invitations', 'employer', statuses] as const,
  employerOne: (id: string) => ['invitations', 'employer', 'one', id] as const,
  candidate: ['invitations', 'candidate'] as const,
  candidateOne: (id: string) => ['invitations', 'candidate', id] as const,
};

export function useEmployerInvitations(statuses: InvitationStatusCode[] = []) {
  return useQuery({
    queryKey: invitationKeys.employer(statuses),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/invitations', {
          params: { query: statuses.length ? { status: statuses } : {} },
        }),
      ),
  });
}

export function useEmployerInvitation(invitationId: string) {
  return useQuery({
    queryKey: invitationKeys.employerOne(invitationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/employer/invitations/{invitation_id}', {
          params: { path: { invitation_id: invitationId } },
        }),
      ),
  });
}

export function useSendInvitation() {
  // После отправки меняются метки в подборке, банке и карточке, квота и воронка.
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: InvitationCreate) =>
      unwrap(api.POST('/api/v1/employer/invitations', { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['invitations', 'employer'] });
      void queryClient.invalidateQueries({ queryKey: employerKeys.all });
    },
  });
}

export function useWithdrawInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (invitationId: string) =>
      unwrap(
        api.POST('/api/v1/employer/invitations/{invitation_id}/withdraw', {
          params: { path: { invitation_id: invitationId } },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['invitations', 'employer'] });
      void queryClient.invalidateQueries({ queryKey: employerKeys.all });
    },
  });
}

export function useCandidateInvitations() {
  return useQuery({
    queryKey: invitationKeys.candidate,
    queryFn: () => unwrap(api.GET('/api/v1/candidates/me/invitations')),
  });
}

export function useCandidateInvitation(invitationId: string) {
  // Открытие приглашения на сервере переводит его в «просмотрено», поэтому после
  // загрузки обновляем и список входящих.
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: invitationKeys.candidateOne(invitationId),
    queryFn: async () => {
      const invitation = await unwrap(
        api.GET('/api/v1/candidates/me/invitations/{invitation_id}', {
          params: { path: { invitation_id: invitationId } },
        }),
      );
      void queryClient.invalidateQueries({ queryKey: invitationKeys.candidate, exact: true });
      return invitation;
    },
  });
}

export function useRespondInvitation(invitationId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      response:
        { action: 'accept' } | { action: 'decline'; reason: DeclineReason; comment: string },
    ) =>
      response.action === 'accept'
        ? unwrap(
            api.POST('/api/v1/candidates/me/invitations/{invitation_id}/accept', {
              params: { path: { invitation_id: invitationId } },
            }),
          )
        : unwrap(
            api.POST('/api/v1/candidates/me/invitations/{invitation_id}/decline', {
              params: { path: { invitation_id: invitationId } },
              body: { reason: response.reason, comment: response.comment },
            }),
          ),
    onSuccess: (invitation) => {
      queryClient.setQueryData(invitationKeys.candidateOne(invitation.id), invitation);
      void queryClient.invalidateQueries({ queryKey: invitationKeys.candidate, exact: true });
    },
  });
}
