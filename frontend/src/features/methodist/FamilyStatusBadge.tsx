import { Badge, Tooltip } from '@mantine/core';
import type { ItemFamilyStatus } from '@/api/types';
import { FAMILY_STATUS_COPY } from '@/shared/lib/itemBank';

export function FamilyStatusBadge({ status }: { status: ItemFamilyStatus }) {
  const copy = FAMILY_STATUS_COPY[status];
  return (
    <Tooltip label={copy.hint} withArrow>
      <Badge variant="light" color={copy.color} tt="none" miw="max-content">
        {copy.label}
      </Badge>
    </Tooltip>
  );
}
