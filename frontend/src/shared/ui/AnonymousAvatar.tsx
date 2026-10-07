import { aliasHue } from '@/shared/lib/matching';
import classes from './AnonymousAvatar.module.css';

export function AnonymousAvatar({ alias, size = 44 }: { alias: string; size?: number }) {
  // Вместо фотографии — псевдоним на цветном фоне. Работодатель различает кандидатов,
  // но не видит ни лица, ни имени, пока кандидат не откроет контакты.
  const hue = aliasHue(alias);
  return (
    <span
      className={classes.avatar}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.3,
        background: `linear-gradient(135deg, hsl(${hue} 55% 34%), hsl(${hue + 25} 60% 22%))`,
      }}
      aria-hidden="true"
    >
      {alias.slice(0, 4)}
    </span>
  );
}
