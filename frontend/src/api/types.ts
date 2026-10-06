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

export type CandidateProfile = Schemas['CandidateProfileRead'];
export type CandidateProfileUpdate = Schemas['CandidateProfileUpdate'];
export type CandidateSkill = Schemas['CandidateSkillRead'];
export type CandidateStatus = Schemas['CandidateStatusRead'];
export type GradeStatus = CandidateStatus['grade_status'];
export type PrivacySettings = Schemas['PrivacySettingsRead'];
export type PrivacySettingsUpdate = Schemas['PrivacySettingsUpdate'];
export type Consents = Schemas['ConsentsRead'];
export type WorkFormat = Schemas['WorkFormat'];
export type SearchStatus = Schemas['SearchStatus'];
export type ContactChannel = Schemas['ContactChannel'];
export type TeamRole = NonNullable<CandidateProfileUpdate['team_roles']>[number];

export type GradeBrief = Schemas['GradeBrief'];
export type Survey = Schemas['SurveyRead'];
export type SurveyCreate = Schemas['SurveyCreate'];
export type Blueprint = Schemas['BlueprintRead'];
export type BlueprintCompetency = Schemas['BlueprintCompetency'];
export type Eligibility = Schemas['EligibilityRead'];
export type GradeOption = Schemas['GradeOptionRead'];
export type AssessmentSession = Schemas['SessionRead'];
export type AssessmentItem = Schemas['ItemView'];
export type ItemTable = Schemas['ItemTable'];
export type SessionResult = Schemas['SessionResult'];
export type SessionSummary = Schemas['SessionSummaryRead'];
export type AssessmentHistory = Schemas['AssessmentHistoryRead'];
export type GradeChange = Schemas['GradeHistoryRead'];
export type AssessmentMode = AssessmentSession['mode'];
export type SessionOutcome = SessionResult['outcome'];
export type SessionStatus = AssessmentSession['status'];
export type IntegrityEvent = Schemas['IntegrityEventCreate']['event'];
