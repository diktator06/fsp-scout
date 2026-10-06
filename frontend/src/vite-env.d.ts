/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_MAILPIT_URL?: string;
  readonly VITE_SHOW_DEMO_ACCOUNTS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
