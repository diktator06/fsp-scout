import { Badge } from '@mantine/core';
import type { ApplicationStatus } from '@/api/types';
import {
  APPLICATION_STATUS_COLORS,
  APPLICATION_STATUS_LABELS,
} from '@/shared/lib/applicationStatus';

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <Badge color={APPLICATION_STATUS_COLORS[status]} variant="light" size="md">
      {APPLICATION_STATUS_LABELS[status]}
    </Badge>
  );
}
