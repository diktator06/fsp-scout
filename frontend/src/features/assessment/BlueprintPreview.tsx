import { Alert, Group, Loader, Stack, Text } from '@mantine/core';
import { IconInfoCircle } from '@tabler/icons-react';
import type { Blueprint } from '@/api/types';
import classes from './BlueprintPreview.module.css';

interface BlueprintPreviewProps {
  blueprint: Blueprint | undefined;
  loading?: boolean;
}

export function BlueprintPreview({ blueprint, loading = false }: BlueprintPreviewProps) {
  // Кандидат до начала видит, из чего состоит тест и почему: компетенции без
  // нужного языка в стеке выключены, а их вес перераспределён на остальные.
  if (!blueprint) {
    return (
      <Text size="sm" c="dimmed">
        Выберите специализацию — покажем, из каких тем будет состоять тест.
      </Text>
    );
  }
  const included = blueprint.competencies.filter((item) => item.included);
  const excluded = blueprint.competencies.filter((item) => !item.included);

  return (
    <Stack gap="md" aria-busy={loading}>
      <Group justify="space-between" align="baseline" wrap="nowrap">
        <Text fw={700}>Состав теста</Text>
        {loading ? (
          <Loader size="xs" />
        ) : (
          <Text size="sm" c="dimmed" className="tabular">
            {blueprint.min_items}–{blueprint.max_items} заданий
          </Text>
        )}
      </Group>
      <ul className={classes.list}>
        {included.map((item) => (
          <li key={item.code} className={classes.row}>
            <span className={classes.name}>{item.name}</span>
            <span className={classes.share}>{Math.round(item.weight * 100)}%</span>
            <span className={classes.bar} aria-hidden="true">
              <span style={{ width: `${Math.max(4, item.weight * 100)}%` }} />
            </span>
          </li>
        ))}
      </ul>
      {excluded.length > 0 && (
        <Text size="xs" c="dimmed" lh={1.5}>
          Не войдут, потому что этого нет в вашем стеке:{' '}
          {excluded.map((item) => item.name).join(', ')}
        </Text>
      )}
      {!blueprint.available && (
        <Alert color="signal" variant="light" icon={<IconInfoCircle size={18} />}>
          Для такого стека заданий пока мало. Добавьте основной язык специализации.
        </Alert>
      )}
      <Text size="xs" c="dimmed" lh={1.5}>
        Тест адаптивный: следующее задание подбирается по ответам, поэтому вернуться к пройденному
        нельзя. Задания уникальны для каждого кандидата.
      </Text>
    </Stack>
  );
}
