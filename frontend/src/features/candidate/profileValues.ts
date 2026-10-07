import type {
  CandidateProfile,
  CandidateProfileUpdate,
  ResumeDraft,
  SearchStatus,
  Skill,
  TeamRole,
  WorkFormat,
} from '@/api/types';

export interface SkillEntry {
  skill: Skill;
  self_level: number | null;
}

export interface ExperienceEntry {
  company_name: string;
  position: string;
  started_on: string;
  ended_on: string;
  description: string;
}

export interface EducationEntry {
  institution: string;
  degree: string;
  graduated_year: number | '';
}

export interface ProfileFormValues {
  full_name: string;
  city: string;
  phone: string;
  telegram: string;
  about: string;
  experience_years: number | '';
  work_formats: WorkFormat[];
  team_roles: TeamRole[];
  soft_skills: string[];
  relocation_ready: boolean;
  salary_expectation_from: number | '';
  salary_expectation_gross: boolean;
  search_status: SearchStatus;
  skills: SkillEntry[];
  experiences: ExperienceEntry[];
  educations: EducationEntry[];
}

const MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

function toMonth(value: string | null): string {
  // Дата с сервера «2023-02-01» → значение поля месяца «2023-02».
  return value ? value.slice(0, 7) : '';
}

export function isMonth(value: string): boolean {
  return MONTH_PATTERN.test(value);
}

export function profileToValues(profile: CandidateProfile): ProfileFormValues {
  return {
    full_name: profile.full_name ?? '',
    city: profile.city ?? '',
    phone: profile.phone ?? '',
    telegram: profile.telegram ?? '',
    about: profile.about,
    experience_years: profile.experience_years ?? '',
    work_formats: profile.work_formats as WorkFormat[],
    team_roles: profile.team_roles as TeamRole[],
    soft_skills: profile.soft_skills,
    relocation_ready: profile.relocation_ready,
    salary_expectation_from: profile.salary_expectation_from ?? '',
    salary_expectation_gross: profile.salary_expectation_gross,
    search_status: profile.search_status,
    skills: profile.skills.map((item) => ({ skill: item.skill, self_level: item.self_level })),
    experiences: profile.experiences.map((job) => ({
      company_name: job.company_name,
      position: job.position,
      started_on: toMonth(job.started_on),
      ended_on: toMonth(job.ended_on),
      description: job.description,
    })),
    educations: profile.educations.map((item) => ({
      institution: item.institution,
      degree: item.degree,
      graduated_year: item.graduated_year ?? '',
    })),
  };
}

export function valuesToPayload(values: ProfileFormValues): CandidateProfileUpdate {
  // PUT заменяет анкету целиком, поэтому отправляем все поля, включая списки,
  // которых нет на экране онбординга: они берутся из текущего профиля без изменений.
  // Пустые строки превращаются в null, месяцы — в даты первого числа.
  const optional = (value: string) => value.trim() || null;
  return {
    full_name: optional(values.full_name),
    city: optional(values.city),
    phone: optional(values.phone),
    telegram: optional(values.telegram),
    about: values.about.trim(),
    experience_years: values.experience_years === '' ? null : values.experience_years,
    work_formats: values.work_formats,
    team_roles: values.team_roles,
    soft_skills: values.soft_skills,
    relocation_ready: values.relocation_ready,
    salary_expectation_from:
      values.salary_expectation_from === '' ? null : values.salary_expectation_from,
    salary_expectation_gross: values.salary_expectation_gross,
    search_status: values.search_status,
    skills: values.skills.map((item) => ({ skill_id: item.skill.id, self_level: item.self_level })),
    experiences: values.experiences.map((job) => ({
      company_name: job.company_name.trim(),
      position: job.position.trim(),
      started_on: `${job.started_on}-01`,
      ended_on: job.ended_on ? `${job.ended_on}-01` : null,
      description: job.description.trim(),
    })),
    educations: values.educations.map((item) => ({
      institution: item.institution.trim(),
      degree: item.degree.trim(),
      graduated_year: item.graduated_year === '' ? null : item.graduated_year,
    })),
  };
}

export function validateExperience(job: ExperienceEntry): string | null {
  // Та же проверка периода, что и на сервере, но до отправки формы.
  if (!job.company_name.trim() || !job.position.trim()) return 'Укажите компанию и должность';
  if (!isMonth(job.started_on)) return 'Месяц начала в формате ГГГГ-ММ';
  if (job.ended_on && !isMonth(job.ended_on)) return 'Месяц окончания в формате ГГГГ-ММ';
  if (job.ended_on && job.ended_on < job.started_on) return 'Окончание раньше начала';
  return null;
}

export type ResumeSection =
  'name' | 'contacts' | 'city' | 'experience_years' | 'skills' | 'roles' | 'experiences';

export function applyResumeDraft(
  values: ProfileFormValues,
  draft: ResumeDraft,
  sections: ReadonlySet<ResumeSection>,
): ProfileFormValues {
  // Переносит в анкету только отмеченные группы полей. Навыки, софт-скиллы и роли
  // дополняют уже заполненное, а не заменяют его: кандидат мог указать больше, чем
  // нашлось в резюме. Места работы добавляются в конец списка.
  const next = { ...values };
  if (sections.has('name') && draft.full_name) next.full_name = draft.full_name;
  if (sections.has('contacts')) {
    if (draft.phone) next.phone = draft.phone;
    if (draft.telegram) next.telegram = draft.telegram;
  }
  if (sections.has('city') && draft.city) next.city = draft.city;
  if (sections.has('experience_years') && draft.experience_years !== null) {
    next.experience_years = draft.experience_years;
  }
  if (sections.has('skills')) {
    const known = new Set(values.skills.map((item) => item.skill.id));
    next.skills = [
      ...values.skills,
      ...draft.skills
        .filter((item) => !known.has(item.skill.id))
        .map((item) => ({ skill: item.skill, self_level: null })),
    ];
    next.soft_skills = Array.from(new Set([...values.soft_skills, ...draft.soft_skills]));
  }
  if (sections.has('roles')) {
    next.team_roles = Array.from(new Set([...values.team_roles, ...draft.team_roles]));
  }
  if (sections.has('experiences')) {
    next.experiences = [
      ...values.experiences,
      ...draft.experiences.map((item) => ({
        company_name: item.company_name,
        position: item.position,
        started_on: toMonth(item.started_on ?? null),
        ended_on: toMonth(item.ended_on ?? null),
        description: item.description,
      })),
    ];
  }
  return next;
}
