import { PersonalDataPanel } from '@/features/account/PersonalDataPanel';
import { PageHeader } from '@/shared/ui';

export function AccountPage() {
  return (
    <>
      <PageHeader
        kicker="Аккаунт"
        title="Мои данные"
        description="Права по 152-ФЗ: получить копию всех своих данных и удалить аккаунт вместе с ними."
      />
      <PersonalDataPanel />
    </>
  );
}
