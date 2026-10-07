import type { Need, NeedCreate, NeedDraft, Skill, SkillImportance, WorkFormat } from '@/api/types';

export interface NeedSkillValue {
  skill: Skill;
  importance: SkillImportance;
}

export interface NeedFormValues {
  title: string;
  raw_text: string;
  team_description: string;
  specialization_id: string | null;
  grade_ids: string[];
  skills: NeedSkillValue[];
  work_formats: WorkFormat[];
  city: string;
  salary_from: number | null;
  salary_to: number | null;
  salary_gross: boolean;
}

export function draftToValues(draft: NeedDraft): NeedFormValues {
  // Черновик разбора превращается в форму. Пустые поля остаются пустыми: работодатель
  // увидит, чего система не нашла, и заполнит сам.
  return {
    title: draft.title ?? '',
    raw_text: draft.raw_text,
    team_description: '',
    specialization_id: draft.specialization ? String(draft.specialization.id) : null,
    grade_ids: draft.grades.map((grade) => String(grade.id)),
    skills: draft.skills.map((item) => ({ skill: item.skill, importance: item.importance })),
    work_formats: draft.work_formats,
    city: draft.city ?? '',
    salary_from: draft.salary_from,
    salary_to: draft.salary_to,
    salary_gross: draft.salary_gross ?? true,
  };
}

export function needToValues(need: Need): NeedFormValues {
  return {
    title: need.title,
    raw_text: need.raw_text,
    team_description: need.team_description,
    specialization_id: String(need.specialization.id),
    grade_ids: need.grades.map((grade) => String(grade.id)),
    skills: need.skills.map((item) => ({ skill: item.skill, importance: item.importance })),
    work_formats: need.work_formats,
    city: need.city ?? '',
    salary_from: need.salary_from,
    salary_to: need.salary_to,
    salary_gross: need.salary_gross,
  };
}

export function valuesToPayload(values: NeedFormValues): NeedCreate {
  // Форма валидирует поля до отправки, поэтому здесь значения уже заполнены.
  return {
    title: values.title.trim(),
    raw_text: values.raw_text,
    team_description: values.team_description.trim(),
    specialization_id: Number(values.specialization_id),
    grade_ids: values.grade_ids.map(Number),
    skills: values.skills.map((item) => ({ skill_id: item.skill.id, importance: item.importance })),
    work_formats: values.work_formats,
    city: values.city.trim() || null,
    salary_from: values.salary_from ?? 0,
    salary_to: values.salary_to ?? 0,
    salary_gross: values.salary_gross,
  };
}
