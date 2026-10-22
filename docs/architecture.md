# Mimari

Sistem dört katmandan oluşur ve katmanlar birbirini yalnızca tanımlı
arayüzlerden görür. Bunun pratik karşılığı şu: Kişi 1 göz takibini
yazarken Kişi 3 arayüzü yazabilir, kimse diğerini beklemez.

```
                    ┌───────────────────────────────────┐
  kamera / fare ──► │  frontend/  React + TypeScript    │
                    │  klavye · dwell halkası · TTS     │
                    └────────────┬──────────────────────┘
                                 │  WebSocket (schemas/messages.py)
                    ┌────────────▼──────────────────────┐
                    │  api/   FastAPI · oturum yönetimi │
                    └───┬──────────────────────┬────────┘
                        │                      │
             ┌──────────▼────────┐   ┌─────────▼──────────┐
             │  gaze/            │   │  nlp/              │
             │  landmark         │   │  şemalar (S1–S4)   │
             │  öznitelik        │   │  genişletici       │
             │  kalibrasyon      │   │  sağlayıcılar      │
             │  filtre · dwell   │   │  istemler          │
             └───────────────────┘   └─────────┬──────────┘
                                               │
                              ┌────────────────▼─────────┐
                              │  data/ · evaluation/     │
                              │  derlem · simülasyon     │
                              └──────────────────────────┘
```

## Katmanlar

### `gaze/` — bakış hattı

Kameradan ekran koordinatına giden yol. Her adım ayrı modül:

- `landmarks.py` — MediaPipe sarmalayıcısı. MediaPipe ağır bir bağımlılık
  olduğu için import işlev içinde yapılır; testler ve simülasyon bu paket
  kurulu olmadan çalışır.
- `features.py` — 478 landmark'tan 12 boyutlu öznitelik vektörü.
- `calibration.py` — öznitelikten ekran koordinatına polinom ridge regresyon.
- `filters.py` — One Euro filtresi ile yumuşatma.
- `dwell.py` — bakışla seçim, tolerans ve bekleme süresi.

### `nlp/` — kısaltma genişletme

- `schemes.py` — dört kısaltma şeması. Projenin araştırma sorusu burada.
- `expander.py` — sağlayıcı arayüzü, geri kontrol, süre ölçümü.
- `providers/` — mock, n-gram, yerel HF modeli, API modeli.
- `prompts.py` — istem şablonları. Eğitim ve çıkarım aynı biçimi kullanır.

### `api/` — servis

- `ws.py` — WebSocket uç noktası, mesaj yönlendirme.
- `session.py` — oturum durumu. İş mantığı içermez, yalnızca bağlar.
- `routes/` — HTTP uç noktaları (sağlık, şema listesi, elle genişletme).

### `evaluation/` — ölçüm

- `metrics.py` — KSR, ilk-k doğruluk, MRR. Tanımlar raporda aynen kullanılır.
- `simulate.py` — çevrimdışı simülasyon. 24 koşul, tek CSV.

## Öznitelik vektörü

Sıra sözleşmedir: değişirse eğitilmiş kalibrasyon modelleri geçersizleşir.

| # | Ad | Açıklama |
| --- | --- | --- |
| 0–1 | `left_iris_rel_x/y` | Sol iris merkezinin göz kutusu içindeki konumu |
| 2–3 | `right_iris_rel_x/y` | Sağ iris için aynısı |
| 4–5 | `left/right_eye_openness` | Göz açıklığı / göz genişliği |
| 6–8 | `head_yaw/pitch/roll` | Kaba baş pozu |
| 9 | `face_scale` | Yüz genişliği — mesafe göstergesi |
| 10–11 | `iris_disparity_x/y` | İki göz arasındaki fark — derinlik ipucu |

Ham piksel koordinatı kullanılmaz. Kullanıcı başını 10 cm sağa kaydırdığında
tüm koordinatlar değişir ama bakış yönü aynı kalır; göreli konum ve yüz
genişliğine bölme bunu ortadan kaldırır.

## Neden bu teknik seçimler

**Kalibrasyonda derin ağ değil regresyon.** Kalibrasyon verisi 9 nokta ×
~30 kare = 270 örnek. Bu veriyle derin ağ ezberler. İkinci derece polinom
açılımı, kameranın doğrusal olmayan davranışını yakalayacak kadar esnek,
ezberlemeyecek kadar kısıtlı.

**Dwell'de tolerans süresi.** Bakış tahmininin doğal titremesi hedefin
kenarında dolaşır. İlerleme her sapmada sıfırlanırsa seçim hiç tamamlanmaz.
150 ms'lik tolerans bunu çözer.

**Seçimden sonra bekleme süresi.** Kullanıcının bakışını çekmesi zaman alır;
bu sürede ikinci seçim tetiklenirse kullanıcı aynı tuşa iki kez basmış olur.

**Tek model, dört şema.** Şema etiketi istemin içinde. Dört ayrı model
eğitmek hem dört kat pahalı hem de karşılaştırmayı adaletsiz kılar; aynı
ağırlıklar üstünde ölçmek daha temiz bir sonuç verir.

**Geri kontrol adımı.** Model Türkçede kolayca "yakın ama yanlış" cümle
üretir ("su istiyorum" yerine "su içmek istiyorum"). Üretilen cümlenin
kısaltmasını yeniden hesaplayıp karşılaştırmak, birkaç satırla doğruluğu
belirgin artırır.

**Sunucuda oturum durumu.** Kalibrasyon modeli bir scikit-learn nesnesidir,
tarayıcıya taşınamaz. Bu, çok süreçli dağıtımı zorlaştırır — ama bu projenin
kapsamında tek süreç yeterli.

## Gecikme bütçesi

| Adım | Hedef |
| --- | --- |
| Kare işleme (landmark + öznitelik) | < 33 ms |
| Yumuşatma gecikmesi | < 100 ms |
| Dwell süresi | 500–1200 ms (ayarlanabilir) |
| İlk 5 adayın dönmesi | < 1000 ms |

1 saniyeyi aşan model yanıtı kullanıcıyı bekletir ve WPM ölçümünü bozar.
Bu yüzden adaylar, kullanıcı hâlâ bakarken önceden üretilmeye başlanır.

## Gizlilik

Yüz görüntüsü diske hiç yazılmaz. Kamera karesi bellekte işlenir ve atılır;
yalnızca landmark koordinatları, zaman damgaları ve bakış tahminleri
kaydedilir. Bu, etik kurul başvurusunda açıkça belirtilir — onay süresini
kısaltır.
