import { Badge, Button, Card, Drawer, Group, Select, Stack, Tabs, Text } from '@mantine/core';
import { useDisclosure, useMediaQuery } from '@mantine/hooks';
import { IconAdjustments, IconBriefcase, IconChartBar, IconPencil } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import {
  useNeed,
  useNeedCategories,
  useRefineShortlist,
  useSetMark,
  useSetNeedStatus,
  useShortlist,
} from '@/api/employer';
import { errorMessage } from '@/api/errors';
import type { CandidateCard, Need } from '@/api/types';
import { CategorySlices } from '@/features/employer/CategorySlices';
import { RefinePanel } from '@/features/employer/RefinePanel';
import { ShortlistEntryCard } from '@/features/employer/ShortlistEntryCard';
import { InviteModal } from '@/features/invitations/InviteModal';
import { WORK_FORMAT_LABELS } from '@/shared/lib/candidate';
import { formatDateTime } from '@/shared/lib/format';
import { ErrorState, LoadingState, PageHeader, SalaryRange } from '@/shared/ui';
import classes from './NeedPage.module.css';

function NeedSummary({ need }: { need: Need }) {
  const formats = need.work_formats.map((item) => WORK_FORMAT_LABELS[item]).join(', ');
  return (
    <Card mb="lg">
      <Group justify="space-between" align="flex-start" gap="lg" wrap="wrap">
        <Stack gap={8}>
          <Text size="sm" c="dimmed">
            {need.specialization.name} · {need.grades.map((grade) => grade.name).join(', ')}
            {formats ? ` · ${formats}` : ''}
            {need.city ? ` · ${need.city}` : ''}
          </Text>
          <Group gap={6}>
            {need.skills.map((item) => (
              <Badge
                key={item.skill.id}
                variant={item.importance === 'must' ? 'light' : 'outline'}
                color="fsp"
                tt="none"
              >
                {item.skill.name}
                {item.importance === 'nice' ? ' · плюс' : ''}
              </Badge>
            ))}
          </Group>
        </Stack>
        <SalaryRange
          from={need.salary_from}
          to={need.salary_to}
          caption={need.salary_gross ? 'до вычета НДФЛ' : 'на руки'}
        />
      </Group>
    </Card>
  );
}

export function NeedPage() {
  // Главный экран работодателя: слева выдача с объяснениями, справа рынок и уточнения.
  // Уточнение создаёт новую версию, переключатель версий позволяет вернуться назад.
  const { needId = '' } = useParams();
  const [version, setVersion] = useState<number | null>(null);
  const [inviting, setInviting] = useState<CandidateCard | null>(null);
  const need = useNeed(needId);
  const categories = useNeedCategories(needId);
  const shortlist = useShortlist(needId, version);
  const refine = useRefineShortlist(needId);
  const mark = useSetMark(needId);
  const status = useSetNeedStatus(needId);
  const wide = useMediaQuery('(min-width: 75em)');
  const [panelOpened, panel] = useDisclosure(false);

  if (need.isPending) return <LoadingState blocks={3} />;
  if (need.isError) {
    return <ErrorState message={errorMessage(need.error)} onRetry={() => void need.refetch()} />;
  }
  const data = shortlist.data;
  const sidePanel = (
    <Tabs defaultValue="refine" color="fsp">
      <Tabs.List grow mb="md">
        <Tabs.Tab value="refine" leftSection={<IconAdjustments size={16} />}>
          Уточнить
        </Tabs.Tab>
        <Tabs.Tab value="market" leftSection={<IconChartBar size={16} />}>
          Рынок
        </Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="refine">
        {data && (
          <RefinePanel
            key={data.version}
            need={need.data}
            current={data.filters}
            loading={refine.isPending}
            onApply={(filters) =>
              refine.mutate(filters, {
                onSuccess: (result) => {
                  setVersion(result.version);
                  panel.close();
                },
              })
            }
          />
        )}
      </Tabs.Panel>
      <Tabs.Panel value="market">
        <CategorySlices slices={categories.data} loading={categories.isPending} />
      </Tabs.Panel>
    </Tabs>
  );
  return (
    <>
      <PageHeader
        kicker="Подборка"
        title={need.data.title}
        actions={
          <>
            <Button
              variant="default"
              component={Link}
              to={`/e/needs/${needId}/edit`}
              leftSection={<IconPencil size={16} />}
            >
              Изменить
            </Button>
            <Button
              variant="light"
              component={Link}
              to={`/e/vacancies/new?need=${needId}`}
              leftSection={<IconBriefcase size={16} />}
            >
              Опубликовать как вакансию
            </Button>
            <Button
              variant="subtle"
              color="gray"
              loading={status.isPending}
              onClick={() => status.mutate(need.data.status === 'active' ? 'close' : 'reopen')}
            >
              {need.data.status === 'active' ? 'Закрыть' : 'Вернуть в работу'}
            </Button>
          </>
        }
      />
      <NeedSummary need={need.data} />
      <div className={classes.layout}>
        <Stack gap="md" className={classes.main}>
          <Group justify="space-between" wrap="wrap" gap="sm">
            <Text size="sm" c="dimmed">
              {data
                ? `В пуле ${data.stats.pool}, после фильтров ${data.stats.after_filters}, показано ${data.stats.shown}${data.stats.autofilled ? ' · точного грейда мало, добавлены соседние' : ''} · ${formatDateTime(data.created_at)}`
                : 'Собираем подборку…'}
            </Text>
            {!wide && (
              <Button size="xs" variant="light" onClick={panel.open}>
                Уточнить и рынок
              </Button>
            )}
            {data && data.versions.length > 1 && (
              <Select
                size="xs"
                w={180}
                aria-label="Версия подборки"
                data={data.versions.map((item) => ({
                  value: String(item),
                  label: `Версия ${item}${item === data.versions[0] ? ' (последняя)' : ''}`,
                }))}
                value={String(data.version)}
                onChange={(value) => setVersion(value ? Number(value) : null)}
                allowDeselect={false}
              />
            )}
          </Group>
          {shortlist.isPending ? (
            <LoadingState blocks={3} height={220} />
          ) : shortlist.isError ? (
            <ErrorState
              message={errorMessage(shortlist.error)}
              onRetry={() => void shortlist.refetch()}
            />
          ) : data && data.entries.length === 0 ? (
            <Card>
              <Text c="dimmed">
                Под эти условия пока никто не подходит. Попробуйте добавить соседние грейды или
                ослабить уточнения подборки.
              </Text>
            </Card>
          ) : (
            data?.entries.map((entry) => (
              <ShortlistEntryCard
                key={entry.card.candidate_id}
                entry={entry}
                needId={needId}
                marking={mark.isPending && mark.variables?.candidateId === entry.card.candidate_id}
                onMark={(value) =>
                  mark.mutate({ candidateId: entry.card.candidate_id, mark: value })
                }
                onInvite={() => setInviting(entry.card)}
              />
            ))
          )}
        </Stack>
        {wide ? (
          <Card className={classes.side} padding="lg">
            {sidePanel}
          </Card>
        ) : (
          <Drawer opened={panelOpened} onClose={panel.close} position="right" title="Подборка">
            {sidePanel}
          </Drawer>
        )}
      </div>
      <InviteModal
        opened={inviting !== null}
        onClose={() => setInviting(null)}
        card={inviting}
        need={need.data}
      />
    </>
  );
}
