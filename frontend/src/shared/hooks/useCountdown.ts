import { useEffect, useState } from 'react';

export function useCountdown(endsAt: number): number {
  // Сколько секунд осталось до момента endsAt по часам клиента. Сам момент
  // вычисляет вызывающий код как «время получения ответа + секунды от сервера»:
  // так расхождение часов клиента и сервера не съедает время кандидата,
  // а свежий ответ сервера сразу поправляет отсчёт.
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  return Math.max(0, Math.ceil((endsAt - now) / 1000));
}
