import { Stack, Text } from '@mantine/core';
import type { ItemTable } from '@/api/types';
import { splitInlineCode } from '@/shared/lib/assessment';
import { DataTablePreview } from '@/shared/ui';
import { CodeBlock } from '@/shared/ui/CodeBlock';
import classes from './ItemPrompt.module.css';

export interface PromptContent {
  prompt: string;
  code?: string | null;
  code_language?: string | null;
  tables?: ItemTable[];
}

export function ItemPrompt({ item, promptId }: { item: PromptContent; promptId?: string }) {
  // Порядок как в задачнике: вопрос, затем код (запрос, программа, конфиг),
  // затем данные, на которых его нужно мысленно выполнить.
  return (
    <Stack gap="md">
      <Text component="h2" className={classes.prompt} id={promptId}>
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
