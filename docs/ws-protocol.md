# WebSocket protokolü

Bu belge, arayüz ile servis arasındaki sözleşmenin okunabilir halidir.
Bağlayıcı tanım `backend/src/gaze_aac/schemas/messages.py` dosyasındadır;
burası ile orası çelişirse kod doğrudur.

Sözleşmeyi değiştiren kişi aynı PR içinde üç şeyi birden yapar: modeli
değiştirir, `python backend/scripts/export_schema.py` ile TypeScript
tiplerini yeniden üretir, bu belgeyi günceller.

## Bağlantı

```
ws://127.0.0.1:8000/ws
```

Geliştirmede Vite vekili üzerinden `ws://localhost:5173/ws` de çalışır.

Her bağlantı bir oturumdur. Oturum kalibrasyon modelini, yumuşatıcıyı ve
dwell sayacını taşır; bağlantı koptuğunda bunlar kaybolur ve kullanıcı
yeniden kalibre etmek zorunda kalır. Bu yüzden istemci üstel geri çekilmeyle
otomatik yeniden bağlanır.

## Akış

```
istemci                          sunucu
   |                                |
   |------------ hello ------------>|
   |<----------- ready -------------|
   |                                |
   |----------- targets ----------->|   (düzen her değiştiğinde)
   |                                |
   |------------ gaze ------------->|   ~30 Hz
   |<----------- gaze --------------|   yumuşatılmış konum
   |<------- dwell_progress --------|   hedef üstündeyken
   |<--------- selection -----------|   dwell tamamlandığında
   |                                |
   |----------- expand ------------>|
   |<--------- candidates ----------|
   |                                |
   |------------ speak ------------>|   (ölçüm kaydı)
```

## İstemci mesajları

| type | Ne zaman | Alanlar |
| --- | --- | --- |
| `hello` | Bağlantı açılır açılmaz | `screen_width`, `screen_height`, `participant_id?` |
| `targets` | Ekran düzeni her değiştiğinde | `targets[]` |
| `gaze` | Kare hızında, ~30 Hz | `point{x, y, t, confidence}` |
| `select` | Fare/düğme ile doğrudan seçim | `target_id` |
| `calibration_sample` | Kalibrasyon sırasında her örnekte | `target_x`, `target_y`, `features[]` |
| `calibration_fit` | Örnek toplama bitince | — |
| `expand` | Kullanıcı "Tamamla" seçince | `abbreviation`, `scheme`, `context?`, `top_k` |
| `speak` | Aday seçilip seslendirilince | `text` |

Koordinatlar 0–1 arasında normalizedir. Piksel dönüşümünü arayüz yapar;
böylece farklı çözünürlükler arasında taşınabilir kalır.

## Sunucu mesajları

| type | Ne zaman | Alanlar |
| --- | --- | --- |
| `ready` | `hello` sonrası | `session_id`, `gaze_source`, `expander_provider`, `dwell_ms` |
| `gaze` | Her bakış örneğine karşılık | `x`, `y`, `t` |
| `dwell_progress` | Bakış bir hedefin üstündeyken | `target_id`, `progress` (0–1) |
| `selection` | Dwell eşiği aşılınca | `target_id`, `dwell_ms` |
| `calibration_result` | `calibration_fit` sonrası | `ok`, `sample_count`, `mean_error_px?`, `mean_error_deg?`, `message?` |
| `candidates` | `expand` sonrası | `abbreviation`, `scheme`, `candidates[]`, `latency_ms` |
| `error` | Mesaj doğrulanamazsa | `code`, `detail` |

## Kurallar

**Bozuk mesaj bağlantıyı kapatmaz.** Sunucu `error` döner ve dinlemeye devam
eder. Kullanıcı kalibrasyonunu kaybederse baştan başlamak zorunda kalır;
tek bir biçim hatası buna değmez.

**Hedef listesi tek doğruluk kaynağıdır.** Arayüz neyi çiziyorsa onu
`targets` olarak göndermelidir. İki liste ayrışırsa kullanıcı bir yere bakar,
başka yer seçilir — ve bu hata ekranda görünmediği için saatlerce fark
edilmez.

**Bakış örnekleri kuyruğa alınmaz.** Bağlantı kapalıyken gönderilen `gaze`
mesajları atılır; biriken eski örnekler yeniden bağlanınca anlamsız bir
imleç sıçramasına yol açar. Diğer mesajlar kuyruğa alınır.

**Adaylar geri kontrolden geçer.** Sunucu, üretilen her cümlenin kısaltmasını
yeniden hesaplar ve girdiyle karşılaştırır. Eşleşmeyenler `valid: false`
işaretlenir; arayüz bunları göstermez ama değerlendirme için kayıtta kalırlar.

## Örnek oturum

```json
→ {"type":"hello","screen_width":1920,"screen_height":1080}
← {"type":"ready","session_id":"a3f9c2","gaze_source":"mouse",
   "expander_provider":"mock","dwell_ms":700}

→ {"type":"targets","targets":[
     {"id":"group:0","x":0.03,"y":0.37,"width":0.22,"height":0.19,
      "label":"a b c ç","kind":"group"}]}

→ {"type":"gaze","point":{"x":0.14,"y":0.46,"t":12.340,"confidence":1.0}}
← {"type":"gaze","x":0.139,"y":0.461,"t":12.340}
← {"type":"dwell_progress","target_id":"group:0","progress":0.34}
← {"type":"selection","target_id":"group:0","dwell_ms":712.4}

→ {"type":"expand","abbreviation":"s i","scheme":"S1","context":null,"top_k":5}
← {"type":"candidates","abbreviation":"s i","scheme":"S1","latency_ms":2.1,
   "candidates":[{"text":"Su istiyorum.","score":1.0,"valid":true}]}
```
