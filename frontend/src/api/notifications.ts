import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import { unwrap } from './errors';

const NOTIFICATIONS_KEY = ['notifications'] as const;
const POLL_INTERVAL = 30_000;

export function useNotifications() {
  // Уведомлений немного, поэтому обычный опрос раз в полминуты проще и надёжнее
  // постоянного соединения: работает через любой прокси и не держит ресурсы сервера.
  return useQuery({
    queryKey: NOTIFICATIONS_KEY,
    queryFn: () => unwrap(api.GET('/api/v1/notifications')),
    refetchInterval: POLL_INTERVAL,
    refetchIntervalInBackground: false,
  });
}

export function useReadNotifications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: string | null) =>
      notificationId
        ? unwrap(
            api.POST('/api/v1/notifications/{notification_id}/read', {
              params: { path: { notification_id: notificationId } },
            }),
          )
        : unwrap(api.POST('/api/v1/notifications/read-all')),
    onSuccess: (list) => queryClient.setQueryData(NOTIFICATIONS_KEY, list),
  });
}
