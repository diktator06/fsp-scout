import {
  Alert,
  Button,
  Card,
  Group,
  Modal,
  Radio,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconCheck, IconLockOpen } from '@tabler/icons-react';
import { useState } from 'react';
import { useParams } from 'react-router';
import { errorMessage } from '@/api/errors';
import { useCandidateInvitation, useRespondInvitation } from '@/api/invitations';
import type { CandidateInvitation, DeclineReason } from '@/api/types';
import { invitationTimeline } from '@/features/invitations/timeline';
import { CompanyCard } from '@/features/vacancies/CompanyCard';
import { WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import { formatDate } from '@/shared/lib/format';
import { DECLINE_REASON_LABELS } from '@/shared/lib/matching';
import {
  ErrorState,
  InvitationStatusBadge,
  LoadingState,
  PageHeader,
  SalaryRange,
  StatusTimeline,
} from '@/shared/ui';
import classes from './InvitationPage.module.css';

function DeclineModal({
  opened,
  onClose,
  onConfirm,
  loading,
}: {
  opened: boolean;
  onClose: () => void;
  onConfirm: (reason: DeclineReason, comment: string) => void;
  loading: boolean;
}) {
  const [reason, setReason] = useState<DeclineReason>('salary');
  const [comment, setComment] = useState('');
  return (
    <Modal opened={opened} onClose={onClose} title="Отклонить приглашение" centered>
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          Компания увидит причину — это помогает ей делать предложения точнее. Контакты не
          раскрываются.
        </Text>
        <Radio.Group value={reason} onChange={(value) => setReason(value as DeclineReason)}>
          <Stack gap={8}>
            {(Object.keys(DECLINE_REASON_LABELS) as DeclineReason[]).map((key) => (
              <Radio key={key} value={key} label={DECLINE_REASON_LABELS[key]} />
            ))}
          </Stack>
        </Radio.Group>
        <Textarea
          label="Комментарий"
          placeholder="Необязательно"
          maxLength={500}
          autosize
          minRows={2}
          value={comment}
          onChange={(event) => setComment(event.currentTarget.value)}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button color="signal" loading={loading} onClick={() => onConfirm(reason, comment)}>
            Отклонить
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function InvitationView({ invitation }: { invitation: CandidateInvitation }) {
  // Зарплата — первое, что видит кандидат: ради этого и задумана обратная механика.
  const respond = useRespondInvitation(invitation.id);
  const [declineOpened, decline] = useDisclosure(false);
  const active = invitation.status === 'sent' || invitation.status === 'viewed';
  return (
    <Stack gap="lg">
      <section className={classes.hero}>
        <Stack gap={6} className={classes.heroTitle}>
          <Text className={classes.company}>{invitation.company.name}</Text>
          <Title order={2} c="white">
            {invitation.title}
          </Title>
          <Text c="rgba(255,255,255,0.82)" size="sm">
            {WORK_FORMAT_LABELS[invitation.work_format]}
            {invitation.company.city ? ` · ${invitation.company.city}` : ''}
          </Text>
        </Stack>
        <SalaryRange
          from={invitation.salary_from}
          to={invitation.salary_to}
          tone="dark"
          size="lg"
          caption={invitation.salary_gross ? 'до вычета НДФЛ' : 'на руки'}
        />
      </section>

      <Card>
        <StatusTimeline steps={invitationTimeline(invitation.status, invitation.events)} />
      </Card>

      <SimpleGrid cols={{ base: 1, lg: 3 }} spacing="lg">
        <Card className={classes.offer}>
          <Stack gap="md">
            <Title order={4}>Предложение</Title>
            <Text lh={1.65} className={classes.text}>
              {invitation.offer_description}
            </Text>
            <Text size="sm">
              <b>Как связаться:</b> {invitation.contact_method}
            </Text>
            {invitation.recruiter_name && (
              <Text size="sm" c="dimmed">
                Приглашение отправил(а) {invitation.recruiter_name}
              </Text>
            )}
          </Stack>
        </Card>
        <CompanyCard company={invitation.company} />
      </SimpleGrid>

      {invitation.employer_contacts && (
        <Alert
          color="teal"
          variant="light"
          icon={<IconLockOpen size={18} />}
          title="Контакты открыты обеим сторонам"
        >
          <Stack gap={2}>
            {invitation.employer_contacts.recruiter_name && (
              <Text size="sm">
                {invitation.employer_contacts.recruiter_name}
                {invitation.employer_contacts.recruiter_position
                  ? `, ${invitation.employer_contacts.recruiter_position}`
                  : ''}
              </Text>
            )}
            <Text size="sm">
              {[
                invitation.employer_contacts.telegram,
                invitation.employer_contacts.email,
                invitation.employer_contacts.phone,
              ]
                .filter(Boolean)
                .join(' · ')}
            </Text>
          </Stack>
        </Alert>
      )}
      {invitation.status === 'declined' && invitation.decline_reason && (
        <Alert color="gray" variant="light">
          Вы отклонили приглашение: {DECLINE_REASON_LABELS[invitation.decline_reason]}.
        </Alert>
      )}
      {respond.isError && (
        <Alert color="signal" variant="light">
          {errorMessage(respond.error)}
        </Alert>
      )}
      {active && (
        <Card>
          <Group justify="space-between" wrap="wrap" gap="md">
            <Text size="sm" c="dimmed" maw={560}>
              Если примете приглашение, компания увидит ваше имя и контакты, которые вы разрешили в
              настройках приватности. Ответить можно до {formatDate(invitation.expires_at)}.
            </Text>
            <Group gap="sm">
              <Button variant="default" onClick={decline.open}>
                Отклонить
              </Button>
              <Button
                leftSection={<IconCheck size={16} />}
                loading={respond.isPending}
                onClick={() => respond.mutate({ action: 'accept' })}
              >
                Принять и открыть контакты
              </Button>
            </Group>
          </Group>
        </Card>
      )}
      <DeclineModal
        opened={declineOpened}
        onClose={decline.close}
        loading={respond.isPending}
        onConfirm={(reason, comment) =>
          respond.mutate({ action: 'decline', reason, comment }, { onSuccess: decline.close })
        }
      />
    </Stack>
  );
}

export function CandidateInvitationPage() {
  const { invitationId = '' } = useParams();
  const invitation = useCandidateInvitation(invitationId);
  return (
    <>
      <PageHeader
        kicker="Приглашение"
        title="Предложение от компании"
        actions={invitation.data ? <InvitationStatusBadge status={invitation.data.status} /> : null}
      />
      {invitation.isPending ? (
        <LoadingState blocks={2} />
      ) : invitation.isError ? (
        <ErrorState message={errorMessage(invitation.error)} />
      ) : (
        <InvitationView invitation={invitation.data} />
      )}
    </>
  );
}
