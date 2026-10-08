import { Badge, Text, VisuallyHidden } from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';
import type { ItemInstance } from '@/api/types';
import { ItemPrompt } from '@/features/assessment/ItemPrompt';
import { formatAnswer, formatParams } from '@/shared/lib/itemBank';
import classes from './InstancePreview.module.css';

interface InstancePreviewProps {
  instance: ItemInstance;
  showParams?: boolean;
}

export function InstancePreview({ instance, showParams = true }: InstancePreviewProps) {
  // Экземпляр глазами кандидата плюс то, чего кандидат не видит: верный вариант,
  // разбор и параметры, которые генератор выбрал случайно. Seed позволяет
  // воспроизвести экземпляр при разборе апелляции.
  const { payload, answer } = instance;
  const params = showParams ? formatParams(instance.params) : [];
  return (
    <div className={classes.root}>
      <ItemPrompt item={payload} />
      {payload.response_format === 'single_choice' ? (
        <ul className={classes.options} aria-label="Варианты ответа">
          {(payload.options ?? []).map((option) => {
            const correct = option.key === answer.correct;
            return (
              <li key={option.key} className={classes.option} data-correct={correct || undefined}>
                <span className={classes.optionKey} aria-hidden="true">
                  {correct ? <IconCheck size={15} /> : option.key}
                </span>
                <span className={classes.optionText}>
                  {option.text}
                  {correct && <VisuallyHidden> — верный ответ</VisuallyHidden>}
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className={classes.answer}>
          <Text size="sm">
            Верный ответ: <strong className="tabular">{formatAnswer(answer, payload.unit)}</strong>
          </Text>
          {payload.input_hint && (
            <Text size="xs" c="dimmed">
              Подсказка кандидату: {payload.input_hint}
            </Text>
          )}
        </div>
      )}
      {instance.explanation && (
        <Text size="sm" className={classes.explanation}>
          {instance.explanation}
        </Text>
      )}
      <div className={classes.meta}>
        {params.map((item) => (
          <Badge key={item} variant="outline" color="gray" tt="none" fw={500}>
            {item}
          </Badge>
        ))}
        <span className={classes.seed}>seed {instance.seed}</span>
      </div>
    </div>
  );
}
