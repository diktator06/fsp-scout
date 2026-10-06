import { useMemo } from 'react';
import classes from './ConstellationBackdrop.module.css';

interface ConstellationBackdropProps {
  seed?: number;
  nodes?: number;
  highlight?: number;
  fade?: 'left' | 'none';
}

const VIEW_WIDTH = 160;

interface Point {
  x: number;
  y: number;
  r: number;
}

function createRandom(seed: number): () => number {
  // Детерминированный генератор (LCG): узор одинаков при каждом рендере и не
  // мигает при перерисовке, а разные экраны получают свой узор через seed.
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function buildConstellation(seed: number, count: number) {
  // Узлы разбрасываются по сетке с дрожанием, чтобы не слипаться, а соединяются
  // только соседние: так узор читается как созвездие из логотипа ФСП, а не как шум.
  const random = createRandom(seed);
  const columns = Math.ceil(Math.sqrt(count * 1.8));
  const rows = Math.ceil(count / columns);
  const points: Point[] = [];
  for (let index = 0; index < count; index += 1) {
    const column = index % columns;
    const row = Math.floor(index / columns);
    points.push({
      x: ((column + 0.2 + random() * 0.6) / columns) * VIEW_WIDTH,
      y: ((row + 0.2 + random() * 0.6) / rows) * 100,
      r: 0.28 + random() * 0.32,
    });
  }
  const edges: Array<[Point, Point]> = [];
  points.forEach((point, index) => {
    const nearest = points
      .map((other, otherIndex) => ({
        other,
        otherIndex,
        distance: Math.hypot(point.x - other.x, point.y - other.y),
      }))
      .filter((item) => item.otherIndex > index && item.distance < 34)
      .sort((left, right) => left.distance - right.distance)
      .slice(0, 2);
    nearest.forEach((item) => edges.push([point, item.other]));
  });
  return { points, edges };
}

export function ConstellationBackdrop({
  seed = 7,
  nodes = 26,
  highlight = 2,
  fade = 'none',
}: ConstellationBackdropProps) {
  const { points, edges, signals } = useMemo(() => {
    // Подсвеченные узлы распределяем равномерно по списку: при любом seed
    // сигнальные точки не собираются в одном углу.
    const constellation = buildConstellation(seed, nodes);
    const step = nodes / Math.max(1, highlight);
    const signalIndexes = new Set(
      Array.from({ length: highlight }, (_, index) => Math.floor(step * (index + 0.5))),
    );
    return { ...constellation, signals: signalIndexes };
  }, [seed, nodes, highlight]);

  return (
    <svg
      className={classes.root}
      data-fade={fade}
      viewBox={`0 0 ${VIEW_WIDTH} 100`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      {edges.map(([from, to], index) => (
        <line key={index} x1={from.x} y1={from.y} x2={to.x} y2={to.y} className={classes.edge} />
      ))}
      {points.map((point, index) =>
        signals.has(index) ? (
          <circle
            key={index}
            cx={point.x}
            cy={point.y}
            r={point.r + 0.6}
            className={classes.signal}
          />
        ) : (
          <circle
            key={index}
            cx={point.x}
            cy={point.y}
            r={point.r * 0.6}
            className={classes.node}
          />
        ),
      )}
    </svg>
  );
}
