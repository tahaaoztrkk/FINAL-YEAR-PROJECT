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

/**
 * Ek sınıfı etiketleri (S4 şeması için). Arka uçtaki `SUFFIX_TAGS` ile aynı
 * küme ve aynı sıra: kısaltmada etiketler bu sırayla yazılır.
 *
 * Bir kelimeye birden çok etiket verilebilir ("istemiyorum" ->
 * `i-NEG+PROG+1S`). Sekiz etiket, eylem satırının üstündeki sekiz hücreyi
 * tam doldurur; hal ekleri (-e, -de, -den, -i) bu yüzden listede yok.
 */
export const SUFFIX_TAGS: readonly { id: string; label: string }[] = [
  { id: 'NEG', label: 'olumsuz' },
  { id: 'PAST', label: 'geçmiş' },
  { id: 'FUT', label: 'gelecek' },
  { id: 'PROG', label: 'şimdiki' },
  { id: 'Q', label: 'soru' },
  { id: '1S', label: 'ben' },
  { id: '2S', label: 'sen' },
  { id: 'PLUR', label: 'çoğul' },
];

const TAG_ORDER = new Map(SUFFIX_TAGS.map((tag, index) => [tag.id, index]));

/** Kısaltmadaki son kelimeyi baş kısmına ve etiketlerine ayırır. */
function splitLastWord(abbreviation: string): { before: string; head: string; tags: string[] } {
  const start = abbreviation.lastIndexOf(' ') + 1;
  const word = abbreviation.slice(start);
  const dash = word.indexOf('-');
  return {
    before: abbreviation.slice(0, start),
    head: dash === -1 ? word : word.slice(0, dash),
    tags: dash === -1 ? [] : word.slice(dash + 1).split('+').filter(Boolean),
  };
}

/** Yazılmakta olan kelimeye verilmiş etiketler. */
export function currentWordTags(abbreviation: string): string[] {
  return splitLastWord(abbreviation).tags;
}

/**
 * Son kelimeye etiketi ekler; zaten varsa çıkarır.
 *
 * Etiketler hangi sırayla seçilirse seçilsin `SUFFIX_TAGS` sırasında yazılır,
 * böylece ekranda görünen kısaltma eğitim verisindekiyle aynı biçimde olur.
 *
 * `toggleSuffix('y h g i-NEG', '1S')` -> `'y h g i-NEG+1S'`
 */
export function toggleSuffix(abbreviation: string, tag: string): string {
  const { before, head, tags } = splitLastWord(abbreviation);
  if (head === '') return abbreviation;
  const next = tags.includes(tag) ? tags.filter((t) => t !== tag) : [...tags, tag];
  next.sort((a, b) => (TAG_ORDER.get(a) ?? 99) - (TAG_ORDER.get(b) ?? 99));
  return next.length > 0 ? `${before}${head}-${next.join('+')}` : `${before}${head}`;
}

export const GRID_COLUMNS = 4;
export const GRID_ROWS = 3;

/** Izgaranın ekranda kapladığı alan (normalize). Üstteki üçte bir metin için. */
const GRID_AREA = { x: 0.02, y: 0.36, width: 0.96, height: 0.62 } as const;

/** Izgaranın üst kenarı. Üstteki alan (durum, kısaltma, adaylar) bunun altına taşmaz. */
export const GRID_TOP = GRID_AREA.y;
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

export interface BuildOptions {
  /**
   * 'Tamamla' tuşu. Kullanıcı testinin A koşulunda (harf harf) kapatılır;
   * hücresi boş kalır, diğer eylemler yerinden kaymaz.
   */
  expand?: boolean;
  /** Ek ekranında, yazılan kelimeye zaten verilmiş etiketler (işaretli görünür). */
  selectedTags?: readonly string[];
}

/**
 * Geçerli moda göre ekrandaki hedefleri üretir.
 *
 * Döndürülen liste hem çizim hem de sunucuya gönderilen dwell hedefleri
 * için kullanılır; iki listenin ayrışması, seçimin görsel olarak başka
 * yerde görünmesine yol açar.
 */
export function buildTargets(
  mode: KeyboardMode,
  activeGroup: number | null,
  { expand = true, selectedTags = [] }: BuildOptions = {},
): GazeTarget[] {
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
    // Seçilen etiket yerinde kalır, yalnızca işaretlenir: kullanıcı
    // yerleri ezberler, kayan hedef yanlış seçime yol açar. Yeniden
    // seçmek etiketi geri alır.
    SUFFIX_TAGS.forEach((tag, index) => {
      targets.push({
        id: `suffix:${tag.id}`,
        ...cellRect(index),
        label: selectedTags.includes(tag.id) ? `✓ ${tag.label}` : tag.label,
        kind: 'key',
      });
    });
  }

  // Eylemler her zaman son satırda, sabit konumda: kullanıcı yerlerini
  // ezberler ve aramak için ekranı taramak zorunda kalmaz.
  const actionStart = (GRID_ROWS - 1) * GRID_COLUMNS;
  ACTIONS.forEach((action, index) => {
    if (!expand && action.id === 'action:expand') return;
    // Ek ekranında 'Geri' kelimeyi bitirir: etiket seçimi bu tuşla kapanır.
    const label = mode === 'suffixes' && action.id === 'action:back' ? 'Bitti' : action.label;
    targets.push({
      id: action.id,
      ...cellRect(actionStart + index),
      label,
      kind: 'action',
    });
  });

  return targets;
}
