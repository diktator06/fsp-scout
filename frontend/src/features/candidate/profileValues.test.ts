import { describe, expect, it } from 'vitest';
import type { CandidateProfile } from '@/api/types';
import { profileToValues, validateExperience, valuesToPayload } from './profileValues';

const PROFILE: CandidateProfile = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'ivan@example.com',
  public_alias: 'A7F3',
  full_name: 'Иван Петров',
  phone: null,
  telegram: '@ivan_petrov',
  city: null,
  about: '',
  experience_years: 3,
  team_roles: ['developer'],
  soft_skills: [],
  work_formats: ['remote'],
  relocation_ready: false,
  salary_expectation_from: null,
  salary_expectation_gross: false,
  search_status: 'open',
  category: null,
  grade_assigned_at: null,
  skills: [
    {
      skill: { id: 7, slug: 'python', name: 'Python', kind: 'language', aliases: [] },
      self_level: 4,
      source: 'profile',
      is_verified: false,
      verified_at: null,
    },
  ],
  experiences: [
    {
      id: '00000000-0000-0000-0000-000000000002',
      company_name: 'Кедр',
      position: 'Разработчик',
      started_on: '2022-09-01',
      ended_on: null,
      description: '',
    },
  ],
  educations: [],
  completeness: 60,
  updated_at: '2026-10-06T10:00:00Z',
};

describe('форма профиля', () => {
  it('сохраняет профиль без потерь при отправке без изменений', () => {
    const payload = valuesToPayload(profileToValues(PROFILE));
    expect(payload.city).toBeNull();
    expect(payload.salary_expectation_gross).toBe(false);
    expect(payload.skills).toEqual([{ skill_id: 7, self_level: 4 }]);
    expect(payload.experiences?.[0]).toMatchObject({ started_on: '2022-09-01', ended_on: null });
  });

  it('проверяет период работы так же, как сервер', () => {
    const job = {
      company_name: 'Кедр',
      position: 'Dev',
      started_on: '2024-05',
      ended_on: '',
      description: '',
    };
    expect(validateExperience(job)).toBeNull();
    expect(validateExperience({ ...job, ended_on: '2023-01' })).toBe('Окончание раньше начала');
    expect(validateExperience({ ...job, started_on: '05.2024' })).toMatch('ГГГГ-ММ');
    expect(validateExperience({ ...job, company_name: ' ' })).toMatch('компанию');
  });
});
