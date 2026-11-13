# Haftalık plan ve proje durumu — 13 Kasım 2026

Bu hafta bir yapılabilirlik haftası. Her parça "çalışıyor mu" sorusuna
ölçülebilir bir cevap verecek; 20 Kasım Cuma günü bu cevaplara bakılıp devam
kararı verilecek.

## 1. Özet

- **Dil tarafı en ileride.** Derlem ~2.900 cümleye çıktı, S4 Zemberek'le
  etiketleniyor, llama.cpp sağlayıcısı demo dizüstünde istek başına ~0,9 sn
  ile çalışıyor. Eksik: dört şemanın gerçek modelle tam simülasyonu ve ince
  ayar.
- **Göz takibi çalışıyor ama henüz klavye için yeterince isabetli değil.**
  Baş sabitken 1,8–3,3°, baş oynayınca eski modelle 14–18°. Baş pozlu
  kalibrasyonla bu farkın büyük kısmı kapanıyor (2,3–4,5°, tek kişi).
- **Gözle uçtan uca yazma henüz hiç yapılmadı.** Kamera, arayüze ve
  protokole bağlı değil.
- **En büyük takvim riski etik kurul.** Onay 4–8 hafta sürüyor; bugün
  gönderilse bile en erken 11 Aralık. Aralık'taki kullanıcı çalışması
  şimdiden risk altında.

## 2. Son durum: GitHub hareketleri (27 Ekim – 13 Kasım)

### main'e girenler (PR #4 – #20)

| Tarih | Alan | Ne oldu |
|---|---|---|
| 28 Ekim | Deney | Kullanıcı testi modu: oturum kaydı, A/B planı, analiz betiği (`?deney`, `study.py`) |
| 7 Kasım | Dil modeli | `hf_local` ayarlanabilir üretim ve istek başına gecikme ölçümü |
| 7 Kasım | Dil modeli | llama.cpp sağlayıcısı; ilk dizüstü ölçümü (aşağıda) |
| 7 Kasım | İnce ayar | İlk Colab ince ayar koşusu hazırlandı (`notebooks/qlora_colab.ipynb`, `nlp/finetune.py`) |
| 7 Kasım | Derlem | Test ve doğrulama cümleleri sabit kümelere kilitlendi; test/deney cümlesini kopyalayan derlem cümlesi derlemeyi durduruyor |
| 7–9 Kasım | Derlem | Altı kategoride cümle eklendi: 376 temel ihtiyaç, 265 sağlık, 212 pozisyon ve bakım, 631 duygu/soru/sosyal, 340 uzun cümle → toplam 2.907 |
| 9 Kasım | Derlem | Diyalog bağlamı eklendi (karşı tarafın önceki cümlesi) |
| 9 Kasım | Şemalar | S4 ekleri Zemberek ile etiketleniyor; 8 etiket, kelime başına çoklu seçim |
| 9 Kasım | Genişletici | Geri kontrol adayları elediğinde liste top_k'ya kadar yeniden dolduruluyor |
| 9 Kasım | Değerlendirme | Simülasyonda dürüst maliyet hesabı ve ilk-1 doğruluk |

Bugünkü main: 221 test (CLAUDE.md'de hâlâ 80 yazıyor), derlem 2.907 cümle
(295 test, 29 doğrulama, kalanı eğitim).

### main'e girmemiş dallar

| Dal | Kim | İçerik | Durum |
|---|---|---|---|
| `feat/gaze-kamera` | Berkay | MediaPipe tarayıcıda (`?kamera`), canlı bakış mesajı önerisi | PR yok, 8 Kasım'dan beri hareketsiz |
| `docs/hipotez-onkayit` | — | Ön kayıt: hipotezler, ölçüt tanımları, analiz planı (`docs/hipotezler.md`) | PR yok, 10 Kasım'da güncellendi |
| `claude/project-thread-vg7ejk` | Taha | Berkay'ın dalı + `?olcum` ölçüm sayfası + `?bakis` canlı bakış sayfası + bu plan | PR yok |

Üç dal da main'den ayrışıyor. Berkay'ın dalı PR #10'dan sonra açıldığı için
main'in son 20 commit'ini içermiyor.

## 3. Yapılabilirlik: şu an bildiklerimiz

### Göz takibi (10 Kasım, Taha'nın dizüstü bilgisayarı, gözlüksüz, 3 ölçüm)

- 30 fps, GPU, yüz her karede bulundu. Görüntüde göz ~18 px genişliğinde,
  iris yarıçapı ~4 px.
- Doğrulama noktalarında hata (görme açısı derecesi, 60 cm'de 1° ≈ 1 cm):

| Model | Baş sabit | Baş oynamış |
|---|---|---|
| Sunucudaki varsayılan (12 öznitelik, 2. derece) | 4,1–8,6° | ~18,5° |
| Baş öznitelikleri çıkarılmış, 1. derece | 1,8–3,3° | 5,1–13,6° |
| İris + açıklık + yaw/pitch, baş pozlu kalibrasyonla | — | 2,3–4,5° |

- 4×3 klavye tuşuna ham kare isabeti en iyi modelde %40–68. Asıl engel dikey
  hata: 1,5–2,7 cm, tuşun yarı yüksekliği 1,9 cm.
- Sunucudaki model baş özniteliklerini kalibrasyonda hiç değişmeden görüyor ve
  küçük bir baş hareketinde tahmini ekran dışına fırlatıyor.
- Kırpış: eski kontrol yalnızca göz tamamen kapanınca devreye giriyordu.
  `?bakis` sayfasında kalibrasyondan hesaplanan bir eşikle düzeltildi.
- Gözlük, birden fazla kişi ve gerçek dwell ile seçim henüz denenmedi.

### Dil modeli

- llama.cpp, RTX 5060 Laptop 8 GB, S1, 10 cümle: istek başına 907 ms, KSR
  %43,9, ilk-1 %90. Aynı model T4'te HuggingFace ile ~4.500 ms. GPU belleği
  6,5/8 GB.
- Bu 10 cümlelik bir ölçüm; S2–S4 ve geliştirme kümesinin tamamı gerçek
  modelle koşulmadı.
- İnce ayar hazır ama koşulup koşulmadığı repoda görünmüyor (`results/` boş).

### Uçtan uca

- Arayüz, dwell, dört şema, WebSocket, Türkçe TTS fareyle çalışıyor.
- Kamera arayüze bağlı değil; kalibrasyon ekranı yok; `gaze_features`
  mesajı yok.

## 4. Bu haftanın hedefi ve karar kapısı (20 Kasım Cuma)

| Parça | Soru | Bitti ölçütü |
|---|---|---|
| Göz takibi | İsabet yeterli mi? | 3 kişide (biri gözlüklü) 700 ms dwell ile 10 denemede en az 8 doğru tuş |
| Uçtan uca | Gözle tam bir cümle yazılabiliyor mu? | Kalibrasyondan sonra yalnızca gözle kısaltma → aday → seslendirme |
| Dil modeli | Gerçek model kısaltmayı açabiliyor mu? | En az bir şemada ilk-5 > %60, dizüstünde gecikme p95 < 2 sn |
| Deney | Deney yapılabilir mi? | Etik kurul başvurusu gönderildi, 1 kişilik pilot ölçüldü |

Sayılar başlangıç önerisidir, ekipçe pazartesi netleştirilmeli.

Karar: dört ölçüt tutarsa plan aynen devam eder. Biri tutmazsa o parça için
alternatife geçilir (bölüm 7).

## 5. Kişi bazında görevler

### Kişi 1 — Berkay (göz takibi)

**Soru:** İsabet klavye için yeterli mi?

1. Dalını main ile güncellemek (20 commit geride) ve PR açmak; `?kamera`
   main'e girsin.
2. `?olcum` ile en az 3 kişide ölçüm (biri gözlüklü). Analiz betiği Taha'da,
   repoya konacak.
3. `?bakis` ile her kişide 4×3 ızgarada 10 dwell denemesi; doğru tuş sayısı.
4. Sunucudaki modeli ölçümlere göre değiştirmek: baş öznitelikleri yalnızca
   kalibrasyonda baş pozu varsa, 1. derece. `FEATURE_NAMES` sırası değişmez,
   yalnızca modele verilen sütunlar seçilir.
5. 12 özniteliğin TypeScript'e taşınması: `gazeLinear.ts` ilk 8'ini Python'la
   birebir hesaplıyor (fark < 1e-13); kalan 4'ü (`head_roll`, `face_scale`,
   iki `iris_disparity`) eklenecek.

**Bitti:** Kişi başına derece cinsinden hata, tuş isabet oranı, gözlüklü ve
gözlüksüz ayrı. 17 Kasım'daki "2° altı" hedefi bu ölçümlere göre yeniden
konuşulur.

### Kişi 3 — Yusuf (arayüz ve sunucu)

**Soru:** Gözle tam bir cümle yazılabiliyor mu?

Bu hafta için kestirme (protokol değişmeden):

1. `?bakis`'teki tarayıcı içi eşlemeyi App'e bağlamak: tahmin edilen ekran
   koordinatı mevcut `gaze` mesajıyla gönderilir, sunucudaki yumuşatma ve
   dwell olduğu gibi çalışır.
2. Kalibrasyon ekranı: tam ekran, 9 nokta + doğrulama noktaları, baş pozlu
   turlar, kırpış filtresi. `GazeLive.tsx` örnek.
3. Kalibrasyon ve klavye aynı pencere boyutunda (tam ekran) olmalı.

Gelecek haftaya kalabilecek kalıcı yol (Berkay'la karar verildikten sonra):

4. `schemas/messages.py`: `gaze_features` (12 sayı, `t`, `confidence`),
   `calibration_sample.purpose` (`fit` / `validate`), `calibration_start`
   (şu an ikinci kalibrasyon eskisinin örneklerine ekleniyor; `reset_calibration()`
   hiç çağrılmıyor). `export_schema.py` içindeki `CLIENT_MODELS` listesi,
   üretilen tipler ve `ws-protocol.md` aynı PR'da.
5. `ws.py`: `gaze_features` → `map_features` → ortak `gaze` yolu;
   `not_calibrated` bir kez; hata yalnızca `validate` örneklerinden.
6. `App.tsx`: kaynak `ready.gaze_source`'tan.

**Bitti:** Kalibrasyondan sonra yalnızca gözle bir cümle söyletildi, ekran
kaydıyla.

### Kişi 2 — Taha (dil modeli, derlem, değerlendirme)

**Soru:** Gerçek model kısaltmayı açabiliyor mu, hangi şema daha iyi?

1. llama.cpp ile dört şemanın simülasyonu, geliştirme kümesinin tamamında,
   bağlamlı ve bağlamsız:
   `python -m gaze_aac.evaluation.simulate --providers llamacpp --schemes S1 S2 S3 S4`
2. Sonuçları `results/` altına yazıp main'e göndermek (şu an boş).
3. Colab ince ayar koşusunu başlatmak (H-A3 hipotezi buna bağlı).
4. Test kümesine dokunmamak; Ocak'a kadar kapalı.

**Bitti:** Her şema için ilk-1, ilk-5, KSR ve gecikme p50/p95 tablosu.

### Kişi 4 — Polat (deney ve rapor)

**Soru:** Deney yapılabilir mi, takvim tutuyor mu?

1. Etik kurul başvurusunu bu hafta göndermek. Görüntü diske yazılmıyor,
   yalnızca landmark ve zaman damgası kaydediliyor; başvurudaki madde kodla
   uyumlu.
2. `docs/hipotez-onkayit` dalını gözden geçirip PR'la main'e almak. Ön kayıt
   veriden önce kilitlenmeli.
3. Yusuf'un uçtan uca sürümüyle 1 kişilik pilot: harf harf yazma (A) ile
   kısaltma (B), `?deney` moduyla; dakikada kelime ve düzeltme sayısı.
4. CLAUDE.md'yi güncellemek (test sayısı, derlem boyutu, durum bölümü).

**Bitti:** Başvuru gönderildi, pilot ölçümü var, ön kayıt main'de.

## 6. Bağımlılıklar ve riskler

| Risk | Etki | Önlem |
|---|---|---|
| Etik kurul onayı 4–8 hafta | Aralık çalışması kayabilir | Bu hafta gönder; hızlandırılmış inceleme sor; yedek tarih Ocak başı |
| Dikey bakış hatası tuşun yarısına yakın | Yanlış tuş seçimi | Daha büyük tuşlar, 3×2 ızgara ya da yalnızca grup adımında durmak (T9 benzeri) |
| Baş hareketi | Kalibrasyon birkaç saniyede bozulur | Baş pozlu kalibrasyon, tek noktalı hızlı düzeltme, ekranda uyarı |
| Dallar main'den ayrışıyor | Birleştirme çatışmaları | Bu hafta üç dalın PR'ı |
| GPU belleği 6,5/8 GB | Demoda başka uygulama açıkken çökebilir | Demo bilgisayarında yalnızca sistem açık |
| Kalibrasyon şemasının sunucuda iki kez değişmesi | Kişi 1 ve 3 aynı kodda | Önce kestirme yol, protokol tek seferde |

## 7. Bundan sonraki haftalar

| Hafta | Hedef |
|---|---|
| 16–20 Kasım | Yapılabilirlik haftası (bölüm 4–5); Cuma karar toplantısı |
| 23–27 Kasım | Kalıcı protokol (`gaze_features`, kalibrasyon mesajları); ince ayarlı modelle simülasyon; 2–3 kişilik pilot |
| 30 Kasım – 4 Aralık | Simülasyon sonuçları kesinleşir (Çalışma A); rapor yöntem bölümü; deney materyalleri dondurulur |
| 7–18 Aralık | Etik onay geldiyse kullanıcı çalışması (Çalışma B); gelmediyse pilot genişletme ve rapor yazımı |
| 21 Aralık – 3 Ocak | Kullanıcı çalışması analizi ya da yedek tarihte çalışma |
| Ocak | Test kümesi açılır, nihai değerlendirme, rapor, demo, teslim |

Karar kapısına göre yedek yollar:

- **Göz isabeti yetersiz:** daha büyük hedefler ve daha az hücre; kalibrasyonu
  sık tazeleme; gerekirse göz takibini demo bileşeni olarak bırakıp
  araştırma sorusunu (şema karşılaştırması) çevrimdışı yanıtlamak. Araştırma
  sorusu prototipten bağımsız, bu yol her zaman açık.
- **Dil modeli yavaş ya da isabetsiz:** daha küçük model ya da n-gram
  sağlayıcısı; aday sayısını azaltmak; ince ayarın sonucunu beklemek.
- **Etik onay gecikirse:** Çalışma B Ocak başına, rapor buna göre.

## 8. Açık kararlar

- Canlı bakış mesajı (`gaze_features`, seçenek A) ve diğer beş protokol
  kararı — Berkay ve Yusuf.
- Bu haftanın bitti ölçütlerindeki eşikler — ekip, pazartesi.
- Tuş boyutu ve ızgara düzeni, göz ölçümlerinden sonra — Yusuf ve Berkay.
