import { Alert, Button, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core';
import { IconArrowUpRight, IconEye, IconRosetteDiscountCheck } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useAcceptSuggestedGrade } from '@/api/assessment';
import { errorMessage } from '@/api/errors';
import type { AssessmentSession, SessionResult } from '@/api/types';
import { BankPublishPrompt } from '@/features/candidate/BankPublishPrompt';
import { MODE_LABELS, OUTCOME_COPY, competencyShare } from '@/shared/lib/assessment';
import { pluralizeRu } from '@/shared/lib/format';
import { CategoryBadge, GradeScale, Kicker } from '@/shared/ui';
import classes from './ResultView.module.css';

function formatNumber(value: number): string {
  return value.toFixed(2).replace('-', '−').replace('.', ',');
}

function CompetencyBreakdown({ result }: { result: SessionResult }) {
  // Разбор по темам показывает, где были ошибки. Процент верных по теме с одним
  // заданием мало что значит, поэтому рядом всегда видно, из скольких заданий он.
  const rows = [...result.competencies].sort((a, b) => b.answered - a.answered);
  return (
    <ul className={classes.competencies}>
      {rows.map((row) => {
        const share = competencyShare(row.correct, row.answered);
        return (
          <li key={row.code} className={classes.competency}>
            <span className={classes.competencyName}>{row.name}</span>
            <span className={classes.competencyScore}>
              {row.correct} из {row.answered}
            </span>
            <span className={classes.competencyBar} aria-hidden="true">
              <span
                style={{ width: `${share}%` }}
                data-level={share >= 70 ? 'high' : share >= 40 ? 'mid' : 'low'}
              />
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function IntegrityNote({ flags }: { flags: Record<string, number> }) {
  // Сигналы честности показываем самому кандидату: он должен знать, что видит методист.
  const focusLost = flags.focus_lost ?? 0;
  const pasted = flags.paste ?? 0;
  const fast = flags.fast_correct ?? 0;
  if (focusLost + pasted + fast === 0) return null;
  const parts = [
    focusLost > 0 &&
      `уходили со вкладки ${focusLost} ${pluralizeRu(focusLost, ['раз', 'раза', 'раз'])}`,
    pasted > 0 &&
      `вставляли ответ из буфера ${pasted} ${pluralizeRu(pasted, ['раз', 'раза', 'раз'])}`,
    fast > 0 &&
      `очень быстро верно ответили на ${fast} ${pluralizeRu(fast, ['задание', 'задания', 'заданий'])}`,
  ].filter(Boolean);
  return (
    <Alert color="gray" variant="light" icon={<IconEye size={18} />}>
      Во время теста вы {parts.join(', ')}. Это видит методист; автоматически результат не
      снижается.
    </Alert>
  );
}

export function ResultView({ session }: { session: AssessmentSession }) {
  const accept = useAcceptSuggestedGrade(session.id);
  const result = session.result;

  if (!result) {
    return (
      <Card>
        <Stack gap="sm" align="flex-start">
          <Title order={3}>
            {session.status === 'expired' ? 'Время теста истекло' : 'Тест прерван'}
          </Title>
          <Text c="dimmed">
            Попытка засчитана как неуспешная. Тест на уровень ниже доступен сразу, этот уровень —
            после паузы.
          </Text>
          <Button component={Link} to="/c/assessment">
            К выбору теста
          </Button>
        </Stack>
      </Card>
    );
  }

  const copy = OUTCOME_COPY[result.outcome];
  const category = result.resulting_category;
  const cuts = result.scale.map((point) => ({
    code: point.grade.code,
    name: point.grade.name,
    cut: point.theta_cut,
  }));

  return (
    <Stack gap="lg">
      <section className={classes.hero} data-outcome={result.outcome}>
        <Stack gap="md" className={classes.heroMain}>
          <Kicker variant="ghost">Результат · {MODE_LABELS[session.mode]}</Kicker>
          <Title order={2} c="white">
            {copy.title}
          </Title>
          {category ? (
            <CategoryBadge
              specialization={category.specialization.name}
              grade={category.grade.code}
              gradeLabel={category.grade.name}
              tone="dark"
            />
          ) : (
            <Text c="rgba(255,255,255,0.82)" size="sm">
              {session.specialization.name}: тест на {result.target_grade.name} не пройден
            </Text>
          )}
          <Text c="rgba(255,255,255,0.86)" maw={560} lh={1.6}>
            {copy.text}
          </Text>
        </Stack>
        <dl className={classes.stats}>
          <div>
            <dt>Заданий</dt>
            <dd>{result.items_scored}</dd>
          </div>
          <div>
            <dt>Оценка θ</dt>
            <dd>
              {formatNumber(result.theta)}
              <small> ± {formatNumber(1.64 * result.theta_se)}</small>
            </dd>
          </div>
        </dl>
      </section>

      {category && <BankPublishPrompt />}

      <SimpleGrid cols={{ base: 1, lg: 5 }} spacing="lg">
        <Card className={classes.scaleCard}>
          <Stack gap="md">
            <Title order={4}>Где вы на шкале</Title>
            <GradeScale
              cuts={cuts}
              theta={result.theta}
              se={result.theta_se}
              targetCode={result.target_grade.code}
            />
            <Text size="sm" c="dimmed" lh={1.6}>
              Точка — оценка уровня, полоса вокруг — 90-процентный интервал. Грейд подтверждается,
              если точка правее порога заявленного уровня. Если правее порога следующего уровня вся
              полоса, тест на него открывается сразу.
            </Text>
          </Stack>
        </Card>
        <Card className={classes.topicsCard}>
          <Stack gap="md">
            <Title order={4}>По темам</Title>
            <CompetencyBreakdown result={result} />
          </Stack>
        </Card>
      </SimpleGrid>

      <IntegrityNote flags={result.integrity_flags} />

      {result.can_accept_suggested && result.suggested_grade && (
        <Card className={classes.offer}>
          <Group justify="space-between" wrap="wrap" gap="md">
            <Group gap="md" wrap="nowrap" align="flex-start">
              <IconRosetteDiscountCheck size={28} color="#520978" />
              <Stack gap={2}>
                <Text fw={700}>Тест уверенно подтвердил уровень {result.suggested_grade.name}</Text>
                <Text size="sm" c="dimmed">
                  Можно принять его сейчас, без отдельного теста. Попытку на{' '}
                  {result.target_grade.name} вы сможете повторить позже.
                </Text>
              </Stack>
            </Group>
            <Button loading={accept.isPending} onClick={() => accept.mutate()}>
              Принять {result.suggested_grade.name}
            </Button>
          </Group>
          {accept.isError && (
            <Text size="sm" c="signal.8" mt="sm">
              {errorMessage(accept.error)}
            </Text>
          )}
        </Card>
      )}

      <Group gap="sm">
        {result.next_grade_unlocked && (
          <Button component={Link} to="/c/assessment" rightSection={<IconArrowUpRight size={18} />}>
            Тест на {result.next_grade_unlocked.name} открыт
          </Button>
        )}
        <Button
          component={Link}
          to="/c"
          variant={result.next_grade_unlocked ? 'default' : 'filled'}
        >
          В кабинет
        </Button>
        <Button component={Link} to="/c/assessment" variant="subtle">
          История попыток
        </Button>
      </Group>
    </Stack>
  );
}
