import { Stack, Text } from '@mantine/core';
import type { AssessmentItem } from '@/api/types';
import { splitInlineCode } from '@/shared/lib/assessment';
import { DataTablePreview } from '@/shared/ui';
import { CodeBlock } from '@/shared/ui/CodeBlock';
import classes from './ItemPrompt.module.css';

export function ItemPrompt({ item }: { item: AssessmentItem }) {
  // Порядок как в задачнике: вопрос, затем код (запрос, программа, конфиг),
  // затем данные, на которых его нужно мысленно выполнить.
  return (
    <Stack gap="md">
      <Text component="h2" className={classes.prompt} id={`item-${item.id}-prompt`}>
        {splitInlineCode(item.prompt).map((segment, index) =>
          segment.code ? (
            <code key={index} className={classes.inlineCode}>
              {segment.text}
            </code>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
      </Text>
      {item.code && <CodeBlock code={item.code} language={item.code_language} />}
      {(item.tables ?? []).map((table) => (
        <DataTablePreview
          key={table.title}
          title={table.title}
          columns={table.columns}
          rows={table.rows}
        />
      ))}
    </Stack>
  );
}
