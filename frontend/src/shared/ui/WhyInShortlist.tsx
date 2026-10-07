import { IconCircleCheckFilled, IconCircleMinus, IconInfoCircle } from '@tabler/icons-react';
import classes from './WhyInShortlist.module.css';

export interface WhyItem {
  kind: string;
  text: string;
}

interface WhyInShortlistProps {
  items: WhyItem[];
  limit?: number;
  title?: string;
}

const ICONS = {
  plus: IconCircleCheckFilled,
  minus: IconCircleMinus,
  info: IconInfoCircle,
} as const;

export function WhyInShortlist({ items, limit, title = 'Почему в подборке' }: WhyInShortlistProps) {
  // Плюсы, минусы и справки из объяснения бэкенда. Порядок сохраняется: сначала
  // навыки, потом тест и условия — так работодатель читает карточку сверху вниз.
  const shown = limit ? items.slice(0, limit) : items;
  return (
    <section className={classes.root} aria-label={title}>
      <span className={classes.title}>{title}</span>
      <ul className={classes.list}>
        {shown.map((item) => {
          const kind = item.kind in ICONS ? (item.kind as keyof typeof ICONS) : 'info';
          const Icon = ICONS[kind];
          return (
            <li key={item.text} className={classes.item} data-kind={kind}>
              <Icon size={16} className={classes.icon} aria-hidden="true" />
              <span>{item.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
