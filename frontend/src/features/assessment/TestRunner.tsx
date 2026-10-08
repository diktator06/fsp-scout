import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Stack,
  Text,
  TextInput,
  UnstyledButton,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconAlertTriangle, IconArrowRight, IconHourglassEmpty } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  assessmentKeys,
  reportIntegrityEvent,
  useAbandonSession,
  useSubmitAnswer,
} from '@/api/assessment';
import { ApiError, errorMessage } from '@/api/errors';
import type { AssessmentItem, AssessmentSession } from '@/api/types';
import { useCountdown } from '@/shared/hooks/useCountdown';
import { MODE_LABELS } from '@/shared/lib/assessment';
import { CountdownRing, Kicker } from '@/shared/ui';
import { ItemPrompt } from './ItemPrompt';
import { useIntegritySignals } from './useIntegritySignals';
import classes from './TestRunner.module.css';

const OPTION_KEYS = ['1', '2', '3', '4'];

function ProgressTrack({ answered, min, max }: { answered: number; min: number; max: number }) {
  // Деления до минимума — обязательная часть, после него тест может закончиться
  // в любой момент, как только оценка станет достаточно точной.
  return (
    <div
      className={classes.track}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={answered}
      aria-label={`Отвечено ${answered}, тест займёт от ${min} до ${max} заданий`}
    >
      {Array.from({ length: max }, (_, index) => (
        <span
          key={index}
          className={classes.tick}
          data-done={index < answered || undefined}
          data-optional={index >= min || undefined}
        />
      ))}
    </div>
  );
}

interface ItemStageProps {
  session: AssessmentSession;
  item: AssessmentItem;
  receivedAt: number;
}

function ItemStage({ session, item, receivedAt }: ItemStageProps) {
  // Компонент монтируется заново на каждое задание: выбор, таймер и ошибки
  // начинаются с чистого листа. Когда время выходит, сессия перечитывается —
  // сервер сам закроет задание с нулём и выдаст следующее.
  const queryClient = useQueryClient();
  const submit = useSubmitAnswer(session.id);
  const secondsLeft = useCountdown(receivedAt + item.seconds_left * 1000);
  const [answer, setAnswer] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const expired = secondsLeft <= 0;
  const choice = item.response_format === 'single_choice';
  const options = useMemo(() => item.options ?? [], [item.options]);

  useEffect(() => {
    // Новое задание читается с начала: страница возвращается наверх, а фокус
    // ставится в поле ответа без прокрутки, иначе длинная формулировка уезжает
    // за верхний край экрана.
    window.scrollTo({ top: 0 });
    inputRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!expired) return;
    const timer = window.setTimeout(
      () => void queryClient.invalidateQueries({ queryKey: assessmentKeys.session(session.id) }),
      1200,
    );
    return () => window.clearTimeout(timer);
  }, [expired, queryClient, session.id]);

  useEffect(() => {
    // Горячие клавиши для вариантов: 1–4 выбирают, Enter отправляет. В поле
    // числового ответа цифры — это ввод, а Enter и так отправляет форму.
    // Enter на сфокусированной кнопке варианта не перехватываем: он её нажимает.
    if (!choice) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === 'Enter') {
        if (event.target instanceof HTMLButtonElement) return;
        event.preventDefault();
        formRef.current?.requestSubmit();
        return;
      }
      const option = options[OPTION_KEYS.indexOf(event.key)];
      if (option) setAnswer(option.key);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [choice, options]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!answer.trim() || expired || submit.isPending) return;
    try {
      await submit.mutateAsync({ item_id: item.id, answer: answer.trim() });
    } catch (error) {
      // 409 значит, что задание уже закрыто (истекло время или ответ ушёл со
      // второй вкладки): просто подтягиваем актуальное состояние сессии.
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: assessmentKeys.session(session.id) });
      }
    }
  };

  return (
    <Card className={classes.stage} padding={0}>
      <form ref={formRef} onSubmit={handleSubmit} aria-labelledby={`item-${item.id}-prompt`}>
        <div className={classes.stageHeader}>
          <Stack gap={6} className={classes.stageTitle}>
            <Text size="sm" c="dimmed" fw={600} className="tabular">
              Задание {item.position}
            </Text>
            <Kicker wrap>{item.competency_name}</Kicker>
          </Stack>
          <CountdownRing secondsLeft={secondsLeft} limit={item.time_limit_sec} />
        </div>

        <div className={classes.stageBody}>
          <ItemPrompt item={item} promptId={`item-${item.id}-prompt`} />

          {choice ? (
            <div role="radiogroup" aria-label="Варианты ответа" className={classes.options}>
              {options.map((option, index) => {
                const selected = answer === option.key;
                return (
                  <UnstyledButton
                    key={option.key}
                    role="radio"
                    aria-checked={selected}
                    className={classes.option}
                    data-selected={selected || undefined}
                    onClick={() => setAnswer(option.key)}
                    disabled={expired}
                  >
                    <span className={classes.optionKey} aria-hidden="true">
                      {index + 1}
                    </span>
                    <span className={classes.optionText}>{option.text}</span>
                  </UnstyledButton>
                );
              })}
            </div>
          ) : (
            <TextInput
              label="Ваш ответ"
              description={item.input_hint ?? undefined}
              placeholder="Например, 42"
              value={answer}
              onChange={(event) => setAnswer(event.currentTarget.value)}
              onPaste={() => reportIntegrityEvent(session.id, 'paste')}
              rightSection={
                item.unit ? (
                  <Text size="sm" c="dimmed">
                    {item.unit}
                  </Text>
                ) : null
              }
              rightSectionWidth={item.unit ? 64 : undefined}
              inputMode="decimal"
              autoComplete="off"
              maxLength={64}
              disabled={expired}
              ref={inputRef}
              className={classes.numeric}
            />
          )}

          {expired && (
            <Alert color="signal" variant="light" icon={<IconHourglassEmpty size={18} />}>
              Время на задание вышло — загружаем следующее.
            </Alert>
          )}
          {submit.isError && !(submit.error instanceof ApiError && submit.error.status === 409) && (
            <Alert color="signal" variant="light" icon={<IconAlertTriangle size={18} />}>
              {errorMessage(submit.error)}
            </Alert>
          )}
        </div>

        <div className={classes.stageFooter}>
          <Text size="xs" c="dimmed">
            {choice ? '1–4 — выбрать вариант, Enter — ответить' : 'Enter — ответить'}. Вернуться к
            заданию нельзя.
          </Text>
          <Button
            type="submit"
            size="md"
            rightSection={<IconArrowRight size={18} />}
            loading={submit.isPending}
            disabled={!answer.trim() || expired}
          >
            Ответить
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function TestRunner({
  session,
  receivedAt,
}: {
  session: AssessmentSession;
  receivedAt: number;
}) {
  const [confirmOpened, confirm] = useDisclosure(false);
  const abandon = useAbandonSession(session.id);
  useIntegritySignals(session.id, session.status === 'in_progress');
  const item = session.current_item;

  return (
    <Stack gap="lg" className={classes.root}>
      <div className={classes.header}>
        <Stack gap={8} className={classes.headerMain}>
          <Group gap="xs" wrap="wrap">
            <Text fw={800} size="lg">
              {session.specialization.name}
            </Text>
            <Badge color="fsp" variant="light">
              {session.target_grade.name}
            </Badge>
            {session.mode === 'express' && (
              <Badge color="signal" variant="light">
                {MODE_LABELS.express}
              </Badge>
            )}
          </Group>
          <ProgressTrack
            answered={session.answered}
            min={session.min_items}
            max={session.max_items}
          />
          <Text size="xs" c="dimmed" className="tabular">
            Отвечено {session.answered} · тест займёт от {session.min_items} до {session.max_items}{' '}
            заданий
          </Text>
        </Stack>
        <Button variant="subtle" color="gray" onClick={confirm.open}>
          Прервать тест
        </Button>
      </div>

      {item ? (
        <ItemStage key={item.id} session={session} item={item} receivedAt={receivedAt} />
      ) : (
        <Card>
          <Text c="dimmed">Подбираем следующее задание…</Text>
        </Card>
      )}

      <Modal opened={confirmOpened} onClose={confirm.close} title="Прервать тест?" centered>
        <Stack gap="md">
          <Text size="sm" lh={1.6}>
            Прерванный тест считается неуспешной попыткой этого уровня: повторить его можно будет
            позже, а тест на уровень ниже доступен сразу.
          </Text>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={confirm.close}>
              Продолжить тест
            </Button>
            <Button
              color="signal"
              loading={abandon.isPending}
              onClick={() => abandon.mutate(undefined, { onSettled: confirm.close })}
            >
              Прервать
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
