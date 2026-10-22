"""Dil modeline giden istem şablonları.

İstem biçimi hem sıfır atış denemelerinde hem ince ayar verisinde aynıdır;
eğitim ile çıkarım arasındaki fark, modelin doğruluğunu sessizce düşüren en
sık hatadır. Bu yüzden tek bir yerde tutulur.
"""

from __future__ import annotations

from .schemes import SUFFIX_TAGS, get_scheme

SYSTEM_PROMPT = (
    "Sen bir Türkçe iletişim yardımcısısın. Kullanıcı konuşamıyor ve gözüyle "
    "yalnızca kısaltma yazabiliyor. Verilen kısaltmayı, kuralına uyan doğal bir "
    "Türkçe cümleye çevir. Sadece cümleyi yaz, açıklama ekleme."
)

_SCHEME_RULES = {
    "S1": "Kısaltmadaki her harf, cümledeki bir kelimenin ilk harfidir.",
    "S2": "Kısaltmadaki her parça, cümledeki bir kelimenin ilk iki harfidir.",
    "S3": "Kısaltmadaki her parça, bir kelimenin ilk ve son harfidir.",
    "S4": (
        "Kısaltmadaki her parça bir kelimenin ilk harfidir; tireden sonraki "
        "etiket o kelimenin ekini belirtir."
    ),
}


def scheme_rule(scheme_id: str) -> str:
    """Şemanın kuralını modele anlatan tek cümle."""
    get_scheme(scheme_id)  # bilinmeyen şemada erken hata
    return _SCHEME_RULES.get(scheme_id.upper(), "")


def build_prompt(
    abbreviation: str,
    scheme: str = "S1",
    context: str | None = None,
    examples: list[tuple[str, str]] | None = None,
) -> str:
    """Tek bir genişletme istemi kurar.

    Args:
        abbreviation: Kullanıcının girdiği kısaltma.
        scheme: Kısaltma şeması kimliği.
        context: Karşı tarafın son cümlesi. Bağlam vermek doğruluğu belirgin
            artırır; literatürde tek konuşma turu doğruluğu iki katından
            fazlasına çıkarıyor.
        examples: Az atışlı istem için (kısaltma, cümle) çiftleri.
    """
    parts = [SYSTEM_PROMPT, "", f"Kural: {scheme_rule(scheme)}"]

    if scheme.upper() == "S4":
        tags = ", ".join(f"{k}={v}" for k, v in SUFFIX_TAGS.items())
        parts.append(f"Ek etiketleri: {tags}")

    if examples:
        parts.append("")
        parts.append("Örnekler:")
        for abbr, sentence in examples:
            parts.append(f"Kısaltma: {abbr}\nCümle: {sentence}")

    parts.append("")
    if context:
        parts.append(f"Bağlam: {context}")
    parts.append(f"Şema: {scheme.upper()}")
    parts.append(f"Kısaltma: {abbreviation}")
    parts.append("Cümle:")

    return "\n".join(parts)


def build_training_record(
    abbreviation: str, sentence: str, scheme: str, context: str | None = None
) -> dict[str, str]:
    """İnce ayar için tek bir eğitim kaydı.

    Çıktı biçimi ``{"prompt": ..., "completion": ...}`` olduğundan TRL'nin
    ``SFTTrainer`` sınıfına doğrudan verilebilir.
    """
    return {
        "prompt": build_prompt(abbreviation, scheme=scheme, context=context),
        "completion": f" {sentence}",
    }
