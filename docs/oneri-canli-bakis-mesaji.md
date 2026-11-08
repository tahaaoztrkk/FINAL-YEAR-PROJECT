<!-- Berkay, Yusuf ile paylaştı — 8 Kasım 2026 -->

# Öneri: kamera modunda canlı bakış mesajı

Durum: **taslak, Kişi 1 (Berkay) → Kişi 3 (Yusuf)**. Karar verilince
`schemas/messages.py`, üretilen TypeScript tipleri ve `ws-protocol.md` aynı
PR'da güncellenir; yapılacaklar listesi bitince bu dosya silinir.

## Sorun

Bugünkü `gaze` mesajı ekran koordinatı taşır:

```json
{"type":"gaze","point":{"x":0.14,"y":0.46,"t":12.340,"confidence":1.0}}
```

Fare modunda bu doğru: imlecin yeri zaten ekran koordinatı. Kamera modunda
tarayıcının elinde ekran koordinatı yok, yalnızca 12 boyutlu öznitelik
vektörü var. Öznitelikten ekrana eşleyen model (`gaze/calibration.py`,
scikit-learn) sunucuda duruyor. Yani kamera modunda sunucuya **öznitelik**
gitmeli ve eşlemeyi sunucu yapmalı. `ws.py` şu an bunu yapmıyor:
`session.map_features` hiç çağrılmıyor.

## Seçenekler

**A. Yeni mesaj: `gaze_features` (önerilen)**

```json
{"type":"gaze_features","features":[0.48,0.52,0.47,0.51,0.31,0.30,0.01,-0.04,0.02,0.21,0.01,0.01],"t":12.340,"confidence":0.93}
```

Sunucu `map_features` → `process_gaze` yapar, geri kalan akış aynıdır:
`gaze`, `dwell_progress`, `selection` hiç değişmez. Fare yolu ve onun
testleri dokunulmadan kalır. Her mesajın tek anlamı vardır.

**B. Mevcut `gaze` mesajını genişletmek** — `point` ya da `features`,
ikisinden biri. Tek mesaj tipi kalır ama "tam olarak biri dolu olmalı"
denetimi gerekir ve fare yolunun şeması değişir. Kazanç yok.

**C. Eşlemeyi tarayıcıda yapmak** — ridge katsayılarını tarayıcıya
göndermek. Yerel ağda gidiş-dönüş zaten birkaç ms, mimari belgesindeki
"model sunucuda" kararını bozar. Şimdilik gerek yok.

## A için karar verilecek ayrıntılar

1. **Alanlar.** `features`: tam 12 sayı, sırası `FEATURE_NAMES`. `t`:
   `performance.now()/1000`, fare modundakiyle aynı saat. `confidence`:
   `features.py`'deki gibi göz açıklığından (kırpışta 0'a iner).
2. **Yüz bulunamayan kare.** Önerim: hiç gönderilmez. Kırpış gibi düşük
   güvenli kareler gönderilir, ama sunucu `confidence < 0.3` olanları
   eşlemeye sokmaz — yoksa her kırpışta imleç aşağı sıçrar ve dwell
   sıfırlanır.
3. **Kalibrasyondan önce.** İstemci `calibration_result.ok` gelmeden
   `gaze_features` göndermez. Sunucu yine de korur: model yoksa bir kez
   `error{code:"not_calibrated"}` döner, sonrakileri sessizce atar.
4. **Boyut denetimi.** `len(features) != 12` ise `error{code:"bad_features"}`.
   Eğitilmiş modeli sessizce bozan en olası hata budur.
5. **Hız.** Her kamera karesinde bir mesaj (~30 Hz), kuyruk yok — bugünkü
   `gaze` kuralıyla aynı.
6. **Kayıt.** Deney kaydında `gaze` olayına öznitelik vektörü de yazılsın
   (`loggable_features` zaten 12 sayıyı kabul ediyor). 17 Kasım'daki hata
   raporu ve sonradan farklı kalibrasyon modeli denemek bu olmadan
   yapılamaz. Görüntü yine kaydedilmez.
7. **Kaynağı kim seçer.** `App.tsx` şu an `kind: 'mouse'` sabit. Önerim:
   arayüz `ready.gaze_source` değerine göre kaynağı seçsin; tek ayar
   sunucunun `.env`'indeki `GAZE_SOURCE` olsun.

## Aynı sözleşmeye dokunan ikinci konu: doğrulama noktaları

17 Kasım hedefi "2° altı hata". `fit_calibration` şu an hatayı eğitim
örnekleriyle ölçüyor (kodda not olarak duruyor); bu ezberi ölçer, gerçek
hatayı değil. Önerim: `calibration_sample` mesajına
`purpose: "fit" | "validate"` alanı (varsayılan `fit`). Kalibrasyon ekranı
ızgaradan sonra ızgaraya denk gelmeyen 4–5 doğrulama noktası gösterir;
rapor yalnızca onlardan hesaplanır. Kalibrasyon ekranı 14 Kasım'da
yazılacağı için şimdi karar vermek iki kez değiştirmekten ucuz.

## Benim tarafımda hazır olan

- `?kamera` sayfası: kamera + MediaPipe tarayıcıda, kare süresi ölçümü,
  landmark kaydı indirme.
- `features/gaze/useFaceTracking.ts`: her karede 478 nokta ve zaman damgası
  veren kanca. Öznitelik hesabı (11 Kasım) bunun üstüne gelecek.

İlk ölçüm (Berkay'ın bilgisayarı, Chrome, 8 Kasım): GPU, 27 fps,
işleme süresi p50 14.7 ms / p95 17.1 ms (bütçe 33 ms), yüz bulunan kare %100.

## Yapılacaklar

### Yusuf ile birlikte karar verilecek

- [ ] Kamera modu için `gaze_features` mesajı (seçenek A) kabul mü?
- [ ] Düşük güvenli kare eşiği (öneri: `confidence < 0.3` eşlemeye girmez)
- [ ] Kalibrasyondan önce gelen örnek: `not_calibrated` hatası bir kez
- [ ] Deney kaydına öznitelik vektörü yazılsın mı?
- [ ] Arayüz bakış kaynağını `ready.gaze_source`'tan mı seçsin?
- [ ] `calibration_sample` için `purpose: "fit" | "validate"` alanı

### Berkay

- [x] 8 Kasım — MediaPipe tarayıcıda çalışıyor (`?kamera`)
- [ ] 8 Kasım — Canlı bakış mesajının içeriği Yusuf'la belli
- [ ] 11 Kasım — 12 öznitelik TypeScript'te; landmark kaydıyla Python'a
      karşı eşitlik testi
- [ ] 14 Kasım — Yusuf'un kalibrasyon ekranıyla ilk kalibrasyon, imleç
      kameradan geliyor
- [ ] 17 Kasım — 2° altı hata ölçümü ve raporu (gözlüklü / gözlüksüz ayrı)

### Yusuf

- [ ] Karar verilen mesajı `schemas/messages.py`'ye ekle, tipleri üret,
      `ws-protocol.md`'yi güncelle
- [ ] `ws.py`: `gaze_features` gelince `map_features` → `process_gaze`
- [ ] `App.tsx`: bakış kaynağını sabit `'mouse'` yerine ayardan al
- [ ] 14 Kasım'a kalibrasyon ekranı (ızgara + doğrulama noktaları)
