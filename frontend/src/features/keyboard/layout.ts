/**
 * Türkçe klavye düzeni.
 *
 * Tek tasarım kısıtı: hiçbir hedef 4 cm'den küçük olmayacak. 1920x1080
 * ekranda 3x4'lük ızgara bunu sağlar (hedef başına ~480x240 piksel).
 *
 * Harf seçimi iki adımlıdır: önce grup, sonra gruptaki harf aynı ızgarada
 * açılır. Bu, 29 harfi 12 hedefe sığdırmanın tek yolu.
 *
 * Denenmeye değer varyant: grup adımında durmak. Kullanıcı yalnızca grubu
 * seçer, hangi harf olduğunu dil modeli çözer — telefonlardaki T9 mantığı.
 * Her karakter için iki dwell yerine bir dwell demek, yani yazma hızında
 * doğrudan iki kat kazanç. `AMBIGUOUS_MODE` bunu açar.
 */

import type { GazeTarget } from '@/types/messages';

export const TURKISH_ALPHABET = 'abcçdefgğhıijklmnoöprsştuüvyz'.split('');

/** Harf grupları. Her grup tek bir hedefe karşılık gelir. */
export const LETTER_GROUPS: readonly string[][] = [
  ['a', 'b', 'c', 'ç'],
  ['d', 'e', 'f', 'g'],
  ['ğ', 'h', 'ı', 'i'],
  ['j', 'k', 'l', 'm'],
  ['n', 'o', 'ö', 'p'],
  ['r', 's', 'ş', 't'],
  ['u', 'ü', 'v', 'y', 'z'],
];

/** Ek sınıfı etiketleri (S4 şeması için). */
export const SUFFIX_TAGS: readonly { id: string; label: string }[] = [
  { id: 'NEG', label: 'olumsuz' },
  { id: 'PAST', label: 'geçmiş' },
  { id: 'FUT', label: 'gelecek' },
  { id: 'PROG', label: 'şimdiki' },
  { id: 'Q', label: 'soru' },
  { id: '1S', label: 'ben' },
];

export const GRID_COLUMNS = 4;
export const GRID_ROWS = 3;

/** Izgaranın ekranda kapladığı alan (normalize). Üstteki üçte bir metin için. */
const GRID_AREA = { x: 0.02, y: 0.36, width: 0.96, height: 0.62 } as const;
const GAP = 0.008;

export type KeyboardMode = 'groups' | 'letters' | 'suffixes';

export interface KeyboardAction {
  id: string;
  label: string;
}

export const ACTIONS: readonly KeyboardAction[] = [
  { id: 'action:expand', label: 'Tamamla' },
  { id: 'action:delete', label: 'Sil' },
  { id: 'action:speak', label: 'Seslendir' },
  { id: 'action:back', label: 'Geri' },
];

/** Izgaradaki (satır, sütun) hücresini normalize dikdörtgene çevirir. */
function cellRect(index: number): { x: number; y: number; width: number; height: number } {
  const row = Math.floor(index / GRID_COLUMNS);
  const column = index % GRID_COLUMNS;
  const cellWidth = GRID_AREA.width / GRID_COLUMNS;
  const cellHeight = GRID_AREA.height / GRID_ROWS;
  return {
    x: GRID_AREA.x + column * cellWidth + GAP / 2,
    y: GRID_AREA.y + row * cellHeight + GAP / 2,
    width: cellWidth - GAP,
    height: cellHeight - GAP,
  };
}

/**
 * Geçerli moda göre ekrandaki hedefleri üretir.
 *
 * Döndürülen liste hem çizim hem de sunucuya gönderilen dwell hedefleri
 * için kullanılır; iki listenin ayrışması, seçimin görsel olarak başka
 * yerde görünmesine yol açar.
 */
export function buildTargets(mode: KeyboardMode, activeGroup: number | null): GazeTarget[] {
  const targets: GazeTarget[] = [];

  if (mode === 'groups') {
    LETTER_GROUPS.forEach((group, index) => {
      targets.push({
        id: `group:${index}`,
        ...cellRect(index),
        label: group.join(' '),
        kind: 'group',
      });
    });
    // Boşluk yalnızca grup ekranında: kelime bir harf seçildikten sonra
    // bittiği için kullanıcı her zaman bu ekrana dönmüş olur. Genişletici
    // kelime sınırı olmadan çalışmaz ('si' aday üretmez, 's i' üretir).
    targets.push({
      id: 'action:space',
      ...cellRect(LETTER_GROUPS.length),
      label: 'Boşluk',
      kind: 'action',
    });
  } else if (mode === 'letters' && activeGroup !== null) {
    const letters = LETTER_GROUPS[activeGroup] ?? [];
    letters.forEach((letter, index) => {
      targets.push({
        id: `letter:${letter}`,
        ...cellRect(index),
        label: letter.toLocaleUpperCase('tr-TR'),
        kind: 'key',
      });
    });
  } else if (mode === 'suffixes') {
    SUFFIX_TAGS.forEach((tag, index) => {
      targets.push({
        id: `suffix:${tag.id}`,
        ...cellRect(index),
        label: tag.label,
        kind: 'key',
      });
    });
  }

  // Eylemler her zaman son satırda, sabit konumda: kullanıcı yerlerini
  // ezberler ve aramak için ekranı taramak zorunda kalmaz.
  const actionStart = (GRID_ROWS - 1) * GRID_COLUMNS;
  ACTIONS.forEach((action, index) => {
    targets.push({
      id: action.id,
      ...cellRect(actionStart + index),
      label: action.label,
      kind: 'action',
    });
  });

  return targets;
}

/** Aday cümleler için hedefler. Ekranın üst bandında yer alır. */
export function buildCandidateTargets(count: number): GazeTarget[] {
  const height = 0.055;
  return Array.from({ length: count }, (_, index) => ({
    id: `candidate:${index}`,
    x: 0.02,
    y: 0.08 + index * (height + 0.006),
    width: 0.96,
    height,
    label: '',
    kind: 'candidate' as const,
  }));
}
