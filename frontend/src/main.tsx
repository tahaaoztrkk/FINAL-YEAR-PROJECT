import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from '@/App';
import { CameraCheck } from '@/features/gaze/CameraCheck';
import { GazeLive } from '@/features/gaze/GazeLive';
import { GazeMeasure } from '@/features/gaze/GazeMeasure';
import '@/styles/global.css';

const container = document.getElementById('root');
if (!container) throw new Error('#root bulunamadı');

// `?kamera`: MediaPipe'ın bu makinede çalıştığını gösteren geliştirici sayfası.
// `?olcum`: bilinen noktalara bakarken landmark kaydı (ekran hatası ölçümü).
const params = new URLSearchParams(window.location.search);
// `?bakis`: kalibrasyondan sonra baktığın yeri canlı gösterir.
const Page = params.has('bakis')
  ? GazeLive
  : params.has('olcum')
    ? GazeMeasure
    : params.has('kamera')
      ? CameraCheck
      : App;

createRoot(container).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
