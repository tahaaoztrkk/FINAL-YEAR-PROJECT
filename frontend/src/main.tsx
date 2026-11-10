import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from '@/App';
import { CameraCheck } from '@/features/gaze/CameraCheck';
import '@/styles/global.css';

const container = document.getElementById('root');
if (!container) throw new Error('#root bulunamadı');

// `?kamera`: MediaPipe'ın bu makinede çalıştığını gösteren geliştirici sayfası.
const cameraCheck = new URLSearchParams(window.location.search).has('kamera');

createRoot(container).render(
  <StrictMode>{cameraCheck ? <CameraCheck /> : <App />}</StrictMode>,
);
