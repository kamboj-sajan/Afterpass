/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_BASE_URL?: string
  readonly VITE_LOCATION_KEY?: string
  readonly VITE_AWS_REGION?: string
  readonly VITE_AGENT_URL?: string
  readonly VITE_SUBSCRIBE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
