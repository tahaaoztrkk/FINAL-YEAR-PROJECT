/**
 * Türkçe seslendirme.
 *
 * Web Speech API tarayıcıda hazır gelir, kurulum gerektirmez. Çevrimdışı
 * garanti gerekiyorsa Piper ONNX modeline geçilir (30 MB, CPU'da gerçek
 * zamanlı) — arayüz tarafı aynı kalır, yalnızca bu dosya değişir.
 */

let cachedVoice: SpeechSynthesisVoice | null = null;

function pickTurkishVoice(): SpeechSynthesisVoice | null {
  if (cachedVoice) return cachedVoice;
  const voices = window.speechSynthesis?.getVoices() ?? [];
  cachedVoice =
    voices.find((voice) => voice.lang === 'tr-TR') ??
    voices.find((voice) => voice.lang.startsWith('tr')) ??
    null;
  return cachedVoice;
}

export function speak(text: string): void {
  if (!text.trim() || !('speechSynthesis' in window)) return;

  // Önceki cümle hâlâ okunuyorsa kes: kullanıcı yeni bir şey söylemek istiyor.
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'tr-TR';
  utterance.rate = 1.0;

  const voice = pickTurkishVoice();
  if (voice) utterance.voice = voice;

  window.speechSynthesis.speak(utterance);
}

export function isTurkishVoiceAvailable(): boolean {
  return pickTurkishVoice() !== null;
}

// Sesler eşzamansız yüklenir; ilk çağrıda liste boş gelebilir.
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  window.speechSynthesis.addEventListener('voiceschanged', () => {
    cachedVoice = null;
  });
}
