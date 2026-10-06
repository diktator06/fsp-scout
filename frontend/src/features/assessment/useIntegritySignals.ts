import { useEffect } from 'react';
import { reportIntegrityEvent } from '@/api/assessment';

export function useIntegritySignals(sessionId: string, active: boolean): void {
  // Уход со вкладки — сигнал для методиста, а не нарушение: тест не прерывается,
  // кандидата никто не наказывает автоматически. Сигнал отправляется один раз
  // на каждый уход, а не на каждое переключение фокуса внутри страницы.
  useEffect(() => {
    if (!active) return;
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') reportIntegrityEvent(sessionId, 'focus_lost');
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [sessionId, active]);
}
