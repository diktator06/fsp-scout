import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { queryClient } from '@/api/queryClient';
import { AuthProvider } from '@/features/auth/AuthProvider';
import { cssVariablesResolver, theme } from './theme';

export function AppProviders({ children }: { children: ReactNode }) {
  // Порядок важен: AuthProvider чистит кеш запросов при выходе, поэтому он
  // внутри QueryClientProvider. Светлая схема зафиксирована: дизайн кабинетов
  // и проверка контраста сделаны под неё.
  return (
    <MantineProvider
      theme={theme}
      cssVariablesResolver={cssVariablesResolver}
      forceColorScheme="light"
    >
      <Notifications position="top-right" />
      <QueryClientProvider client={queryClient}>
        <AuthProvider>{children}</AuthProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
