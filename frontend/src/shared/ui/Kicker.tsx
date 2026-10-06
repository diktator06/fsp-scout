import type { ReactNode } from 'react';
import classes from './Kicker.module.css';

interface KickerProps {
  children: ReactNode;
  variant?: 'signal' | 'soft' | 'ghost';
}

export function Kicker({ children, variant = 'soft' }: KickerProps) {
  // Плашка-рубрика в духе шаблона ЛЦТ: заглавные буквы и разрядка. Сигнальный
  // вариант — только на тёмном фоне, где у белого текста достаточный контраст.
  return (
    <span className={classes.kicker} data-variant={variant}>
      {children}
    </span>
  );
}
