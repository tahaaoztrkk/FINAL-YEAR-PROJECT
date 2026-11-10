/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WS_URL?: string;
  readonly VITE_FACE_LANDMARKER_MODEL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
