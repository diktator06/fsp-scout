import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';
import type { ComplaintCreate, ComplaintStatus, TrustLevel } from './types';

export const moderationKeys = {
  all: ['moderation'] as const,
  complaints: (status: ComplaintStatus | null) => ['moderation', 'complaints', status] as const,
  companies: ['moderation', 'companies'] as const,
};

export function useFileComplaint() {
  return useMutation({
    mutationFn: (body: ComplaintCreate) => unwrap(api.POST('/api/v1/complaints', { body })),
  });
}

export function useModerationComplaints(status: ComplaintStatus | null) {
  return useQuery({
    queryKey: moderationKeys.complaints(status),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/moderation/complaints', {
          params: { query: status ? { status } : {} },
        }),
      ),
  });
}

export function useModerationCompanies() {
  return useQuery({
    queryKey: moderationKeys.companies,
    queryFn: () => unwrap(api.GET('/api/v1/moderation/companies')),
  });
}

export function useResolveComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      complaintId,
      status,
      note,
    }: {
      complaintId: string;
      status: 'confirmed' | 'rejected';
      note: string;
    }) =>
      unwrap(
        api.POST('/api/v1/moderation/complaints/{complaint_id}/resolve', {
          params: { path: { complaint_id: complaintId } },
          body: { status, note },
        }),
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: moderationKeys.all }),
  });
}

export type CompanyAction =
  | { kind: 'restrict'; reason: string }
  | { kind: 'lift' }
  | { kind: 'trust'; trustLevel: TrustLevel };

export function useCompanyModeration(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: CompanyAction) => {
      const path = { company_id: companyId };
      if (action.kind === 'restrict') {
        return unwrap(
          api.POST('/api/v1/moderation/companies/{company_id}/restrict', {
            params: { path },
            body: { reason: action.reason },
          }),
        );
      }
      if (action.kind === 'lift') {
        return unwrap(
          api.POST('/api/v1/moderation/companies/{company_id}/lift', { params: { path } }),
        );
      }
      return unwrap(
        api.PUT('/api/v1/moderation/companies/{company_id}/trust', {
          params: { path },
          body: { trust_level: action.trustLevel },
        }),
      );
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: moderationKeys.all }),
  });
}
