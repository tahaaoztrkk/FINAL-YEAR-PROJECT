/**
 * Hedef cümle karşılaştırması.
 *
 * Sunucudaki `normalize_sentence` ile aynı kural: Türkçe küçük harf,
 * yalnızca harfler, kelimeler arasında tek boşluk. Katılımcının klavyesinde
 * noktalama yok; "Su istiyorum." ile "su istiyorum" aynı cümledir. İki taraf
 * ayrışırsa doğru yazılan cümle yanlış sayılır ve deneme bitmez.
 */

export function normalizeSentence(text: string): string {
  const words = text.normalize('NFC').toLocaleLowerCase('tr-TR').match(/\p{L}+/gu);
  return words ? words.join(' ') : '';
}

export function sentencesMatch(output: string, target: string): boolean {
  const normalized = normalizeSentence(output);
  return normalized !== '' && normalized === normalizeSentence(target);
}
