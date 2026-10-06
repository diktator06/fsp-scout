import type { components } from './schema.gen';

export type Schemas = components['schemas'];

export type CurrentUser = Schemas['UserRead'];
export type UserRole = CurrentUser['role'];
export type TokenResponse = Schemas['TokenResponse'];
export type RegisterRequest = Schemas['RegisterRequest'];
export type RegisterResponse = Schemas['RegisterResponse'];

export type Specialization = Schemas['SpecializationRead'];
export type Grade = Schemas['GradeRead'];
export type Category = Schemas['CategoryRead'];
export type Industry = Schemas['IndustryRead'];
export type Skill = Schemas['SkillRead'];
export type SkillKind = Skill['kind'];
