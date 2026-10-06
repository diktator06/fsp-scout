import { Badge } from '@mantine/core';
import {
  INVITATION_STATUS_COLORS,
  INVITATION_STATUS_LABELS,
  type InvitationStatus,
} from '@/shared/lib/invitationStatus';

export function InvitationStatusBadge({ status }: { status: InvitationStatus }) {
  return (
    <Badge color={INVITATION_STATUS_COLORS[status]} variant="light" size="md">
      {INVITATION_STATUS_LABELS[status]}
    </Badge>
  );
}
