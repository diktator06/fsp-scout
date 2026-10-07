import { Alert, Button, Modal, Radio, Stack, Text, Textarea } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconFlag } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '@/api/errors';
import { useFileComplaint } from '@/api/trust';
import type { ComplaintReason, ComplaintTarget } from '@/api/types';
import { COMPLAINT_REASON_LABELS } from '@/shared/lib/trust';

interface ComplaintButtonProps {
  targetType: ComplaintTarget;
  targetId: string;
}

export function ComplaintButton({ targetType, targetId }: ComplaintButtonProps) {
  // Жалоба уходит модератору. Три жалобы разных кандидатов ставят компанию на
  // проверку автоматически: до решения она не может приглашать и публиковать.
  const [opened, { open, close }] = useDisclosure(false);
  const [reason, setReason] = useState<ComplaintReason | null>(null);
  const [comment, setComment] = useState('');
  const complaint = useFileComplaint();

  const handleClose = () => {
    close();
    if (complaint.isError) complaint.reset();
  };

  return (
    <>
      <Button
        variant="subtle"
        color="gray"
        size="xs"
        leftSection={<IconFlag size={14} />}
        onClick={open}
        disabled={complaint.isSuccess}
        style={{ alignSelf: 'flex-start' }}
      >
        {complaint.isSuccess ? 'Жалоба отправлена' : 'Пожаловаться'}
      </Button>
      <Modal opened={opened} onClose={handleClose} title="Пожаловаться на работодателя" size="lg">
        {complaint.isSuccess ? (
          <Stack gap="md">
            <Alert color="teal" variant="light">
              Спасибо: жалобу проверит модератор. Работодатель не узнает, кто именно пожаловался.
            </Alert>
            <Button onClick={handleClose} style={{ alignSelf: 'flex-start' }}>
              Закрыть
            </Button>
          </Stack>
        ) : (
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              Если компания на платформе ведёт себя недобросовестно, расскажите. Подтверждённые
              жалобы видны в её репутации, а после нескольких жалоб компания уходит на проверку.
            </Text>
            <Radio.Group
              label="Что случилось"
              value={reason}
              onChange={(value) => setReason(value as ComplaintReason)}
            >
              <Stack gap="xs" mt="xs">
                {Object.entries(COMPLAINT_REASON_LABELS).map(([value, label]) => (
                  <Radio key={value} value={value} label={label} />
                ))}
              </Stack>
            </Radio.Group>
            <Textarea
              label="Подробности"
              description="Необязательно, но помогает модератору"
              autosize
              minRows={3}
              maxLength={1000}
              value={comment}
              onChange={(event) => setComment(event.currentTarget.value)}
            />
            {complaint.isError && (
              <Alert color="signal" variant="light">
                {errorMessage(complaint.error)}
              </Alert>
            )}
            <Button
              color="signal"
              disabled={!reason}
              loading={complaint.isPending}
              onClick={() =>
                reason &&
                complaint.mutate({
                  target_type: targetType,
                  target_id: targetId,
                  reason,
                  comment: comment.trim(),
                })
              }
              style={{ alignSelf: 'flex-start' }}
            >
              Отправить жалобу
            </Button>
          </Stack>
        )}
      </Modal>
    </>
  );
}
