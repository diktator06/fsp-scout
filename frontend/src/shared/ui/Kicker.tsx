import type { ReactNode } from 'react';
import classes from './Kicker.module.css';

interface KickerProps {
  children: ReactNode;
  variant?: 'signal' | 'soft' | 'ghost';
  wrap?: boolean;
}

export function Kicker({ children, variant = 'soft', wrap = false }: KickerProps) {
  // Плашка-рубрика в духе шаблона ЛЦТ: заглавные буквы и разрядка. Сигнальный
  // вариант — только на тёмном фоне, где у белого текста достаточный контраст.
  // Длинным рубрикам (названия компетенций) разрешён перенос, чтобы на телефоне
  // они не выталкивали соседние элементы за край экрана.
  return (
    <span className={classes.kicker} data-variant={variant} data-wrap={wrap || undefined}>
      {children}
    </span>
  );
}
