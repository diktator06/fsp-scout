export const env = {
  mailpitUrl: (import.meta.env.VITE_MAILPIT_URL as string | undefined) ?? '',
  showDemoAccounts: (import.meta.env.VITE_SHOW_DEMO_ACCOUNTS as string | undefined) !== 'false',
  apiDocsUrl: '/api/docs',
} as const;

export const DEMO_PASSWORD = 'ScoutDemo2026';

export const DEMO_ACCOUNTS = [
  { role: 'candidate', label: 'Специалист', email: 'candidate@example.com' },
  { role: 'employer', label: 'Работодатель', email: 'employer@example.com' },
  { role: 'methodist', label: 'Методист', email: 'methodist@example.com' },
] as const;
