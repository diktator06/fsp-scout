import { describe, expect, it } from 'vitest';
import { searchSkills } from './skills';

const SKILLS = [
  { name: 'Python', slug: 'python', aliases: ['питон', 'py'] },
  { name: 'PostgreSQL', slug: 'postgresql', aliases: ['постгрес', 'postgres'] },
  { name: 'Kubernetes', slug: 'kubernetes', aliases: ['k8s', 'кубер'] },
  { name: 'Pytest', slug: 'pytest', aliases: [] },
  { name: 'Ёмкостное планирование', slug: 'capacity', aliases: [] },
];

describe('поиск навыков', () => {
  it('находит по синонимам на русском и сокращениям', () => {
    expect(searchSkills(SKILLS, 'питон').map((skill) => skill.name)).toEqual(['Python']);
    expect(searchSkills(SKILLS, 'K8S').map((skill) => skill.name)).toEqual(['Kubernetes']);
    expect(searchSkills(SKILLS, ' постгрес ').map((skill) => skill.name)).toEqual(['PostgreSQL']);
  });

  it('ставит совпадения с начала слова выше совпадений в середине', () => {
    expect(searchSkills(SKILLS, 'py').map((skill) => skill.name)).toEqual(['Pytest', 'Python']);
    expect(searchSkills(SKILLS, 'gres').map((skill) => skill.name)).toEqual(['PostgreSQL']);
  });

  it('не различает «е» и «ё» и ограничивает выдачу', () => {
    expect(searchSkills(SKILLS, 'емкост')).toHaveLength(1);
    expect(searchSkills(SKILLS, '', 2).map((skill) => skill.name)).toEqual([
      'Kubernetes',
      'PostgreSQL',
    ]);
  });
});
