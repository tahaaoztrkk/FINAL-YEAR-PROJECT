<!-- Berkay, Yusuf ile paylaştı — 8 Kasım 2026, 20 Kasım'da karar belgesine çevrildi -->

# Karar belgesi: canlı bakış protokolü, tuş boyutu ve ızgara

Durum: **Berkay (Kişi 1) ve Yusuf (Kişi 3) birlikte dolduracak.** Her kararda
öneri ve seçenekler var; "Karar" satırı toplantıda yazılır. Kararlar
kesinleşince `schemas/messages.py`, üretilen TypeScript tipleri ve
`ws-protocol.md` aynı PR'da güncellenir.

## 1. Bugünkü durum (20 Kasım)

- Kamera tarayıcıda çalışıyor (`?kamera`, #24). 12 öznitelik TypeScript'te
  ve Python'la birebir aynı (#26).
- `?bakis` tarayıcıda kalibre edip bakılan yeri gösteriyor; **D** ile 10
  denemelik dwell oturumu var (#26).
- Sunucudaki kalibrasyon modeli ölçümlere göre düzeltildi (#27): 1. derece,
  baş öznitelikleri yalnızca kalibrasyonda baş oynadıysa, kırpışlar eleniyor.
  `in_calibrated_pose()` başın kalibrasyon aralığında olup olmadığını söylüyor.
- **Eksik:** kamera arayüze bağlı değil. `ws.py` öznitelik almıyor
  (`session.map_features` hiç çağrılmıyor). `App.tsx` kaynağı `'mouse'`
  olarak sabit tutuyor. Kalibrasyon ekranı yok.

## 2. Protokol kararları

### K1. Kamera modu arayüze nasıl bağlanacak?

Tarayıcıda yalnızca öznitelik var; öznitelikten ekrana eşleyen bir model
gerekiyor.

| Seçenek | Ne yapılır | Artı | Eksi |
|---|---|---|---|
| **a. Kestirme** | `?bakis`'teki tarayıcı içi model App'e taşınır, tahmin mevcut `gaze` mesajıyla gider | Protokol değişmez; en hızlı uçtan uca | Model iki yerde (tarayıcı ve sunucu); deney kaydına öznitelik girmez |
| **b. Kalıcı: `gaze_features`** | Tarayıcı 12 sayı gönderir, eşlemeyi sunucu yapar | Tek model (#27), kayıtta öznitelik, mimariye uygun | Şema, ws ve kalibrasyon ekranı birlikte değişir |
| c. Mevcut `gaze`'i genişletmek | `point` ya da `features` | Tek mesaj tipi | "Tam olarak biri dolu" denetimi; fare yolu değişir |

**Öneri:** Bu hafta (a) ile gözle uçtan uca bir cümle yazılsın. Gelecek
hafta (b)'ye geçilsin. (c) yapılmasın.

Önerilen mesaj (b için):

```json
{"type":"gaze_features","features":[0.48,0.52,0.47,0.51,0.31,0.30,0.01,-0.04,0.02,0.21,0.01,0.01],"t":12.340,"confidence":0.93}
```

Sunucu `map_features` → `process_gaze` yapar. `gaze`, `dwell_progress` ve
`selection` hiç değişmez.

**Karar:** ______________________

### K2. `gaze_features` ayrıntıları (K1-b seçilirse)

| # | Konu | Öneri |
|---|---|---|
| 2a | Alanlar | `features`: tam 12 sayı, `FEATURE_NAMES` sırası (model sütun seçer, istemci hep 12 gönderir). `t`: `performance.now()/1000`. `confidence`: göz açıklığından |
| 2b | Yüz yokken | Mesaj gönderilmez |
| 2c | Kırpış | Gönderilir. Sunucu `confidence < 0.3` olanı eşlemeye sokmaz, imleci yerinde tutar, dwell sıfırlanmaz |
| 2d | Kalibrasyondan önce | İstemci göndermez. Gelirse sunucu bir kez `error{code:"not_calibrated"}` döner, sonrakileri atar |
| 2e | Yanlış boy | `error{code:"bad_features"}` (model 12 değilse zaten hata veriyor) |
| 2f | Hız | Kare başına bir mesaj (~30 Hz), kuyruk yok |
| 2g | Kayıt | Deney kaydındaki `gaze` olayına öznitelik vektörü de yazılsın; görüntü yine yazılmaz |

**Karar:** ______________________

### K3. Baş kalibrasyon aralığının dışına çıkınca

`?bakis`'te imleç donuyor ve "başın uzaklaştı" yazıyor. Sunucuda
`in_calibrated_pose()` hazır. **Öneri:** sunucu `gaze` mesajına isteğe bağlı
`hold: "head" | "blink" | null` alanı eklesin. Arayüz imleci soluklaştırıp
nedeni yazar, dwell ilerlemez. Kullanıcıya "ortadaki noktaya bak" ile tek
noktalı düzeltme önerilir (`?bakis`'teki Boşluk).

**Karar:** ______________________

### K4. Kalibrasyon mesajları

| # | Konu | Öneri |
|---|---|---|
| 4a | Doğrulama noktaları | `calibration_sample.purpose: "fit" \| "validate"` (varsayılan `fit`). Rapordaki hata yalnızca `validate` örneklerinden. Bugün hata eğitim örnekleriyle ölçülüyor, bu ezberi ölçer |
| 4b | Yeniden kalibrasyon | `calibration_start` mesajı: sunucu eski örnekleri siler (`reset_calibration()` bugün hiç çağrılmıyor; ikinci kalibrasyon eskisinin üstüne ekleniyor) |
| 4c | Baş pozlu turlar | Kalibrasyon ekranı `?bakis` gibi: 9 nokta baş sabit + 4 baş pozunda (sağ, sol, yukarı, aşağı) 5'er nokta. Turlar olmazsa sunucu baş özniteliklerini kullanmaz, model yine çalışır ama baş oynayınca hata büyür |
| 4d | Ekran | Kalibrasyon ve klavye aynı pencere boyutunda (tam ekran) |

**Karar:** ______________________

### K5. Bakış kaynağını kim seçer?

**Öneri:** Arayüz `ready.gaze_source` değerine göre seçsin. Tek ayar
sunucunun `.env`'indeki `GAZE_SOURCE` olsun. `App.tsx` bugün `'mouse'`
olarak sabit.

**Karar:** ______________________

## 3. Tuş boyutu ve ızgara (ölçüm sonuçlarına göre)

Ölçüm: `docs/olcum-yonergesi-goz.md`. İki girdi var:

- `?bakis` dwell denemesi: kişi başına 10 denemede doğru sayısı (4×3).
- Analiz raporundaki "Tuş boyutu" tablosu: aynı hatalarla 4×3, 3×3, 3×2 ve
  2×2 düzenlerinde isabet, baş sabit ve baş oynamış ayrı.

**Karar kuralı (öneri):**

1. Her kişide 4×3'te `?bakis` ≥ 8/10 ise **4×3 kalır**.
2. Değilse: raporda **baş oynamış** ortalama isabeti ≥ %80 olan en çok
   hücreli düzen seçilir. O düzende `?bakis` yeniden koşulur
   (`?bakis&izgara=3x2` gibi) ve herkes ≥ 8/10 ise karar verilir.
3. 2×2 de tutmazsa göz takibi yalnızca grup adımında kullanılır (T9 benzeri:
   önce grup, sonra grup içi seçim) ya da plan bölüm 7'deki yedek yola geçilir.

Seçilen düzenin şemalara etkisi (S1–S4'te tuş sayısı, grup adımı) Yusuf'un
kararı.

| Ölçüm | Değer |
|---|---|
| `?bakis` 4×3, kişi başına doğru / 10 | |
| Rapor: baş oynamış ortalama isabet (4×3 / 3×3 / 3×2 / 2×2) | |
| Seçilen düzen ve tuş boyutu (cm) | |

**Karar:** ______________________

## 4. Kim ne yapacak

### Berkay

- [x] MediaPipe tarayıcıda (`?kamera`)
- [x] 12 öznitelik TypeScript'te, Python'la eşitlik testi (#26)
- [x] Sunucu modeli: 1. derece, koşullu baş pozu, kırpış filtresi (#27)
- [x] `?bakis` dwell denemesi ve `?olcum` analiz betiği (#26, #27)
- [ ] 3 kişilik ölçüm (biri gözlüklü, 60 cm, tam ekran); özet sayılar
- [ ] K1–K5 ve tuş boyutu kararı Yusuf'la

### Yusuf

- [ ] K1-a: `?bakis` eşlemesini App'e bağlamak, `gaze` ile göndermek
- [ ] Kalibrasyon ekranı (K4: 9 nokta + baş pozlu turlar + doğrulama noktaları, tam ekran)
- [ ] K1-b ve K2–K5: şema, `export_schema.py`'deki `CLIENT_MODELS`, üretilen tipler, `ws-protocol.md`, `ws.py`, `App.tsx` (gelecek hafta)
- [ ] Seçilen ızgaraya göre klavye düzeni
