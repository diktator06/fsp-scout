import {
  ActionIcon,
  Button,
  Group,
  Indicator,
  Popover,
  ScrollArea,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { IconBell } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useNotifications, useReadNotifications } from '@/api/notifications';
import type { NotificationItem } from '@/api/types';
import { formatDateTime } from '@/shared/lib/format';
import classes from './NotificationBell.module.css';

export function NotificationBell() {
  // Колокольчик в шапке кабинета: новые приглашения у кандидата, ответы кандидатов
  // у работодателя. Клик по уведомлению отмечает его прочитанным и ведёт к объекту.
  const [opened, setOpened] = useState(false);
  const navigate = useNavigate();
  const notifications = useNotifications();
  const read = useReadNotifications();
  const unread = notifications.data?.unread ?? 0;
  const items = notifications.data?.items ?? [];

  const open = (item: NotificationItem) => {
    if (!item.read_at) read.mutate(item.id);
    setOpened(false);
    if (item.link) navigate(item.link);
  };

  return (
    <Popover opened={opened} onChange={setOpened} width={340} position="bottom-end" shadow="md">
      <Popover.Target>
        <Indicator
          label={unread > 9 ? '9+' : unread}
          size={18}
          color="signal"
          disabled={unread === 0}
          offset={4}
        >
          <ActionIcon
            variant="subtle"
            color="gray"
            size="lg"
            onClick={() => setOpened((value) => !value)}
            aria-label={unread ? `Уведомления, непрочитанных: ${unread}` : 'Уведомления'}
          >
            <IconBell size={20} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Group justify="space-between" px="md" py="sm" className={classes.head}>
          <Text fw={700} size="sm">
            Уведомления
          </Text>
          {unread > 0 && (
            <Button variant="subtle" size="compact-xs" onClick={() => read.mutate(null)}>
              Прочитать все
            </Button>
          )}
        </Group>
        <ScrollArea.Autosize mah={360}>
          {items.length === 0 ? (
            <Text size="sm" c="dimmed" p="md">
              Пока тихо. Здесь появятся приглашения и ответы на них.
            </Text>
          ) : (
            <Stack gap={0}>
              {items.map((item) => (
                <UnstyledButton
                  key={item.id}
                  className={classes.item}
                  data-unread={!item.read_at || undefined}
                  onClick={() => open(item)}
                >
                  <Text size="sm" fw={600} lh={1.35}>
                    {item.title}
                  </Text>
                  <Text size="xs" c="dimmed" lineClamp={2}>
                    {item.text}
                  </Text>
                  <Text size="xs" c="dimmed" mt={2}>
                    {formatDateTime(item.created_at)}
                  </Text>
                </UnstyledButton>
              ))}
            </Stack>
          )}
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}
