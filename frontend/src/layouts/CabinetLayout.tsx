import {
  Anchor,
  AppShell,
  Avatar,
  Badge,
  Burger,
  Group,
  Menu,
  NavLink,
  ScrollArea,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconBook2,
  IconBriefcase,
  IconBuildingSkyscraper,
  IconChecklist,
  IconChevronDown,
  IconDatabaseExport,
  IconHome,
  IconLogout,
  IconMailOpened,
  IconPlugConnected,
  IconPuzzle,
  IconRadar,
  IconRoute,
  IconSend,
  IconSettings,
  IconShieldCheck,
  IconTargetArrow,
  IconTrophy,
  IconUserCircle,
  IconUsersGroup,
  type Icon,
} from '@tabler/icons-react';
import { Link, Outlet, ScrollRestoration, useLocation, useNavigate } from 'react-router';
import type { UserRole } from '@/api/types';
import { ROLE_HOME, ROLE_TITLES } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';
import { NotificationBell } from '@/features/notifications/NotificationBell';
import { ScoutLogo } from '@/shared/ui';
import classes from './CabinetLayout.module.css';

interface NavItem {
  to: string;
  label: string;
  icon: Icon;
}

const NAVIGATION: Record<UserRole, NavItem[]> = {
  candidate: [
    { to: '/c', label: 'Главная', icon: IconHome },
    { to: '/c/profile', label: 'Профиль', icon: IconUserCircle },
    { to: '/c/assessment', label: 'Категория и тест', icon: IconTargetArrow },
    { to: '/c/fsp', label: 'Достижения ФСП', icon: IconTrophy },
    { to: '/c/tasks', label: 'Микрозадачи', icon: IconPuzzle },
    { to: '/c/invitations', label: 'Приглашения', icon: IconMailOpened },
    { to: '/c/vacancies', label: 'Вакансии', icon: IconBriefcase },
    { to: '/c/applications', label: 'Мои отклики', icon: IconSend },
    { to: '/c/settings', label: 'Приватность', icon: IconShieldCheck },
  ],
  employer: [
    { to: '/e', label: 'Главная', icon: IconHome },
    { to: '/e/needs', label: 'Подборки', icon: IconRadar },
    { to: '/e/bank', label: 'Банк кандидатов', icon: IconUsersGroup },
    { to: '/e/invitations', label: 'Приглашения', icon: IconMailOpened },
    { to: '/e/vacancies', label: 'Вакансии', icon: IconBriefcase },
    { to: '/e/tasks', label: 'Микрозадачи', icon: IconPuzzle },
    { to: '/e/integrations', label: 'Интеграции', icon: IconPlugConnected },
    { to: '/e/company', label: 'Компания', icon: IconBuildingSkyscraper },
  ],
  methodist: [
    { to: '/m', label: 'Справочники', icon: IconBook2 },
    { to: '/m/moderation', label: 'Модерация', icon: IconShieldCheck },
    { to: '/m/item-bank', label: 'Банк заданий', icon: IconChecklist },
    { to: '/m/vacancy-test', label: 'Вакансия → тест', icon: IconRoute },
    { to: '/m/settings', label: 'Настройки оценки', icon: IconSettings },
  ],
};

function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const handleLogout = async () => {
    // Сначала уходим из кабинета, потом закрываем сессию. В обратном порядке
    // защита маршрута успела бы отправить человека на вход с ?next= на кабинет,
    // хотя он сам нажал «Выйти». Переход рисуем синхронно (flushSync): обычно роутер
    // выполняет его как transition, и срочное обновление сессии могло отрисоваться
    // раньше смены адреса.
    await navigate('/', { replace: true, flushSync: true });
    await logout();
  };

  return (
    <Menu position="bottom-end" width={240} shadow="md">
      <Menu.Target>
        <UnstyledButton className={classes.userButton} aria-label="Меню пользователя">
          <Group gap={10} wrap="nowrap">
            <Avatar color="fsp" radius="xl" size={34}>
              {user.email.slice(0, 2).toUpperCase()}
            </Avatar>
            <Text size="sm" fw={600} visibleFrom="sm" className={classes.userEmail}>
              {user.email}
            </Text>
            <IconChevronDown size={16} />
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{ROLE_TITLES[user.role]}</Menu.Label>
        <Menu.Item
          leftSection={<IconDatabaseExport size={16} />}
          component={Link}
          to={`${ROLE_HOME[user.role]}/account`}
        >
          Мои данные
        </Menu.Item>
        <Menu.Item leftSection={<IconLogout size={16} />} color="signal" onClick={handleLogout}>
          Выйти
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

export function CabinetLayout({ role }: { role: UserRole }) {
  const [opened, { toggle, close }] = useDisclosure(false);
  const location = useLocation();

  return (
    <AppShell
      header={{ height: 68 }}
      navbar={{ width: 284, breakpoint: 'md', collapsed: { mobile: !opened } }}
      padding={{ base: 'md', md: 'xl' }}
      className={classes.shell}
    >
      <AppShell.Header className={classes.header}>
        <Group h="100%" px="lg" justify="space-between" wrap="nowrap">
          <Group gap="md" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="md" size="sm" aria-label="Меню" />
            <Anchor component={Link} to={ROLE_HOME[role]} underline="never">
              <ScoutLogo size="sm" />
            </Anchor>
            <Badge variant="light" color="fsp" visibleFrom="xs" size="lg" radius="sm">
              {ROLE_TITLES[role]}
            </Badge>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {role !== 'methodist' && <NotificationBell />}
            <UserMenu />
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md" className={classes.navbar}>
        <AppShell.Section grow component={ScrollArea}>
          <Stack gap={4}>
            {NAVIGATION[role].map((item) => {
              const active =
                item.to === ROLE_HOME[role]
                  ? location.pathname === item.to
                  : location.pathname.startsWith(item.to);
              return (
                <NavLink
                  key={item.to}
                  component={Link}
                  to={item.to}
                  label={item.label}
                  leftSection={<item.icon size={20} stroke={1.7} />}
                  active={active}
                  noWrap
                  onClick={close}
                  className={classes.navLink}
                />
              );
            })}
          </Stack>
        </AppShell.Section>
        <AppShell.Section>
          <Text size="xs" c="dimmed" px="sm" lh={1.5}>
            Подбор ИТ-специалистов с верифицированным профилем ФСП
          </Text>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main className={classes.main}>
        <div className={classes.content}>
          <Outlet />
          <ScrollRestoration />
        </div>
      </AppShell.Main>
    </AppShell>
  );
}
