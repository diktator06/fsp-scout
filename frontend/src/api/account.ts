import { api } from './client';
import { unwrap } from './errors';
import { saveBlob } from '@/shared/lib/download';

export async function downloadPersonalData(): Promise<void> {
  // Выгрузка отдаётся только с токеном, поэтому качаем запросом и сохраняем как файл.
  const blob = await unwrap(api.GET('/api/v1/account/personal-data', { parseAs: 'blob' }));
  saveBlob(blob, `scout-personal-data-${new Date().toISOString().slice(0, 10)}.json`);
}
