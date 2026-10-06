import fspLogoBlack from '@/assets/brand/fsp-logo-black.png';
import fspLogoWhite from '@/assets/brand/fsp-logo-white.png';

interface FspLogoProps {
  tone?: 'dark' | 'light';
  height?: number;
}

export function FspLogo({ tone = 'dark', height = 28 }: FspLogoProps) {
  // Логотип постановщика задачи из брендбука. Тёмная версия идёт на светлый фон,
  // светлая на тёмный.
  return (
    <img
      src={tone === 'light' ? fspLogoWhite : fspLogoBlack}
      alt="Федерация спортивного программирования России"
      height={height}
      style={{ height, width: 'auto', display: 'block' }}
    />
  );
}
