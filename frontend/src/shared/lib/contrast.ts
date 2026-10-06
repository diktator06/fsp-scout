function channelToLinear(channel: number): number {
  // Перевод sRGB-канала в линейное пространство по формуле WCAG 2.x.
  const value = channel / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

export function relativeLuminance(hex: string): number {
  const normalized = hex.replace('#', '');
  const full =
    normalized.length === 3
      ? normalized
          .split('')
          .map((part) => part + part)
          .join('')
      : normalized;
  const [r, g, b] = [0, 2, 4].map((offset) => parseInt(full.slice(offset, offset + 2), 16));
  return (
    0.2126 * channelToLinear(r ?? 0) +
    0.7152 * channelToLinear(g ?? 0) +
    0.0722 * channelToLinear(b ?? 0)
  );
}

export function contrastRatio(foreground: string, background: string): number {
  // Контраст по WCAG: (L светлого + 0,05) / (L тёмного + 0,05), от 1 до 21.
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  const [light, dark] = first > second ? [first, second] : [second, first];
  return (light + 0.05) / (dark + 0.05);
}

export type ContrastLevel = 'AAA' | 'AA' | 'AA крупный' | 'не проходит';

export function contrastLevel(ratio: number): ContrastLevel {
  // Пороги WCAG 2.1 для обычного текста: AA — 4,5:1, AAA — 7:1;
  // крупный (от 18,66 px полужирным) текст проходит AA уже с 3:1.
  if (ratio >= 7) return 'AAA';
  if (ratio >= 4.5) return 'AA';
  if (ratio >= 3) return 'AA крупный';
  return 'не проходит';
}
