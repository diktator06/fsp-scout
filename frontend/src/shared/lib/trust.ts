import type { ComplaintReason, ComplaintStatus, SalaryCheck } from '@/api/types';

export const COMPLAINT_REASON_LABELS: Record<ComplaintReason, string> = {
  fake_offer: 'Похоже на фиктивное предложение',
  salary_mismatch: 'Условия не совпадают с заявленными',
  payment_request: 'Просят заплатить за обучение или оформление',
  spam: 'Рассылка, не связанная со мной',
  rude: 'Некорректное общение',
  other: 'Другое',
};

export const COMPLAINT_STATUS_COPY: Record<ComplaintStatus, { label: string; color: string }> = {
  open: { label: 'Ждёт решения', color: 'signal' },
  confirmed: { label: 'Подтверждена', color: 'teal' },
  rejected: { label: 'Отклонена', color: 'gray' },
};

export const SALARY_CHECK_COLORS: Record<SalaryCheck['status'], string> = {
  ok: 'teal',
  below_market: 'signal',
  suspicious: 'signal',
  unknown: 'gray',
};
