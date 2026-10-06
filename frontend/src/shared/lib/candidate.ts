export const TEAM_ROLE_LABELS = {
  developer: 'Разработчик',
  team_lead: 'Тимлид',
  tech_lead: 'Техлид',
  mentor: 'Ментор',
  architect: 'Архитектор',
  researcher: 'Исследователь',
} as const;

export const WORK_FORMAT_LABELS = {
  office: 'Офис',
  hybrid: 'Гибрид',
  remote: 'Удалённо',
} as const;

export const SEARCH_STATUS_LABELS = {
  active: 'Активно ищу работу',
  open: 'Открыт к предложениям',
  not_looking: 'Не ищу',
} as const;

export const CONTACT_CHANNEL_LABELS = {
  email: 'Email',
  phone: 'Телефон',
  telegram: 'Telegram',
} as const;

export const GRADE_STATUS_COPY = {
  confirmed: { label: 'Подтверждён тестом', color: 'teal' },
  unconfirmed: { label: 'Заявлен, не подтверждён', color: 'lilac' },
  not_declared: { label: 'Не заявлен', color: 'gray' },
} as const;

export function toOptions<K extends string>(labels: Record<K, string>) {
  // Справочник подписей → данные для Select, Chip.Group и SegmentedControl.
  return (Object.keys(labels) as K[]).map((value) => ({ value, label: labels[value] }));
}
