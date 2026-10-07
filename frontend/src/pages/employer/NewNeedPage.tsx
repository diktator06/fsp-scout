import { Alert, Button, Card, Group, Stack, Text, Textarea } from '@mantine/core';
import { IconSparkles } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useParseNeed, useSaveNeed } from '@/api/employer';
import { errorMessage } from '@/api/errors';
import type { NeedDraft } from '@/api/types';
import { CompanyGate } from '@/features/employer/CompanyGate';
import { NeedForm } from '@/features/employer/NeedForm';
import { draftToValues, type NeedFormValues } from '@/features/employer/needValues';
import { PageHeader } from '@/shared/ui';

const EXAMPLE = `Python-разработчик (Middle) в команду платежей
Требования: Python, FastAPI, PostgreSQL, опыт от 2 лет.
Будет плюсом: Kafka, Docker.
Удалённо или гибрид, вилка 230–320 тыс. ₽ до вычета НДФЛ.`;

const EMPTY: NeedFormValues = {
  title: '',
  raw_text: '',
  team_description: '',
  specialization_id: null,
  grade_ids: [],
  skills: [],
  work_formats: [],
  city: '',
  salary_from: null,
  salary_to: null,
  salary_gross: true,
};

export function NewNeedPage() {
  // Два шага: свободный текст → проверка разобранных полей. Разбор не сохраняет
  // ничего сам: работодатель видит, что нашла система, и правит перед сохранением.
  const navigate = useNavigate();
  const parse = useParseNeed();
  const save = useSaveNeed();
  const [text, setText] = useState('');
  const [draft, setDraft] = useState<NeedDraft | null>(null);
  const [manual, setManual] = useState(false);

  const handleParse = async () => {
    try {
      setDraft(await parse.mutateAsync(text));
    } catch {
      // Ошибка показывается под полем из состояния мутации.
    }
  };

  const showForm = draft !== null || manual;
  return (
    <>
      <PageHeader
        kicker="Подборки"
        title="Новая потребность"
        description="Опишите, кого ищете, как написали бы коллеге. Стек, грейд, формат и вилку система найдёт сама."
      />
      <CompanyGate>
        {!showForm ? (
          <Card>
            <Stack gap="md">
              <Textarea
                label="Кого ищете"
                placeholder={EXAMPLE}
                autosize
                minRows={6}
                maxLength={5000}
                value={text}
                onChange={(event) => setText(event.currentTarget.value)}
              />
              {parse.isError && (
                <Alert color="signal" variant="light">
                  {errorMessage(parse.error)}
                </Alert>
              )}
              <Group gap="sm">
                <Button
                  leftSection={<IconSparkles size={16} />}
                  onClick={handleParse}
                  loading={parse.isPending}
                  disabled={text.trim().length < 20}
                >
                  Разобрать текст
                </Button>
                <Button variant="subtle" onClick={() => setText(EXAMPLE)}>
                  Подставить пример
                </Button>
                <Button variant="subtle" color="gray" onClick={() => setManual(true)}>
                  Заполнить вручную
                </Button>
              </Group>
              <Text size="xs" c="dimmed">
                Разбор работает без внешних нейросетей: по справочнику из 150 навыков с синонимами
                («питон», «постгрес», «k8s») и правилам для грейда, формата и вилки.
              </Text>
            </Stack>
          </Card>
        ) : (
          <NeedForm
            initial={draft ? draftToValues(draft) : { ...EMPTY, raw_text: text }}
            evidence={draft?.evidence}
            submitLabel="Сохранить и подобрать кандидатов"
            onSubmit={(payload) => save.mutateAsync(payload)}
            onSaved={(need) => navigate(`/e/needs/${need.id}`)}
          />
        )}
      </CompanyGate>
    </>
  );
}
