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

export type Company = Schemas['CompanyRead'];
export type CompanyUpdate = Schemas['CompanyUpdate'];
export type EmployerProfile = Schemas['EmployerProfileRead'];
export type EmployerDashboard = Schemas['EmployerDashboardRead'];
export type InvitationQuota = Schemas['InvitationQuotaRead'];
export type CompanySize = NonNullable<Company['size']>;

export type NeedDraft = Schemas['NeedDraft'];
export type NeedCreate = Schemas['NeedCreate'];
export type Need = Schemas['NeedRead'];
export type SkillImportance = Schemas['NeedSkillRead']['importance'];
export type CategorySlice = Schemas['CategorySliceRead'];
export type ShortlistFilters = Schemas['ShortlistFilters'];
export type Shortlist = Schemas['ShortlistRead'];
export type ShortlistEntry = Schemas['ShortlistEntryRead'];
export type ShortlistMark = NonNullable<ShortlistEntry['mark']>;
export type Match = Schemas['MatchRead'];
export type ScoreComponent = Schemas['ScoreComponentRead'];
export type ExplanationItem = Schemas['ExplanationItemRead'];
export type SkillMatch = Schemas['SkillMatchRead'];
export type CandidateCard = Schemas['CandidateAnonymousCard'];
export type CandidateCardView = Schemas['CandidateCardRead'];
export type DisclosedContacts = Schemas['DisclosedContacts'];
export type BankPage = Schemas['BankPage'];
export type BankCandidate = Schemas['BankCandidateRead'];
export type BankSort = Schemas['BankSort'];
export type InvitationBrief = Schemas['InvitationBrief'];

export type InvitationCreate = Schemas['InvitationCreate'];
export type EmployerInvitation = Schemas['EmployerInvitationRead'];
export type CandidateInvitation = Schemas['CandidateInvitationRead'];
export type InvitationEvent = Schemas['InvitationEventRead'];
export type DeclineReason = Schemas['DeclineRequest']['reason'];
export type InvitationStatusCode = EmployerInvitation['status'];

export type NotificationItem = Schemas['NotificationRead'];
export type NotificationList = Schemas['NotificationListRead'];

export type FspProfile = Schemas['FspProfileRead'];
export type FspState = FspProfile['state'];
export type FspScore = Schemas['FspScoreRead'];
export type FspSummary = Schemas['FspSummary'];
export type FspAchievement = Schemas['FspAchievementRead'];
export type FspAuthorization = Schemas['FspAuthorizationRead'];
export type FspResultStatus = FspAchievement['result_status'];
export type FspEventLevel = FspAchievement['event_level'];

export type Vacancy = Schemas['VacancyRead'];
export type VacancyCreate = Schemas['VacancyCreate'];
export type VacancyPublic = Schemas['VacancyPublicRead'];
export type VacancyBoardPage = Schemas['VacancyBoardPage'];
export type VacancyStatus = Vacancy['status'];
export type ApplicationStatus = Schemas['ApplicationStatus'];
export type RejectReason = Schemas['RejectReason'];
export type CandidateApplication = Schemas['CandidateApplicationRead'];
export type EmployerApplication = Schemas['EmployerApplicationRead'];
export type ApplicationDecision = Schemas['ApplicationDecision'];

export type TasksOverview = Schemas['TasksOverviewRead'];
export type TaskAssignment = Schemas['AssignmentRead'];
export type AssignmentStatus = TaskAssignment['status'];
export type MicroTask = Schemas['MicroTaskRead'];
export type MicroTaskCreate = Schemas['MicroTaskCreate'];
export type MicroTaskKind = MicroTask['kind'];
export type TaskSubmission = Schemas['SubmissionRead'];

export type ResumeDraft = Schemas['ResumeDraftRead'];

export type ComplaintCreate = Schemas['ComplaintCreate'];
export type ComplaintTarget = ComplaintCreate['target_type'];
export type ComplaintReason = ComplaintCreate['reason'];
export type Complaint = Schemas['ComplaintRead'];
export type ComplaintStatus = Complaint['status'];
export type CompanyReputation = Schemas['CompanyReputationRead'];
export type SalaryCheck = Schemas['SalaryCheckRead'];
export type ModerationComplaint = Schemas['ModerationComplaintRead'];
export type ModerationCompany = Schemas['ModerationCompanyRead'];
export type TrustLevel = ModerationCompany['trust_level'];
