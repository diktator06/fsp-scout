import { notifications } from '@mantine/notifications';
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useCompleteFspLink } from '@/api/fsp';
import { FspReturnNotice } from '@/features/fsp/FspReturnNotice';
import { useFspReturn } from '@/features/fsp/useFspReturn';

export function FspCallbackPage() {
  // Сюда ФСП ID возвращает браузер после входа участника. Бэкенд проверяет state,
  // обменивает код и загружает участия, после чего ведём на страницу ФСП.
  const navigate = useNavigate();
  const { mutateAsync } = useCompleteFspLink();
  const complete = useCallback(
    async (code: string, state: string) => {
      const profile = await mutateAsync({ code, state });
      notifications.show({
        color: 'teal',
        title: 'ФСП ID привязан',
        message:
          profile.state === 'linked'
            ? `Загружено участий: ${profile.achievements.length}`
            : 'В реестре пока нет ваших участий — это штатное состояние',
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
