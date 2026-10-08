import {
  Alert,
  Button,
  Card,
  Group,
  List,
  Modal,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconDownload, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { downloadPersonalData } from '@/api/account';
import { errorMessage } from '@/api/errors';
import type { UserRole } from '@/api/types';
import { useAuth } from '@/features/auth/useAuth';

const DELETED_DATA: Record<UserRole, string[]> = {
  candidate: [
    'анкета, опыт, навыки и настройки приватности',
    'опрос, все попытки теста, категория и история грейдов',
    'приглашения, отклики и записи о том, каким компаниям открывались контакты',
    'привязка ФСП ID и достижения, микрозадачи и уведомления',
  ],
  employer: [
    'учётная запись рекрутера, уведомления и согласия',
    'если вы единственный рекрутер компании — сама компания с вакансиями, подборками, приглашениями и вебхуками',
  ],
  methodist: [
    'учётная запись, уведомления и согласия; решения модерации остаются в журнале без автора',
  ],
};

function DeleteAccountModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const { user, deleteAccount } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  if (!user) return null;
  const matches = email.trim().toLowerCase() === user.email;

  const confirm = async () => {
    // Удаление необратимо, поэтому подтверждение — ввод собственного email, а не галочка.
    // Сначала уходим из кабинета, затем чистим сессию: иначе защита маршрута
    // отправила бы человека на страницу входа.
    setPending(true);
    setError(null);
    try {
      await deleteAccount(email.trim());
      await navigate('/', { replace: true, flushSync: true });
      notifications.show({ color: 'teal', message: 'Аккаунт и все данные удалены' });
    } catch (caught) {
      setError(errorMessage(caught));
      setPending(false);
    }
  };

  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={700}>Удалить аккаунт</Text>} centered>
      <Stack gap="md">
        <Text size="sm">Будут удалены без возможности восстановления:</Text>
        <List size="sm" spacing={4}>
          {DELETED_DATA[user.role].map((item) => (
            <List.Item key={item}>{item}</List.Item>
          ))}
        </List>
        <Text size="sm" c="dimmed">
          В журнале аудита останется только факт удаления и число удалённых записей — без самих
          данных. Перед удалением можно скачать копию.
        </Text>
        <TextInput
          label="Введите email аккаунта"
          placeholder={user.email}
          value={email}
          onChange={(event) => setEmail(event.currentTarget.value)}
          autoComplete="off"
        />
        {error && (
          <Alert color="signal" variant="light">
            {error}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button
            color="signal"
            onClick={() => void confirm()}
            disabled={!matches}
            loading={pending}
          >
            Удалить навсегда
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function PersonalDataPanel() {
  const { user } = useAuth();
  const [opened, { open, close }] = useDisclosure(false);
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    setDownloading(true);
    try {
      await downloadPersonalData();
    } catch (caught) {
      notifications.show({ color: 'signal', message: errorMessage(caught) });
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Stack gap="lg">
      <Card padding="lg">
        <Stack gap="sm">
          <Title order={4}>Копия всех данных</Title>
          <Text size="sm" c="dimmed">
            Один JSON-файл со всем, что платформа хранит о вас: учётная запись и согласия, сессии
            входа, профиль, результаты тестов, приглашения и отклики, какие компании видели ваши
            контакты и когда. Служебные секреты — хеши паролей, ключи ответов теста — не
            выгружаются.
          </Text>
          <Group>
            <Button
              leftSection={<IconDownload size={16} />}
              variant="light"
              onClick={() => void download()}
              loading={downloading}
            >
              Скачать мои данные
            </Button>
          </Group>
        </Stack>
      </Card>
      <Card padding="lg">
        <Stack gap="sm">
          <Title order={4}>Удалить аккаунт</Title>
          <Text size="sm" c="dimmed">
            Это отзыв согласия на обработку персональных данных: аккаунт и связанные данные
            удаляются сразу, на почту придёт подтверждение.
            {user?.role === 'candidate' &&
              ' Отдельно скрыть профиль от работодателей можно в настройках приватности — без удаления.'}
          </Text>
          <Group>
            <Button
              color="signal"
              variant="light"
              leftSection={<IconTrash size={16} />}
              onClick={open}
            >
              Удалить аккаунт
            </Button>
          </Group>
        </Stack>
      </Card>
      <DeleteAccountModal opened={opened} onClose={close} />
    </Stack>
  );
}
