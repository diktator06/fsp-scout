import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { saveBlob } from '@/shared/lib/download';
import { api } from './client';
import { unwrap } from './errors';
import type { WebhookEndpointCreate, WebhookEndpointUpdate } from './types';

export const integrationKeys = {
  all: ['employer', 'integrations'] as const,
  events: ['employer', 'integrations', 'events'] as const,
  webhooks: ['employer', 'integrations', 'webhooks'] as const,
  deliveries: ['employer', 'integrations', 'deliveries'] as const,
};

const PENDING_POLL_MS = 2500;

export function useWebhookEvents() {
  return useQuery({
    queryKey: integrationKeys.events,
    queryFn: () => unwrap(api.GET('/api/v1/employer/integrations/events')),
    staleTime: Infinity,
  });
}

export function useWebhooks() {
  return useQuery({
    queryKey: integrationKeys.webhooks,
    queryFn: () => unwrap(api.GET('/api/v1/employer/integrations/webhooks')),
  });
}

export function useDeliveries() {
  // Пока в журнале есть доставки в очереди, обновляем его: диспетчер отправляет
  // события в фоне, и результат появляется через пару секунд.
  return useQuery({
    queryKey: integrationKeys.deliveries,
    queryFn: () => unwrap(api.GET('/api/v1/employer/integrations/deliveries')),
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === 'pending') ? PENDING_POLL_MS : false,
  });
}

function useInvalidateIntegrations() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: integrationKeys.all });
}

export function useCreateWebhook() {
  const invalidate = useInvalidateIntegrations();
  return useMutation({
    mutationFn: (body: WebhookEndpointCreate) =>
      unwrap(api.POST('/api/v1/employer/integrations/webhooks', { body })),
    onSuccess: invalidate,
  });
}

export function useConnectSandbox() {
  const invalidate = useInvalidateIntegrations();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/v1/employer/integrations/sandbox')),
    onSuccess: invalidate,
  });
}

export function useWebhookActions(endpointId: string) {
  const invalidate = useInvalidateIntegrations();
  const path = { endpoint_id: endpointId };
  return {
    update: useMutation({
      mutationFn: (body: WebhookEndpointUpdate) =>
        unwrap(
          api.PATCH('/api/v1/employer/integrations/webhooks/{endpoint_id}', {
            params: { path },
            body,
          }),
        ),
      onSuccess: invalidate,
    }),
    rotate: useMutation({
      mutationFn: () =>
        unwrap(
          api.POST('/api/v1/employer/integrations/webhooks/{endpoint_id}/secret', {
            params: { path },
          }),
        ),
      onSuccess: invalidate,
    }),
    test: useMutation({
      mutationFn: () =>
        unwrap(
          api.POST('/api/v1/employer/integrations/webhooks/{endpoint_id}/test', {
            params: { path },
          }),
        ),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: () =>
        unwrap(
          api.DELETE('/api/v1/employer/integrations/webhooks/{endpoint_id}', {
            params: { path },
          }),
        ),
      onSuccess: invalidate,
    }),
  };
}

export function useRetryDelivery() {
  const invalidate = useInvalidateIntegrations();
  return useMutation({
    mutationFn: (deliveryId: string) =>
      unwrap(
        api.POST('/api/v1/employer/integrations/deliveries/{delivery_id}/retry', {
          params: { path: { delivery_id: deliveryId } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export async function downloadCandidatesExport(format: 'csv' | 'json'): Promise<void> {
  const blob = await unwrap(
    api.GET('/api/v1/employer/integrations/export', {
      params: { query: { format } },
      parseAs: 'blob',
    }),
  );
  const stamp = new Date().toISOString().slice(0, 10);
  saveBlob(blob, `scout-candidates-${stamp}.${format}`);
}
