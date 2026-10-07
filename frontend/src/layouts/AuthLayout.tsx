import { Anchor, Box, Stack, Text, Title } from '@mantine/core';
import { Link, Outlet, ScrollRestoration } from 'react-router';
import { CategoryBadge, ConstellationBackdrop, FspLogo, Kicker, ScoutLogo } from '@/shared/ui';
import classes from './AuthLayout.module.css';

export function AuthLayout() {
  // Экран входа и регистрации делится на брендовую панель и форму. Панель
  // напоминает, ради чего регистрироваться: категория по результату и работодатели,
  // которые приходят сами. На узком экране она ужимается до полосы с логотипом.
  return (
    <Box className={classes.root}>
      <aside className={classes.brand}>
        <ConstellationBackdrop seed={19} nodes={30} highlight={3} />
        <Stack className={classes.brandContent} justify="space-between" h="100%">
          <Anchor component={Link} to="/" underline="never" aria-label="Скаут — на главную">
            <ScoutLogo tone="light" size="lg" />
          </Anchor>
          <Stack gap="lg" className={classes.pitch}>
            <Kicker variant="ghost">Подбор с обратной механикой</Kicker>
            <Title order={2} c="white" className={classes.pitchTitle}>
              Ваш профиль — это результат, а не самоописание
            </Title>
            <Text c="rgba(255,255,255,0.78)" lh={1.6} maw={440}>
              Пройдите опрос и адаптивный тест, получите категорию — и работодатели сами придут с
              предложением и вилкой зарплаты.
            </Text>
            <CategoryBadge specialization="Backend-разработка" grade="middle" tone="dark" />
          </Stack>
          <FspLogo tone="light" height={26} />
        </Stack>
      </aside>
      <main className={classes.content}>
        <div className={classes.formColumn}>
          <Outlet />
          <ScrollRestoration />
        </div>
      </main>
    </Box>
  );
}
