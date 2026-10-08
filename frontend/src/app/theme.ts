import {
  Badge,
  Button,
  Card,
  Checkbox,
  createTheme,
  type CSSVariablesResolver,
  type MantineColorsTuple,
  Paper,
  PasswordInput,
  rem,
  SegmentedControl,
  TextInput,
  NumberInput,
  Tooltip,
} from '@mantine/core';

const fsp: MantineColorsTuple = [
  '#f7f0fb',
  '#eddcf6',
  '#d9b9ec',
  '#c493e1',
  '#ae6cd5',
  '#9147c3',
  '#7120a3',
  '#520978',
  '#420762',
  '#310f53',
];

const signal: MantineColorsTuple = [
  '#fff0f5',
  '#ffd6e4',
  '#ffadc8',
  '#ff85ac',
  '#ff5c90',
  '#fc3777',
  '#ff0053',
  '#d90047',
  '#b3003b',
  '#8c002e',
];

const lilac: MantineColorsTuple = [
  '#f4f3fb',
  '#e7e5f6',
  '#cfcbee',
  '#b7b2e5',
  '#a09adb',
  '#8a83d1',
  '#716ac0',
  '#5a53a6',
  '#463f87',
  '#332e66',
];

const neutral: MantineColorsTuple = [
  '#f8f7fb',
  '#f1eff6',
  '#e6e3ee',
  '#d6d2e1',
  '#b9b4c8',
  '#8f8aa1',
  '#6b6780',
  '#4f4b60',
  '#353343',
  '#1c1d22',
];

const FONT_STACK = 'Montserrat, "Segoe UI", system-ui, -apple-system, sans-serif';

const BADGE_SIZES: Record<string, { fz: string; height: string }> = {
  xs: { fz: rem(10), height: rem(18) },
  sm: { fz: rem(11), height: rem(20) },
  md: { fz: rem(12), height: rem(23) },
  lg: { fz: rem(14), height: rem(28) },
  xl: { fz: rem(16), height: rem(32) },
};

const BUTTON_HEIGHTS: Record<string, string> = {
  xs: rem(32),
  sm: rem(38),
};

export const theme = createTheme({
  primaryColor: 'fsp',
  primaryShade: { light: 7, dark: 4 },
  colors: { fsp, signal, lilac, gray: neutral },
  black: '#1c1d22',
  white: '#ffffff',
  fontFamily: FONT_STACK,
  fontFamilyMonospace: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
  fontSizes: { xs: rem(13), sm: rem(15), md: rem(16), lg: rem(18), xl: rem(21) },
  lineHeights: { xs: '1.45', sm: '1.5', md: '1.6', lg: '1.6', xl: '1.55' },
  headings: {
    fontFamily: FONT_STACK,
    fontWeight: '800',
    sizes: {
      h1: { fontSize: 'clamp(2rem, 1.4rem + 2.2vw, 3.25rem)', lineHeight: '1.08' },
      h2: { fontSize: 'clamp(1.625rem, 1.2rem + 1.4vw, 2.25rem)', lineHeight: '1.15' },
      h3: { fontSize: '1.4375rem', lineHeight: '1.25', fontWeight: '700' },
      h4: { fontSize: '1.1875rem', lineHeight: '1.3', fontWeight: '700' },
      h5: { fontSize: '1.0625rem', lineHeight: '1.35', fontWeight: '700' },
      h6: { fontSize: '1rem', lineHeight: '1.4', fontWeight: '700' },
    },
  },
  radius: { xs: '6px', sm: '10px', md: '14px', lg: '20px', xl: '28px' },
  defaultRadius: 'md',
  shadows: {
    xs: '0 1px 2px rgba(49, 15, 83, 0.06)',
    sm: '0 2px 8px rgba(49, 15, 83, 0.07)',
    md: '0 10px 30px -12px rgba(49, 15, 83, 0.22)',
    lg: '0 24px 60px -20px rgba(49, 15, 83, 0.35)',
    xl: '0 40px 90px -30px rgba(49, 15, 83, 0.45)',
  },
  cursorType: 'pointer',
  focusRing: 'auto',
  respectReducedMotion: true,
  components: {
    Button: Button.extend({
      defaultProps: { radius: 'md' },
      vars: (_theme, props) => {
        // Кнопки xs и sm на пару пикселей выше стандартных: при крупном кегле
        // стандартная высота делает подпись тесной.
        const height = BUTTON_HEIGHTS[String(props.size ?? 'sm')];
        return { root: height ? { '--button-height': height } : {} };
      },
    }),
    Card: Card.extend({ defaultProps: { radius: 'lg', withBorder: true, padding: 'xl' } }),
    Paper: Paper.extend({ defaultProps: { radius: 'lg' } }),
    TextInput: TextInput.extend({ defaultProps: { size: 'md' } }),
    PasswordInput: PasswordInput.extend({ defaultProps: { size: 'md' } }),
    NumberInput: NumberInput.extend({ defaultProps: { size: 'md' } }),
    SegmentedControl: SegmentedControl.extend({ defaultProps: { radius: 'md' } }),
    Checkbox: Checkbox.extend({ defaultProps: { radius: 'xs' } }),
    Badge: Badge.extend({
      defaultProps: { radius: 'xl' },
      vars: (_theme, props) => {
        // Стандартные бейджи Mantine набраны 9–11 px: навыки и статусы в карточках
        // читаются с трудом, поэтому каждая ступень крупнее на 1–2 px.
        const size = BADGE_SIZES[String(props.size ?? 'md')];
        return { root: size ? { '--badge-fz': size.fz, '--badge-height': size.height } : {} };
      },
    }),
    Tooltip: Tooltip.extend({ defaultProps: { withArrow: true, color: 'fsp.9' } }),
  },
});

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--scout-hero-gradient': 'linear-gradient(140deg, #1c1d22 0%, #310f53 45%, #520978 100%)',
    '--scout-signal': '#ff0053',
    '--scout-ink': '#1c1d22',
  },
  light: {
    '--mantine-color-body': '#f6f4fa',
    '--mantine-color-text': '#1c1d22',
    '--mantine-color-dimmed': '#5b5e6b',
    '--mantine-color-default-border': '#e2deec',
    '--mantine-color-anchor': '#520978',
  },
  dark: {},
});
