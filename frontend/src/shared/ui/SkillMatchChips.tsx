import { Tooltip } from '@mantine/core';
import { SKILL_STATUS_COPY, type SkillStatus } from '@/shared/lib/matching';
import classes from './SkillMatchChips.module.css';

export interface SkillChip {
  id: number;
  name: string;
  status: SkillStatus;
  importance?: 'must' | 'nice';
  via?: string | null;
}

export function SkillMatchChips({ skills }: { skills: SkillChip[] }) {
  // Навыки потребности глазами кандидата: подтверждён тестом, заявлен, закрыт
  // родственным или отсутствует. Обязательные отмечены рамкой потолще.
  return (
    <ul className={classes.list} aria-label="Совпадение навыков">
      {skills.map((skill) => {
        const copy = SKILL_STATUS_COPY[skill.status];
        const hint =
          skill.status === 'related' && skill.via
            ? `${skill.name}: нет, но есть ${skill.via}`
            : `${skill.name}: ${copy.label}${skill.importance === 'nice' ? ' (желательный)' : ''}`;
        return (
          <Tooltip key={skill.id} label={hint}>
            <li
              className={classes.chip}
              data-status={skill.status}
              data-importance={skill.importance}
              aria-label={hint}
            >
              <span aria-hidden="true" className={classes.mark}>
                {copy.short}
              </span>
              {skill.name}
            </li>
          </Tooltip>
        );
      })}
    </ul>
  );
}
