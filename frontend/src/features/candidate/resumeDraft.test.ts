import { describe, expect, it } from 'vitest';
import type { ResumeDraft } from '@/api/types';
import { applyResumeDraft, type ProfileFormValues } from './profileValues';

const VALUES: ProfileFormValues = {
  full_name: '',
  city: '',
  phone: '',
  telegram: '',
  about: '',
  experience_years: '',
  work_formats: [],
  team_roles: ['developer'],
  soft_skills: ['Английский язык'],
  relocation_ready: false,
  salary_expectation_from: '',
  salary_expectation_gross: true,
  search_status: 'open',
  skills: [
    {
      skill: { id: 1, slug: 'python', name: 'Python', kind: 'language', aliases: [] },
      self_level: 4,
    },
  ],
  experiences: [],
  educations: [],
};

const DRAFT: ResumeDraft = {
  full_name: 'Мария Иванова',
  email: 'maria@example.com',
  phone: '+79123456789',
  telegram: '@maria_dev',
  city: 'Казань',
  experience_years: 4.5,
  grade: null,
  specialization: null,
  skills: [
    {
      skill: { id: 1, slug: 'python', name: 'Python', kind: 'language', aliases: [] },
      evidence: 'Python',
    },
    {
      skill: { id: 2, slug: 'fastapi', name: 'FastAPI', kind: 'framework', aliases: [] },
      evidence: 'FastAPI',
    },
  ],
  soft_skills: ['Коммуникация'],
  team_roles: ['mentor', 'developer'],
  experiences: [
    {
      position: 'Ведущий разработчик',
      company_name: 'Платёжный шлюз',
      started_on: '2021-03-01',
      ended_on: null,
      description: 'Биллинг',
    },
  ],
  about: 'Пишу бэкенд для платёжных сервисов.',
  educations: [
    { institution: 'Казанский федеральный университет', degree: 'Магистр', graduated_year: 2017 },
  ],
  work_formats: ['remote', 'hybrid'],
  relocation_ready: true,
  evidence: {},
  warnings: [],
};

describe('applyResumeDraft', () => {
  it('переносит отмеченное и дополняет навыки, роли и опыт', () => {
    const next = applyResumeDraft(
      VALUES,
      DRAFT,
      new Set(['name', 'contacts', 'city', 'experience_years', 'skills', 'roles', 'experiences']),
    );
    expect(next.full_name).toBe('Мария Иванова');
    expect(next.telegram).toBe('@maria_dev');
    expect(next.experience_years).toBe(4.5);
    expect(next.skills.map((item) => item.skill.name)).toEqual(['Python', 'FastAPI']);
    expect(next.skills[0]?.self_level).toBe(4);
    expect(next.soft_skills).toEqual(['Английский язык', 'Коммуникация']);
    expect(next.team_roles).toEqual(['developer', 'mentor']);
    expect(next.experiences[0]).toMatchObject({ started_on: '2021-03', ended_on: '' });
  });

  it('переносит «О себе», образование без повторов, форматы и переезд', () => {
    const values: ProfileFormValues = {
      ...VALUES,
      work_formats: ['office'],
      educations: [
        { institution: 'Казанский федеральный университет', degree: '', graduated_year: 2017 },
      ],
    };
    const next = applyResumeDraft(values, DRAFT, new Set(['about', 'educations', 'conditions']));
    expect(next.about).toBe('Пишу бэкенд для платёжных сервисов.');
    expect(next.educations).toHaveLength(1);
    expect(next.work_formats).toEqual(['office', 'remote', 'hybrid']);
    expect(next.relocation_ready).toBe(true);
  });

  it('не трогает неотмеченные группы', () => {
    const next = applyResumeDraft(VALUES, DRAFT, new Set(['skills']));
    expect(next.full_name).toBe('');
    expect(next.city).toBe('');
    expect(next.experiences).toEqual([]);
    expect(next.about).toBe('');
    expect(next.relocation_ready).toBe(false);
  });
});
