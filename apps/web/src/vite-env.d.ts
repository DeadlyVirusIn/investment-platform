/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_RESEARCH_RO_ENABLED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
