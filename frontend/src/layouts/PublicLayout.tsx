import { Anchor, Box, Burger, Button, Container, Drawer, Group, Stack, Text } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { Link, Outlet, useLocation } from 'react-router';
import { ROLE_HOME } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';
import { env } from '@/shared/config/env';
import { FspLogo, ScoutLogo } from '@/shared/ui';
import classes from './PublicLayout.module.css';

const NAV_LINKS = [
  { href: '/#principles', label: 'Принципы' },
  { href: '/#tracks', label: 'Как это работает' },
  { href: '/#fsp', label: 'Достижения ФСП' },
];

function HeaderActions({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  if (user) {
    return (
      <Button component={Link} to={ROLE_HOME[user.role]} onClick={onNavigate} color="signal">
        Перейти в кабинет
      </Button>
    );
  }
  return (
    <>
      <Button
        component={Link}
        to="/auth/login"
        variant="subtle"
        color="gray.0"
        onClick={onNavigate}
        className={classes.ghostButton}
      >
        Войти
      </Button>
      <Button component={Link} to="/auth/register" color="signal" onClick={onNavigate}>
        Зарегистрироваться
      </Button>
    </>
  );
}

export function PublicLayout() {
  // Шапка прозрачная поверх тёмного hero лендинга. На остальных публичных страницах
  // у неё сплошной фон, чтобы не терялся контраст.
  const location = useLocation();
  const isLanding = location.pathname === '/';
  const [drawerOpened, drawer] = useDisclosure(false);

  return (
    <Box className={classes.shell}>
      <header className={classes.header} data-overlay={isLanding || undefined}>
        <Container size="xl" className={classes.headerInner}>
          <Anchor component={Link} to="/" underline="never" aria-label="Скаут — на главную">
            <ScoutLogo tone="light" />
          </Anchor>
          <Group gap={28} visibleFrom="md" component="nav" aria-label="Разделы">
            {NAV_LINKS.map((link) => (
              <Anchor key={link.href} href={link.href} className={classes.navLink}>
                {link.label}
              </Anchor>
            ))}
          </Group>
          <Group gap="xs" visibleFrom="sm">
            <HeaderActions />
          </Group>
          <Burger
            opened={drawerOpened}
            onClick={drawer.toggle}
            hiddenFrom="sm"
            color="#ffffff"
            aria-label="Открыть меню"
          />
        </Container>
      </header>

      <Drawer opened={drawerOpened} onClose={drawer.close} title={<ScoutLogo />} size="xs">
        <Stack gap="md">
          {NAV_LINKS.map((link) => (
            <Anchor key={link.href} href={link.href} onClick={drawer.close} fw={600} c="dark">
              {link.label}
            </Anchor>
          ))}
          <Stack gap="xs" mt="md">
            <HeaderActions onNavigate={drawer.close} />
          </Stack>
        </Stack>
      </Drawer>

      <main className={classes.main}>
        <Outlet />
      </main>

      <footer className={classes.footer}>
        <Container size="xl">
          <Group justify="space-between" align="flex-start" gap="xl" wrap="wrap">
            <Stack gap="sm" maw={420}>
              <ScoutLogo size="sm" />
              <Text size="sm" c="dimmed" lh={1.6}>
                Платформа подбора ИТ-специалистов с обратной механикой и верифицированным профилем
                участника Федерации спортивного программирования.
              </Text>
            </Stack>
            <Stack gap={6}>
              <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: '0.1em' }}>
                Ресурсы
              </Text>
              <Anchor component={Link} to="/design-system" size="sm">
                Дизайн-система
              </Anchor>
              <Anchor href={env.apiDocsUrl} size="sm" target="_blank" rel="noreferrer">
                Документация API
              </Anchor>
              <Anchor component={Link} to="/legal/personal-data" size="sm">
                Обработка персональных данных
              </Anchor>
            </Stack>
            <Stack gap={8} align="flex-start">
              <Text size="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: '0.1em' }}>
                Постановщик задачи
              </Text>
              <FspLogo height={30} />
            </Stack>
          </Group>
          <Text size="xs" c="dimmed" mt={40}>
            © 2026 Скаут · Лидеры цифровой трансформации, спецтрек ФСП
          </Text>
        </Container>
      </footer>
    </Box>
  );
}
