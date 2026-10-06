import type { UserRole } from '@/api/types';

export const ROLE_HOME: Record<UserRole, string> = {
  candidate: '/c',
  employer: '/e',
  methodist: '/m',
};

export const ROLE_TITLES: Record<UserRole, string> = {
  candidate: 'Кабинет специалиста',
  employer: 'Кабинет работодателя',
  methodist: 'Кабинет методиста',
};

export function safeNextPath(next: string | null, role: UserRole): string {
  // Возврат после входа разрешаем только на внутренние пути своей роли.
  // Ссылка вида ?next=https://evil.example не должна уводить пользователя с сайта.
  const home = ROLE_HOME[role];
  if (!next || !next.startsWith('/') || next.startsWith('//')) return home;
  return next.startsWith(home) ? next : home;
}
