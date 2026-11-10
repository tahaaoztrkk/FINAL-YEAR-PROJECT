# Ön Kayıt: Hipotezler, Ölçütler ve Analiz Planı

**Sorumlu:** Polat Elmas (Kişi 4 — deney ve yazım)
**Durum:** TASLAK. Ekip onayından sonra `main`'e birleştirilir ve `onkayit-v1` etiketi konur.
**Kayıt tarihi:** `onkayit-v1` etiketli commit'in tarihi.

> **Kural:** `onkayit-v1` etiketinden sonra 1–5. bölümler değiştirilmez. Her değişiklik en alttaki
> **Değişiklik günlüğü**ne tarih, gerekçe ve "veri görülmeden önce mi, sonra mı" bilgisiyle eklenir.
> Raporda ön kayıtlı analizler ile keşif amaçlı analizler ayrı başlıklarda verilir.

Bu dosya kodu tanımlamaz, kodun **neyi kanıt sayacağını** önceden sabitler. Ölçütlerin hesaplandığı yerler:
`backend/src/gaze_aac/evaluation/metrics.py`, `simulate.py`, `study.py` ve `study/protocol.py`.
Kod ile bu dosya ayrışırsa, veri toplanmadan önce biri düzeltilir.

İşaretler: **[EKİPLE]** ekipte anlaşılacak nokta ·
**[DOĞRULANACAK]** kaynağı henüz açılıp kontrol edilmedi.

---

## 0. Kapsam

İki ayrı çalışma vardır; her birinin **tek bir birincil hipotezi** vardır.

| | Çalışma A — Çevrimdışı simülasyon | Çalışma B — Kullanıcı testi |
|---|---|---|
| Soru | Türkçede hangi kısaltma şeması en iyi tuş tasarrufu–doğruluk dengesini verir? | Kısaltma sistemi, harf harf göz klavyesine göre yazma hızını artırır mı? |
| Gözlem birimi | Cümle | Katılımcı |
| Tasarım | 4 şema × 3 model × bağlamlı/bağlamsız = 24 koşul, aynı cümlelerle eşleştirilmiş | Denek içi, 2 koşul (A harf harf, B kısaltma), karşıt dengelemeli |
| Örneklem | Ayrılmış test kümesi: 295 cümle (doğrulama 291, eğitim 2.321; 11 Kasım derlemi) | 12–15 sağlıklı gönüllü (alt sınır 10) |
| Kod | `python -m gaze_aac.evaluation.simulate` | `python -m gaze_aac.evaluation.study` |

---

## 1. Hipotezler

### 1.1 Çalışma A — Simülasyon

**H-A1 (birincil):** İnce ayarlı model, bağlamsız koşulda, **S4** (baş harf + ek sınıfı etiketi), **S1**'e (yalnızca baş harf)
göre cümle başına **daha az toplam seçim** gerektirir.

Gerekçe: Projenin özgün iddiası budur. Türkçede baş harf ekleri kaybettiği için S4'ün kısaltması başta daha uzun olsa da
düzeltme turları azaldığından toplamda daha az seçim gerekir.

> **Teknik plandaki ifade düzeltildi.** Planda (ve `schemes.py`'deki açıklamada) "S4 daha az tasarruf etse de toplam seçimi düşürür"
> deniyor. KSR toplam seçimden hesaplandığı için toplam seçim azalırsa KSR **artar**; ifade bu hâliyle kendiyle çelişir.
> Tutarlı hâli iki ölçütle kurulur: **nominal tasarruf** (`metrics.theoretical_savings`: her genişletme ilk denemede doğru
> olsaydı) ve **gerçekleşen KSR** (geri dönüşler dahil). Hipotez: S4'ün nominal tasarrufu S1'inkinden düşük, gerçekleşen
> KSR'si yüksek.

**Karar (Polat, 8 Kasım):** Birincil hipotez H-A1'dir. Değerlendirilen alternatifler: (a) yönsüz "şemalar arasında ilk-1
doğrulukta fark vardır"; (b) birincil hipotezi yalnızca Çalışma B'ye koymak. (b) seçilmedi: kullanıcı testi etik onaya bağlı ve
4 kişilik pilota inebilir, o zaman projenin ön kayıtlı birincil sonucu kalmaz. H-A1 tutmazsa bu da raporlanacak bir bulgudur.

**İkincil hipotezler (Holm düzeltmesiyle tek aile):**
- **H-A2:** S1 dört şema içinde en yüksek nominal tasarrufu, ama en düşük ilk-1 doğruluğu verir.
- **H-A3:** İnce ayarlı Turkish-Gemma, ince ayarsız (sıfır atış) Turkish-Gemma'dan daha yüksek ilk-1 doğruluk verir (S1, bağlamsız).
- **H-A4:** Diyalog bağlamı ilk-1 doğruluğu artırır (ince ayarlı model, S1).
  > Bağlam: Doğrulama ve test kümesindeki **her** cümlenin `context` alanı var (karşı tarafın o cümleden hemen önce
  > söylediği cümle; PR #19). Bu yüzden bağlamlı ve bağlamsız koşullar aynı cümlelerde, eşleştirilmiş ölçülür.
  > Bağlamlar üç türden karışık: cevabı güçlü ima eden, yalnızca konuyu veren ve genel ("Bir şey ister misin?").
  > **Sınırlılık:** Bağlamlar gerçek diyaloglardan kaydedilmedi, her cümle için ayrıca yazıldı. H-A4 "doğal diyalog
  > bağlamının" değil, "bu şekilde yazılmış bağlamın" etkisini ölçer. Bağlamın etkisi yalnızca bağlamla eğitilmiş
  > modelde (5 Aralık yeniden eğitimi) anlamlıdır; n-gram bağlamı kullanmaz.

**Yalnızca betimsel:** büyük API modeli (üst sınır; model adı, sürümü ve sorgu tarihi kaydedilir), n-gram (alt sınır), gecikme
ölçüleri, MRR. T9 (harf grubu) varyantı **keşif amaçlıdır**, ön kayıtlı değildir.

### 1.2 Çalışma B — Kullanıcı testi

**H-B1 (birincil):** B koşulunda (kısaltma + aday listesi) yazma hızı (`wpm`), A koşuluna (harf harf) göre **daha yüksektir**.

> Planda "WPM'i en az %30 artırır" yazıyor. "%30'dan fazla" iddiasını test etmek (H₀: oran ≤ 1,3) 12 kişiyle çok daha fazla
> güç ister. Test edilen hipotez **"fark > 0"**dır; %30 **beklenen etki** olarak yazılır ve sonuçta B/A oranının %95 güven
> aralığı verilir.

**İkincil hipotezler (Holm düzeltmesiyle):**
- **H-B2:** B koşulunun SUS puanı 68'den yüksektir (tek örneklem testi).
- **H-B3:** B koşulunda cümle başına düzeltme sayısı (`duzeltme` = Sil + Geri) A'dan düşüktür.

**Yalnızca betimsel:** `study.py`'nin `karsilastirma.csv`'de p değeri verdiği diğer ölçüler (`ksr`, `sure_s`, `secim`,
`yanlis_cikti`) **hipotez testi sayılmaz**; raporda betimsel tablo olarak verilir. (`sure_s` ile `wpm` aynı şeyi ölçer; ikisini
ayrı "anlamlı bulgu" saymak çoklu karşılaştırma hatası olur.) Ayrıca: B koşulunda ilk-1 / ilk-5, kalibrasyon hatası, kısa anket
maddeleri (`k1`–`k5`), 2019 Türkçe webcam klavyesiyle (6,63 kelime/dk) dolaylı kıyas. Bu son kıyas **farklı düzenekle**
(gözlüğe takılı kamera) elde edildiği için kanıt değil bağlamdır.

**Kullanıcı testinin şeması: S1** (`data/study/sentences.json`, `"scheme": "S1"`). Simülasyon sonuçlarına bakılarak
değiştirilmez; "en iyi çıkanı seçtiniz" eleştirisini bu önler.

---

## 2. Ölçütlerin kesin tanımları

### 2.1 İki ayrı KSR (repodaki tanımlar)

| | Simülasyon KSR'si | Kullanıcı testi KSR'si |
|---|---|---|
| Formül | (1 − toplam_seçim / toplam_harf) × 100 | (1 − seçim / harf_harf_en_az_seçim) × 100 |
| Payda | `character_count`: boşluksuz harf sayısı, harf başına 1 seçim | `letter_by_letter_selections`: harf başına 2 seçim (grup + harf), kelime aralarında 1 Boşluk, sonda 1 Seslendir |
| Pay | Kısaltmanın seçimleri + açık yazılan kelimelerin fazladan harfleri + 1 aday seçimi | Arayüzdeki bütün seçimler (dwell ya da tıklama) |
| Sayılmayan | "Tamamla" ve "Seslendir" seçimleri (bütün şemalarda aynı olduğu için karşılaştırmayı etkilemez, mutlak KSR'yi yükseltir) | — |

İki KSR aynı tabloda karşılaştırılmaz (`docs/setup.md` de bunu söylüyor). H-A1'in ölçütü simülasyondaki **cümle başına toplam seçim**dir.

**Örnek — "Yarın hastaneye gitmek istemiyorum." (31 harf; arayüzde harf harf en az 66 seçim).** Değerler repodaki kodla (11 Kasım, Zemberek etiketleri, 8 etiket) hesaplandı:

| Şema | Kısaltma (`abbreviate`) | Kısaltma seçimi | Simülasyon KSR'si, ilk aday doğruysa |
|---|---|---|---|
| S1 | `y h g i` | 4 | %83,9 |
| S2 | `ya ha gi is` | 8 | %71,0 |
| S3 | `yn he gk im` | 8 | %71,0 |
| S4 | `y h g i-NEG+PROG+1S` | 7 | %74,2 |

**S4 etiket kümesi (karar verildi, PR #18 ve #20):** Simülasyon ve arayüz aynı **8 etiketi** kullanır: NEG, PAST, FUT, PROG,
Q, 1S, 2S, PLUR. Hal ekleri (DAT, LOC, ABL, ACC) arayüz ızgarasına sığmadığı için çıkarıldı. Bir kelimeye birden çok etiket
seçilebilir; etiketler hep `SUFFIX_TAGS` sırasında yazılır, geri kontrol sıraya bakmaz. Etiketler Zemberek'in bağlamlı
çözümlemesinden gelir (`nlp/morphology.py`); Zemberek'in tanımadığı kelimelerde kural tablosuna dönülür.
**S4'ün model sonuçları 5 Aralık'taki yeniden eğitimden önce rapora girmez:** şu anki model eski (12 etiketli, kural tabanlı)
S4 çiftleriyle eğitildi. Sınırlılık: hal ekleri etiketlenmediği için S4 Türkçedeki ek kaybının yalnızca bir kısmını telafi eder.

### 2.2 Simülasyondaki kullanıcı modeli (`simulate.simulate_case`)

Tur 1'de tam kısaltma girilir. Doğru cümle ilk 5 adayda yoksa sonraki her turda **cümlenin başından bir kelime daha açık
yazılır**. En fazla 5 tur denenir. Doğru cümle hiç bulunmazsa cümle harf harf yazılmış sayılır.

**Maliyet kuralları (karar verildi, PR #20):**
- Bulunan cümle: o ana kadar girilen seçimler (kısaltma + açık yazılan kelimelerin fazladan harfleri) + 1 aday seçimi.
- Bulunamayan cümle: son denemeye kadar girilen seçimler **boşa gitmiş** sayılır ve cümle baştan harf harf yazılır
  (maliyet = girilen seçimler + harf sayısı). Son denemede bütün kelimeler açık yazılmışsa cümle zaten yazılmıştır; maliyet
  = girilen seçimler + 1 (seslendirme).
- Bu kurallar altında bir cümlenin KSR'si negatif olabilir (kısaltma denemesi harf harf yazmaktan pahalıya gelmiş demektir).
  Negatif değerler kırpılmaz, olduğu gibi raporlanır.

**[EKİPLE — Taha] Açık kalan tek nokta:** En fazla 5 deneme (`max_rounds = 5`) sınırı, 4 kelimeden uzun cümlelerde bütün
kelimeler açık yazılmadan denemeyi keser. Sınır sabit bir parametre olarak bu dosyayla birlikte dondurulur; değiştirilecekse
`onkayit-v1`'den önce değiştirilir.

**Doğru cümle eşleşmesi:** `tokenize` ile normalleştirme (Türkçe küçük harf, noktalama yok, tek boşluk) sonrası birebir eşleşme.
Simülasyon ve kullanıcı testi aynı kuralı kullanır (`protocol.normalize_sentence`). Anlamca yakın cümle doğru sayılmaz.

**Üretim belirlenimci olmalı:** Aynı girdi her koşuda aynı adayları vermeli (ışın araması ya da sabit tohum). CSV'nin yanına
commit hash, model/adaptör sürümü ve kütüphane sürümleri yazılır.

### 2.3 Doğruluk

- **İlk-1 / ilk-5 / MRR:** Yalnızca **ilk denemede** (tam kısaltmayla, kelime açık yazılmadan) doğru cümlenin 1. sırada /
  ilk 5'te olduğu cümlelerin oranı (karar verildi, PR #20; `CaseResult.first_rank`).
- **Bulunma oranı:** Herhangi bir denemede bulunan cümlelerin oranı (CSV'de `bulunan`). Betimseldir; sonraki denemelerin
  maliyeti KSR'ye yansır.
- Geri kontrol (kısaltması uyuşmayan adayı atma) ve morfolojik filtre bütün koşullarda aynı uygulanır.

### 2.4 Kullanıcı testi ölçütleri (`study.py`)

- **`wpm`** = (karakter − 1) / saniye × 60 / 5. Karakter: noktalamasız hedefin boşluk dahil uzunluğu. Süre: ilk seçimden doğru
  seslendirmeye kadar (hedefi okuma süresi girmez). **[DOĞRULANACAK]** Kodda MacKenzie'ye atıf var; atıf yapmadan önce kaynak açılıp
  kontrol edilecek. "5 karakter = 1 kelime" uzlaşımı Türkçede de kullanılır, aksi hâlde İngilizce çalışmalarla karşılaştırılamaz;
  sınırlılık olarak yazılır.
- **Görev:** Kopyalama. Hedef cümle gösterilir; cümle ancak hedefle eşleşen seslendirmeyle biter (tam düzeltme koşulu).
  Düzeltme maliyeti böylece WPM'in içindedir.
- **`duzeltme`:** Sil + Geri seçimleri. **`yanlis_cikti`:** hedefle eşleşmeyen seslendirme.
- **Kalibrasyon hatası:** Kalibrasyon modeline **girmeyen** doğrulama noktalarında (ızgaraya denk gelmeyen 4–8 nokta) ölçülen
  ortalama açısal hata, derece. Kalibrasyonun kendi eğitim noktalarındaki hata kullanılmaz: o, modelin noktaları ezberleyip
  ezberlemediğini ölçer, gerçek hatayı değil.
  **[EKİPLE — Berkay, Yusuf]** `fit_calibration` şu an hatayı eğitim noktalarından hesaplıyor (Berkay'ın notu,
  `docs/oneri-canli-bakis-mesaji.md`). Dışlama kuralı (Bölüm 5) ancak `calibration_sample` mesajına `purpose: "fit" | "validate"`
  alanı eklenip `mean_error_deg` yalnızca doğrulama noktalarından hesaplandığında uygulanabilir. Kalibrasyon ekranı 14 Kasım'da
  yazılacağı için bu karar ondan önce verilmeli.
- **SUS:** `study.sus_score` (tek maddeler yanıt − 1, çift maddeler 5 − yanıt, × 2,5). Geçerlik çalışması yapılmış Türkçe sürüm
  kullanılır; kendi çevirimiz kullanılmaz. **[DOĞRULANACAK]** Sürüm ve kaynak 11 Kasım'da `data/study/` altına yazılacak.

---

## 3. Analiz planı

### 3.1 Genel

- α = 0,05, **çift yönlü**. (Tek yönlü testle 12 kişide gereken etki d ≈ 0,89'dan 0,77'ye iner; çift yönlü daha savunulabilir.)
- Her çalışmanın birincil hipotezi düzeltmesiz; ikinciller kendi ailesinde **Holm** düzeltmesiyle.
- Her testte etki büyüklüğü ve %95 güven aralığı raporlanır.

### 3.2 Çalışma A

Aynı cümleler bütün koşullarda kullanıldığı için karşılaştırmalar **eşleştirilmiş**tir. Veri ikili (doğru/yanlış) ya da sayım
olduğu için Shapiro-Wilk/t-testi kullanılmaz.

| Hipotez | Veri | Test | Etki büyüklüğü |
|---|---|---|---|
| H-A1 | Cümle başına toplam seçim, S4 vs S1 | Wilcoxon işaretli sıralar | Eşleştirilmiş sıra-iki serili korelasyon; medyan fark, bootstrap %95 GA |
| H-A2, H-A3, H-A4 | İlk denemede ilk-1 doğru/yanlış | Kesin McNemar | Oran farkı, %95 GA |

Bootstrap: cümleler üzerinden 10.000 yeniden örnekleme, sabit tohum. **Not:** `simulate.py` şu an koşul başına toplam satır yazıyor;
eşleştirilmiş test için **cümle başına** satırlar da (cümle kimliği, seçim, sıra) CSV'ye yazılmalı. **[EKİPLE — Taha]**

**Hangi küme:** Simülasyon şu an doğrulama kümesinde (291 cümle) ölçüyor. 15 Aralık sonuçları doğrulama kümesinden gelir. Kod ve model
dondurulduktan sonra (commit hash kaydedilir) ayrılmış test kümesi (295 cümle) **bir kez** çalıştırılır; rapordaki asıl sayılar odur.
**[EKİPLE — Taha]**

### 3.3 Çalışma B

`study.paired_comparison` ile: katılımcı × koşul ortalamaları alınır, **eşleştirilmiş farklar** üzerinde Shapiro-Wilk; p ≥ 0,05
ise eşleştirilmiş t-testi, değilse Wilcoxon işaretli sıralar. Etki büyüklüğü Cohen d_z. H-B1 için ek olarak B/A WPM oranının
geometrik ortalaması ve %95 GA.

- n = 12'de Shapiro-Wilk'in gücü düşüktür; prosedür teknik plandaki analiz planıyla uyumlu olduğu için korunur, sınırlılık olarak yazılır.
- **H-B2:** SUS puanları üzerinde 68'e karşı tek örneklem t-testi (normallik yoksa tek örneklem Wilcoxon). `study.py` şu an
  yalnızca "68 üstü yüzde"yi veriyor; bu test eklenecek.
- **H-B3:** `duzeltme` ortalamaları üzerinde `paired_comparison`.
- Holm düzeltmesi `study.py`'de yok; H-B2 ve H-B3'e uygulanacak.

### 3.4 Güç

Eşleştirilmiş t-testi, α = 0,05, çift yönlü, %80 güç için tespit edilebilecek en küçük etki (scipy ile hesaplandı):

| n | 15 | 12 | 10 | 4 (ekip içi pilot) |
|---|---|---|---|---|
| En küçük d_z | 0,78 | 0,89 | 1,00 | 2,13 |

Çalışma B yalnızca **büyük** etkileri yakalayabilir; bu baştan sınırlılık olarak yazılır. Çalışma 4 kişilik pilota inerse hipotez
testi yapılmaz; H-B1–H-B3 "test edilemedi" olarak raporlanır ve yalnızca betimsel sonuç verilir.

---

## 4. Deney tasarımı (`study/protocol.py`)

- **Koşullar:** A harf harf (aynı arayüz, aynı ızgara, dil modeli yok), B kısaltma + aday listesi (S1). Dwell süresi iki koşulda da
  **700 ms** (`DWELL_MS`), hedef boyutu, kamera ve çene desteği aynı.
- **Sıra:** Katılımcı kodundan çıkar: tek numara A→B, çift numara B→A. Deneyi yürüten seçmez. Dengeli olması için **katılımcı
  sayısı çift** tutulur (12 ya da 14).
- **Cümle setleri:** 1. blok hep 1. seti, 2. blok hep 2. seti alır; böylece her koşul katılımcıların yarısında bir seti görür.
  Her koşul 2 alıştırma cümlesiyle açılır, ardından 10 ölçülen cümle gelir.
- **Set dengesi (kontrol edildi):** 1. set 39 kelime / 248 karakter, 2. set 38 kelime / 249 karakter.
- **Sızıntı:** Deney cümleleri ve yakın biçimleri derlemde yok; `build_corpus` bunu her derlemede kontrol ediyor (PR #17).
  Test kümesinde de eğitimdeki bir cümlenin yakın biçimi bulunmaz (anlam grupları birlikte sabitlenir, PR #14).
- **Oturum:** 5 dk eğitim → kalibrasyon → blok 1 → 2 dk mola → yeniden kalibrasyon → blok 2 → anket + SUS. 35–40 dk.
- **Kod:** `sentences.json`'un özeti (`materials`) her kayda yazılır; katılımcılar arasında değişirse `check_sessions` uyarır.
  Bu dosya `onkayit-v1`'den sonra değiştirilmez.

---

## 5. Katılım ve dışlama kuralları (veri görülmeden önce yazıldı)

**Etik kurul:** Başvuru şu an askıda; gerekip gerekmediği danışmanla görüşülecek. Onay gerekirse **hiçbir katılımcı verisi
onaydan önce toplanmaz**; gerekmezse bu, danışmandan yazılı olarak alınıp rapora eklenir. Her iki durumda da aydınlatılmış onam
formu kullanılır. **[EKİPLE — danışman]**

**Katılım:** 18 yaş ve üzeri; anadili Türkçe; normal ya da düzeltilmiş görme; bilinen nörolojik ya da göz hareketi bozukluğu yok;
aydınlatılmış onam formunu imzalamış.

**Gözlük (karar, 8 Kasım):** Gözlüklü katılımcılar alınır; durum `katilimcilar.csv`'deki `gozluk_lens` sütununa yazılır ve
betimsel raporlanır. Gerekçe: dışlamak örneklemi daraltır. Gözlük camı yansımasının MediaPipe iris tespitini bozup bozmadığı
**[DOĞRULANACAK]**; ölçmedik.

**Kalibrasyon:** Doğrulama hatası eşiği aşarsa en fazla **2 kez** yeniden kalibrasyon yapılır. Üçüncüde de aşarsa katılımcı **her
iki koşuldan** dışlanır (denek içi tasarımda tek koşulda tutulamaz).

**Eşik (karar, 8 Kasım): 2,5°.** Gerekçe: ızgara ekran yüksekliğinin %62'sini 3 satıra bölüyor (`layout.ts`), yani bir
hedef ~223 px. 15,6" 1080p ekranda bu ~4,0 cm; 60 cm'de merkezden kenara ~1,9°. Plandaki 3° eşiğindeki katılımcının bakışı
ortalamada hedefin dışına düşer; ölçülen WPM sistemi değil kalibrasyonu yansıtır. Kesin ekran belli olunca bu sayı yeniden hesaplanır.
`study.py` dışlamayı şu an uygulamıyor; analizden önce eklenecek ya da elle uygulanıp gerekçesiyle raporlanacak.

**Diğer kurallar:**
- Teknik arıza (çökme, kamera kopması) nedeniyle bir blokta ölçülen cümlelerin yarısından fazlası tamamlanamazsa katılımcı dışlanır;
  arıza kayıtla belgelenir.
- Bir cümle **3 dakikada** bitmezse deneyi yürüten onu atlar (`skipped`). Atlananlar ortalamaya girmez, ayrı sayılır.
- Onamını geri çeken katılımcının verisi silinir.
- **Uç değer temizliği yapılmaz.** Yukarıdakiler dışında hiçbir veri çıkarılmaz. Dışlanan katılımcı sayısı ve nedenleri raporlanır.
- Katılımcılar `K01`, `K02`… kodlarıyla kaydedilir. Ekip provaları (fareyle 25 Kasım, kamerayla 8 Aralık) `P` kodlarıyla kaydedilir;
  `study.py` yalnızca `K` kodlarını okuduğu için analize girmez.

**Veri koruma:** Kamera görüntüsü ve 478 noktalı yüz ağı yazılmaz; yalnızca öznitelik vektörü, zaman damgaları, bakış tahminleri ve
seçim olayları kaydedilir. `data/sessions/` repoya girmez. Ad–kod eşleşmesi repoda değil, ayrı ve şifreli bir dosyada durur.
Tam yüz ağını (478 nokta) kaydeden `?olcum` sayfası yalnızca **ekip içi** göz takibi ölçümleri (17 Kasım raporu) içindir;
katılımcılarla kullanılmaz ve kayıtları repoya girmez.

---

## Değişiklik günlüğü

| Tarih | Bölüm | Değişiklik | Gerekçe | Veri görülmeden önce mi? |
|---|---|---|---|---|
| 2026-11-08 | 1.1, 5 | İlk taslak; birincil hipotez (H-A1), kalibrasyon eşiği (2,5°) ve gözlük kuralı kararlaştırıldı | — | Evet (veri yok) |
| 2026-11-11 | 0, 1.1, 2.1–2.4, 3.2, 4, 5 | PR #14–#20 sonrası güncelleme: S4'te 8 etiket ve Zemberek; bulunamayan cümlenin maliyeti; ilk-1 yalnızca ilk denemeden; bağlam alanı; sızıntı denetimi; küme boyutları. Kalibrasyon hatası doğrulama noktalarından tanımlandı; `?olcum` ekip içiyle sınırlandı. | Kodda verilen kararları ön kayda işlemek; Berkay'ın eğitim noktası hatası notu; etik kurul durumu (askıda) eklendi | Evet (simülasyonun yalnızca n-gram doğrulama sonuçları görüldü; model ve test sonuçları görülmedi) |
