import { MantineProvider } from '@mantine/core';
import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { theme } from '@/app/theme';

function Providers({ children }: { children: ReactNode }) {
  return <MantineProvider theme={theme}>{children}</MantineProvider>;
}

export function renderWithTheme(ui: ReactElement, options?: RenderOptions) {
  return render(ui, { wrapper: Providers, ...options });
}
