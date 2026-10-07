import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FspAchievement, FspSummary } from '@/api/types';
import { renderWithTheme } from '@/test/render';
import { FspAchievementList } from './FspAchievementList';
import { FspCardBlock } from './FspCardBlock';

const ACHIEVEMENT: FspAchievement = {
  external_event_id: 'EV-1',
  event_name: 'Кубок России по продуктовому программированию',
  event_level: 'national',
  discipline: 'продуктовое программирование',
  event_date: '2025-11-02',
  participation_format: 'team',
  team_name: 'Байт',
  team_role: 'капитан',
  place: 2,
  participants_total: 141,
  result_status: 'prize',
  is_online: false,
  rating_points: 99.3,
  protocol_url: 'https://fsp-registry.example/protocols/EV-1',
};

const EMPTY: FspSummary = {
  state: 'not_linked',
  message: 'Профиль ФСП не привязан — оценка основана на тесте и профиле',
  summary: null,
  best_result: null,
  score: 0,
  sport_rank: null,
  synced_at: null,
  achievements: [],
};

describe('FspCardBlock', () => {
  it('без привязки показывает нейтральную справку, а не пустоту', () => {
    renderWithTheme(<FspCardBlock fsp={EMPTY} />);
    expect(screen.getByText('ФСП ID не привязан')).toBeTruthy();
    expect(screen.getByText(EMPTY.message)).toBeTruthy();
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('привязанный без истории — отдельное штатное состояние', () => {
    renderWithTheme(
      <FspCardBlock
        fsp={{ ...EMPTY, state: 'linked_empty', message: 'Участий пока нет', sport_rank: 'КМС' }}
      />,
    );
    expect(screen.getByText('Привязан, участий пока нет')).toBeTruthy();
    expect(screen.getByText(/Разряд: КМС/)).toBeTruthy();
  });

  it('с участиями показывает сводку, лучший результат и протокол', () => {
    renderWithTheme(
      <FspCardBlock
        fsp={{
          ...EMPTY,
          state: 'linked',
          message: 'Участия подтверждены реестром ФСП',
          summary: '1 соревнование в 2025 году, 1 призовое место',
          best_result: 'призёр (2 место из 141): Кубок России, 2025',
          score: 0.42,
          achievements: [ACHIEVEMENT],
        }}
      />,
    );
    expect(screen.getByText('Подтверждено реестром ФСП')).toBeTruthy();
    expect(screen.getByText('1 соревнование в 2025 году, 1 призовое место')).toBeTruthy();
    expect(screen.getByText(/Балл ФСП 42%/)).toBeTruthy();
    const link = screen.getByRole('link', { name: /Протокол/ });
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });
});

describe('FspAchievementList', () => {
  it('показывает место среди участников и команду', () => {
    renderWithTheme(<FspAchievementList items={[ACHIEVEMENT]} />);
    expect(screen.getByText('2 место из 141')).toBeTruthy();
    expect(screen.getByText('выше 99% участников')).toBeTruthy();
    expect(screen.getByText(/команда «Байт», капитан/)).toBeTruthy();
  });

  it('не делает ссылку из небезопасного адреса протокола', () => {
    renderWithTheme(
      <FspAchievementList items={[{ ...ACHIEVEMENT, protocol_url: 'javascript:alert(1)' }]} />,
    );
    expect(screen.queryByRole('link')).toBeNull();
  });
});
