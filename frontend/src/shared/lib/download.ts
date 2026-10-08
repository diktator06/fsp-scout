export function saveBlob(blob: Blob, filename: string): void {
  // Файлы API отдаются только с токеном, поэтому обычная ссылка не подойдёт:
  // скачиваем запросом и сохраняем через временную ссылку на Blob.
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
