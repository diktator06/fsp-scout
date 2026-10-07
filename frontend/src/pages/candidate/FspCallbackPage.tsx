import { notifications } from '@mantine/notifications';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useCompleteFspLink } from '@/api/fsp';
import { FspReturnNotice } from '@/features/fsp/FspReturnNotice';
import { takeIndexBefore } from '@/features/fsp/indexMemo';
import { useFspReturn } from '@/features/fsp/useFspReturn';

export function FspCallbackPage() {
  // Сюда ФСП ID возвращает браузер после входа участника. Бэкенд проверяет state,
  // обменивает код и загружает участия, после чего ведём на страницу ФСП.
  const navigate = useNavigate();
  const { mutateAsync } = useCompleteFspLink();
  const complete = useCallback(
    async (code: string, state: string) => {
      const profile = await mutateAsync({ code, state });
      const before = takeIndexBefore();
      const after = profile.verified_score ? Math.round(profile.verified_score.total) : null;
      const growth =
        before !== null && after !== null ? ` Индекс профиля: ${before} → ${after}.` : '';
      notifications.show({
        color: 'teal',
        title: 'ФСП ID привязан',
        autoClose: 8000,
        message:
          profile.state === 'linked'
            ? `Загружено участий: ${profile.achievements.length}.${growth}`
            : 'В реестре пока нет ваших участий — это штатное состояние, индекс строится по тесту и профилю.',
      });
      navigate('/c/fsp', { replace: true });
    },
    [mutateAsync, navigate],
  );
  const { pending, error } = useFspReturn(complete);
  return (
    <FspReturnNotice
      pending={pending}
      pendingText="Проверяем ответ ФСП ID и загружаем участия…"
      error={error}
      backTo="/c/fsp"
      backLabel="Вернуться к разделу ФСП"
    />
  );
}
