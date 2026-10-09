import {
  Alert,
  Badge,
  Button,
  Checkbox,
  FileButton,
  Group,
  Modal,
  Stack,
  Text,
} from '@mantine/core';
import { IconFileTypePdf } from '@tabler/icons-react';
import { useMutation } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { parseResume } from '@/api/candidate';
import { errorMessage } from '@/api/errors';
import type { ResumeDraft } from '@/api/types';
import { TEAM_ROLE_LABELS } from '@/shared/lib/candidate';
import { pluralizeRu } from '@/shared/lib/format';
import type { ResumeSection } from './profileValues';

interface ResumeImportProps {
  onApply: (draft: ResumeDraft, sections: Set<ResumeSection>) => void;
}

function Row({
  section,
  label,
  checked,
  onToggle,
  children,
}: {
  section: ResumeSection;
  label: string;
  checked: boolean;
  onToggle: (section: ResumeSection) => void;
  children: ReactNode;
}) {
  return (
    <Group align="flex-start" gap="sm" wrap="nowrap">
      <Checkbox checked={checked} onChange={() => onToggle(section)} aria-label={label} mt={2} />
      <Stack gap={2} style={{ minWidth: 0 }}>
        <Text size="sm" fw={700}>
          {label}
        </Text>
        {children}
      </Stack>
    </Group>
  );
}

export function ResumeImport({ onApply }: ResumeImportProps) {
  // Автораспознавание резюме: файл разбирается на сервере в памяти и не сохраняется.
  // Кандидат видит, что и откуда найдено, отмечает нужное — и только после
  // «Сохранить» анкета меняется. Категорию резюме не присваивает.
  const parse = useMutation({ mutationFn: parseResume });
  const [draft, setDraft] = useState<ResumeDraft | null>(null);
  const [sections, setSections] = useState<Set<ResumeSection>>(new Set());

  const handleFile = (file: File | null) => {
    if (!file) return;
    parse.mutate(file, {
      onSuccess: (result) => {
        const found = new Set<ResumeSection>();
        if (result.full_name) found.add('name');
        if (result.phone || result.telegram) found.add('contacts');
        if (result.city) found.add('city');
        if (result.experience_years !== null) found.add('experience_years');
        if (result.skills.length || result.soft_skills.length) found.add('skills');
        if (result.team_roles.length) found.add('roles');
        if (result.experiences.length) found.add('experiences');
        setSections(found);
        setDraft(result);
      },
    });
  };
  const toggle = (section: ResumeSection) =>
    setSections((previous) => {
      const next = new Set(previous);
      if (next.has(section)) next.delete(section);
      else next.add(section);
      return next;
    });

  return (
    <>
      <Group gap="sm" wrap="wrap">
        <FileButton onChange={handleFile} accept="application/pdf">
          {(props) => (
            <Button
              {...props}
              variant="light"
              leftSection={<IconFileTypePdf size={18} />}
              loading={parse.isPending}
            >
              Заполнить из резюме (PDF)
            </Button>
          )}
        </FileButton>
        <Text size="xs" c="dimmed">
          Распознаём ФИО, контакты, город, стек и софт-скиллы, роли, опыт и подсказку грейда. Файл
          не сохраняется.
        </Text>
      </Group>
      {parse.isError && (
        <Alert color="signal" variant="light" mt="sm">
          {errorMessage(parse.error)}
        </Alert>
      )}
      <Modal
        opened={draft !== null}
        onClose={() => setDraft(null)}
        title="Что нашлось в резюме"
        size="lg"
        centered
      >
        {draft && (
          <Stack gap="md">
            <Text size="sm" c="dimmed">
              Отметьте, что перенести в анкету. Навыки и роли добавятся к уже указанным.
            </Text>
            {draft.full_name && (
              <Row section="name" label="Имя" checked={sections.has('name')} onToggle={toggle}>
                <Text size="sm">{draft.full_name}</Text>
              </Row>
            )}
            {(draft.phone || draft.telegram) && (
              <Row
                section="contacts"
                label="Контакты"
                checked={sections.has('contacts')}
                onToggle={toggle}
              >
                <Text size="sm">{[draft.phone, draft.telegram].filter(Boolean).join(' · ')}</Text>
                {draft.email && (
                  <Text size="xs" c="dimmed">
                    Email из резюме ({draft.email}) не заменяет email аккаунта
                  </Text>
                )}
              </Row>
            )}
            {draft.city && (
              <Row section="city" label="Город" checked={sections.has('city')} onToggle={toggle}>
                <Text size="sm">{draft.city}</Text>
              </Row>
            )}
            {draft.experience_years !== null && (
              <Row
                section="experience_years"
                label="Стаж"
                checked={sections.has('experience_years')}
                onToggle={toggle}
              >
                <Text size="sm">
                  {String(draft.experience_years).replace('.', ',')}{' '}
                  {Number.isInteger(draft.experience_years)
                    ? pluralizeRu(draft.experience_years, ['год', 'года', 'лет'])
                    : 'года'}
                  {draft.evidence.experience_years ? ` — ${draft.evidence.experience_years}` : ''}
                </Text>
              </Row>
            )}
            {(draft.skills.length > 0 || draft.soft_skills.length > 0) && (
              <Row
                section="skills"
                label="Навыки и софт-скиллы"
                checked={sections.has('skills')}
                onToggle={toggle}
              >
                <Group gap={6}>
                  {draft.skills.map((item) => (
                    <Badge key={item.skill.id} variant="light" color="fsp" tt="none">
                      {item.skill.name}
                    </Badge>
                  ))}
                  {draft.soft_skills.map((name) => (
                    <Badge key={name} variant="outline" color="lilac" tt="none">
                      {name}
                    </Badge>
                  ))}
                </Group>
              </Row>
            )}
            {draft.team_roles.length > 0 && (
              <Row
                section="roles"
                label="Роли в команде"
                checked={sections.has('roles')}
                onToggle={toggle}
              >
                <Text size="sm">
                  {draft.team_roles.map((role) => TEAM_ROLE_LABELS[role]).join(', ')}
                </Text>
              </Row>
            )}
            {draft.experiences.length > 0 && (
              <Row
                section="experiences"
                label={`Опыт работы: ${draft.experiences.length} ${pluralizeRu(draft.experiences.length, ['место', 'места', 'мест'])}`}
                checked={sections.has('experiences')}
                onToggle={toggle}
              >
                {draft.experiences.map((item, index) => (
                  <Text key={`${item.position}-${index}`} size="sm">
                    {item.position || 'Должность не распознана'}
                    {item.company_name ? ` — ${item.company_name}` : ''}
                  </Text>
                ))}
              </Row>
            )}
            {(draft.specialization || draft.grade) && (
              <Alert color="lilac" variant="light">
                Подсказка для опроса: {draft.specialization?.name ?? 'специализация не ясна'}
                {draft.grade ? ` · ${draft.grade.name}` : ''}.
              </Alert>
            )}
            {draft.warnings.map((warning) => (
              <Text key={warning} size="xs" c="dimmed">
                {warning}
              </Text>
            ))}
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setDraft(null)}>
                Отмена
              </Button>
              <Button
                disabled={sections.size === 0}
                onClick={() => {
                  onApply(draft, sections);
                  setDraft(null);
                }}
              >
                Перенести в анкету
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}
