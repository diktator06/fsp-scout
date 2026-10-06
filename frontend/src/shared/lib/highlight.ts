import './prismGlobal';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-docker';
import 'prismjs/components/prism-http';

const LANGUAGE_ALIASES: Record<string, string> = {
  html: 'markup',
  text: 'plain',
  shell: 'bash',
  dockerfile: 'docker',
};

const LANGUAGE_TITLES: Record<string, string> = {
  python: 'Python',
  sql: 'SQL',
  javascript: 'JavaScript',
  jsx: 'JSX',
  css: 'CSS',
  markup: 'HTML',
  bash: 'Bash',
  docker: 'Dockerfile',
  http: 'HTTP',
};

export function prismLanguage(language: string | null | undefined): string {
  // Генераторы заданий называют языки по-своему (html, text): приводим к именам Prism.
  // Неизвестный язык показываем без подсветки, а не падаем.
  const normalized = (language ?? 'plain').toLowerCase();
  return LANGUAGE_ALIASES[normalized] ?? normalized;
}

export function languageTitle(language: string | null | undefined): string | null {
  return LANGUAGE_TITLES[prismLanguage(language)] ?? null;
}
