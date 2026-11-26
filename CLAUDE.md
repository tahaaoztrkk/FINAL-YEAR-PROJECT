# CLAUDE.md

Bu dosya, bu repoda çalışan Claude (ve diğer kod asistanları) için yazıldı.
Kullanıcı belgeleri `README.md` ve `docs/` altındadır; burası kodun bugünkü
haliyle nasıl birbirine bağlandığını ve neye dokunurken dikkat edileceğini
özetler. Kod ile bu dosya çelişirse kod doğrudur; bu dosyayı düzeltin.

## Proje ne yapıyor

Konuşma ve hareket yeteneğini kaybetmiş kullanıcılar için göz takibiyle
Türkçe iletişim (AAC) sistemi. Kullanıcı bakışıyla kısaltma girer (`s i`),
dil modeli aday cümleler üretir ("Su istiyorum."), kullanıcı birini seçer ve
cümle tarayıcıda seslendirilir.

Araştırma sorusu: Türkçe eklemeli bir dil olduğu için baş harf kısaltması
İngilizcedeki kadar bilgi taşımaz. Dört kısaltma şeması (S1–S4) ve sağlayıcılar
(n-gram, sıfır atış LLM, QLoRA ince ayarlı LLM) çevrimdışı simülasyonla ve
A/B kullanıcı testiyle karşılaştırılır. Ön kayıtlı hipotezler
`docs/hipotezler.md` içindedir.

## Dizin haritası

```
backend/src/gaze_aac/
  main.py            FastAPI fabrikası; açılışta sağlayıcıyı bir kez kurar (app.state.expansion)
  config.py          Bütün ayarlar (pydantic-settings, backend/.env); veri yolları da burada
  api/
    ws.py            /ws WebSocket: mesaj yönlendirme + kullanıcı testi kaydı
    session.py       Bağlantı başına durum (kalibrasyon, filtre, dwell); iş mantığı içermez
    routes/          HTTP: GET /health, GET /schemes, POST /expand, POST /expand/abbreviate
  schemas/           Pydantic sözleşmeleri: messages.py (WS, tek doğruluk kaynağı), expansion, gaze, study
  gaze/              landmarks (MediaPipe, tembel import), features (12 boyut), calibration
                     (GazeMapper: StandardScaler + Ridge, 1. derece), filters (One Euro), dwell
  nlp/
    schemes.py       S1–S4 şemaları, Türkçe küçük harf, kısaltma kanonikleştirme
    morphology.py    Zemberek ile S4 ek etiketleri (NEG PAST FUT PROG Q 1S 2S PLUR)
    expander.py      ExpansionService: sağlayıcı çağrısı, geri kontrol, ek istek, süre ölçümü
    prompts.py       İstem şablonu; eğitim ve çıkarım AYNI fonksiyonu kullanır
    providers/       mock, ngram, hf_local (transformers+peft), llamacpp (llama-server /completion),
                     openai_compatible
    finetune.py      QLoRA eğitimi (Unsloth ya da PEFT), --dry-run sızıntı denetimi
  data/              corpus.py (derlem, grup bazlı bölme, eğitim çiftleri), build_corpus.py (CLI)
  evaluation/        metrics (KSR, ilk-k, MRR, WPM), simulate (şema × sağlayıcı × bağlam),
                     study (kullanıcı testi ayrıntısı), study_descriptive (rapordaki betimsel tablo:
                     katılımcı başına A/B, 180 sn duyarlılık), gaze_accuracy (?olcum kayıtlarından derece hatası)
  study/             protocol.py (katılımcı kodundan A/B sırası ve plan), recorder.py (JSONL oturum kaydı)
backend/scripts/     export_schema.py, export_feature_fixture.py, download_model.py
backend/tests/       pytest (Zemberek'i yüklediği için ~1,5 dk sürer)

frontend/src/
  main.tsx           URL'e göre sayfa seçer: varsayılan App, ?bakis GazeLive, ?olcum GazeMeasure, ?kamera CameraCheck
  App.tsx            Uygulama kabuğu; bütün durum burada (klavye modu, kısaltma, şema, deney)
  hooks/             useGazeSession (WS durumu), useGazeSource (fare ya da kamera; kamera kontrollerini döndürür)
  lib/               ws.ts (yeniden bağlanan GazeSocket), speech.ts (Web Speech API, tr-TR)
  components/        TargetTile, CandidateList, StatusBar, StudyPanel, GazeCursor,
                     CalibrationScreen (kamera modunda kalibrasyon + GazeHoldBanner)
  features/keyboard/ layout.ts: 12 hücrelik ızgara, iki adımlı harf seçimi (grup → harf), S4 etiket satırı
  features/study/    useStudy (plan akışı), normalize.ts (sunucudaki normalize_sentence'ın eşi)
  features/gaze/     Tarayıcıda MediaPipe: camera, landmarker, useFaceTracking, features.ts
                     (features.py'nin birebir eşi), gazeLinear.ts + dwellTrial.ts (?bakis denemesi),
                     browserGaze.ts + useWebcamGaze.ts (ana uygulamanın tarayıcı içi bakış modeli)
  types/             messages.generated.ts (ÜRETİLİR, elle düzenlenmez), messages.ts

data/corpus/aac_sentences.jsonl   Elle derlenen ~2.900 cümle, 6 kategori (repoda)
data/study/                       Kullanıcı testi cümleleri (sentences.json) ve anket şablonları
data/processed/, data/sessions/, models/, results/*   Repoya girmez (.gitignore)
docs/                             architecture, setup, ws-protocol (+ ws-schema.json), hipotezler, yönergeler
notebooks/qlora_colab.ipynb       Colab'da ince ayar ve GGUF dışa aktarma
report/                           LaTeX rapor (İngilizce; tek kaynak burası, PR'la yazılır; PDF CI'da derlenir)
```

## Veri akışı

**Ana uygulama, fare modu (`GAZE_SOURCE=mouse`, varsayılan).** `useGazeSource` fare konumunu
30 Hz'de normalize koordinat olarak `gaze_sample` mesajıyla yollar. Sunucuda
`GazeSession.process_gaze` One Euro filtresinden geçirir, `DwellDetector`
arayüzün bildirdiği hedeflere (`targets`) göre dwell ilerlemesi ve seçim
üretir; sunucu `gaze`, `dwell_progress`, `selection` döner. Tıklama `select`
ile aynı yoldan geçer. Kullanıcı "Tamamla"yı seçince `expand` gider,
`ExpansionService` sağlayıcıdan aday alır, her adayın kısaltmasını yeniden
hesaplayıp girilenle karşılaştırır (geri kontrol), `top_k`'dan az geçerli
aday kalırsa `EXPANDER_MAX_REFILLS` kadar yeniden ister ve `candidates` döner.
Seslendirme tarayıcıda yapılır; `speak` mesajı yalnızca kayıt içindir.

**Ana uygulama, kamera modu (`GAZE_SOURCE=webcam`; K1-a, kestirme yol).**
App kaynağı `ready.gaze_source`'tan seçer (K5); sunucu bu ayarı yalnızca
bildirir. MediaPipe FaceLandmarker tarayıcıda koşar (`features/gaze/`),
`irisFeatures` (12 özniteliğin ilk 8'i + göz başına x·y çarpımı) çıkar.
`useWebcamGaze` tam ekran kalibrasyonu yürütür (9 nokta baş sabit + 4 baş
pozunda 5'er nokta), `browserGaze.ts` modeli kurar (StandardScaler + Ridge,
köşe düzeltmesi, kırpış kapısı, baş aralığı, iki noktalı ortalama) ve
tahmin edilen nokta mevcut `gaze` mesajıyla gider. Protokol değişmedi;
yumuşatma yalnızca sunucuda yapılır (tarayıcıda ikinci kez yapılmaz).
Kırpışta, yüz yokken, baş aralık dışındayken ya da pencere boyutu
kalibrasyondakinden farklıyken örnek gönderilmez ve neden ekrana yazılır.
Kısayollar: Boşluk ortala, K yeniden kalibre et, Esc kalibrasyonu bırak.
`browserGaze.ts`'deki sayılar ve kurallar `?bakis` (`GazeLive.tsx`) ile aynı
tutulur; biri değişirse diğeri gözden geçirilir.

Eksikler: doğrulama noktaları ve derece cinsinden hata yok; kalibrasyon
tarayıcı belleğinde olduğu için `?deney`'e geçiş (sayfa yenilenir) onu siler.
Kalıcı yol (K1-b) `gaze_features` mesajı ve sunucudaki `GazeMapper`
(`calibration_sample` / `calibration_fit` hazır) ile olacak; karar
`docs/oneri-canli-bakis-mesaji.md` içinde bekliyor. `?bakis` sayfası
sunucusuz, kendi doğrusal modeliyle çalışan bir deneme aracı olarak durur.

**Kullanıcı testi (`?deney`).** `study_start` → sunucu katılımcı kodundan
(K01, K02…; tek AB, çift BA) planı kurar ve `study_plan` döner →
arayüz her cümle için `trial_start` / `trial_end` yollar. Her olay
`data/sessions/<kod>/<tarih-saat>_<oturum>.jsonl` dosyasına satır tamponlu
yazılır. Kullanıcı testi 4 kişilik ekiple yapıldığı için rapordaki analiz
betimseldir: `python -m gaze_aac.evaluation.study_descriptive --survey <anket.csv>`
(ön kayıt Bölüm 3.3). `gaze_aac.evaluation.study` cümle ayrıntısını ve p
değerlerini üretir; o p değerleri rapora konmaz.

**Model hattı.** `aac_sentences.jsonl` → `build_corpus` (tekrar ayıklama,
grup bazlı %80/%10/%10 bölme, `split` alanı dolu cümleler o kümede sabit) →
`data/processed/{train,val,test,training_pairs}.jsonl` → `finetune` (Colab) →
adaptör → `hf_local` ya da GGUF'a çevrilip `llamacpp` (demo bilgisayarı,
`llama-server --parallel 5`).

## Çalıştırma ve test

Backend (`backend/` içinden, sanal ortam etkin):

```bash
pip install -e ".[dev]"            # [gaze] MediaPipe/OpenCV, [llm] torch/transformers/peft
cp .env.example .env               # Windows: copy
uvicorn gaze_aac.main:app --reload --port 8010
pytest                             # ~311 test
ruff check src tests && ruff format src tests
mypy src                           # strict
python -m gaze_aac.data.build_corpus
python -m gaze_aac.evaluation.simulate --providers mock ngram --schemes S1 S2 S3 S4
python scripts/export_schema.py    # messages.py değişince
```

Frontend (`frontend/` içinden):

```bash
cp .env.example .env
npm install
npm run dev          # http://127.0.0.1:5173, Vite /ws'i BACKEND_PORT'a (8010) vekiller
npm test             # vitest: features.ts == features.py, dwellTrial
npm run typecheck && npm run lint
```

Varsayılan kurulum hiçbir model indirmez: `GAZE_SOURCE=mouse`,
`EXPANDER_PROVIDER=mock`. Port 8010'dur çünkü Windows'ta 8000 sık sık
rezerve edilir. Ayrıntılı kurulum, ince ayar ve llama.cpp adımları
`docs/setup.md` içindedir.

## Bozulmaması gereken sözleşmeler

- **WS mesajları:** tek tanım `schemas/messages.py`. Değiştiren aynı PR'da
  `python backend/scripts/export_schema.py` çalıştırır (üretir:
  `frontend/src/types/messages.generated.ts`, `docs/ws-schema.json`) ve
  `docs/ws-protocol.md`'yi günceller.
- **Öznitelik vektörü:** 12 boyut, sıra sabit (`FEATURE_NAMES`). Sıra
  değişirse eğitilmiş kalibrasyonlar geçersizleşir. `features.py` ile
  `features.ts` birebir aynı kalmalı; ikisi de
  `frontend/src/features/gaze/__fixtures__/features.json`'a karşı test edilir.
  `features.py` bilerek değişirse `scripts/export_feature_fixture.py`
  yeniden çalıştırılır ve `features.ts` aynı şekilde güncellenir.
- **İstem:** eğitim ve çıkarım `nlp/prompts.py`'deki aynı fonksiyondan üretilir.
  İstemi değiştirmek eğitilmiş adaptörleri bozar.
- **S4 etiketleri:** 8 etiket, sabit sırayla yazılır; backend `SUFFIX_TAGS`
  ile frontend `layout.ts` aynı küme ve sırada. Zemberek'ten önceki ya da
  12 etiketli S4 sonuçları ve modelleri yenileriyle karşılaştırılamaz.
- **Cümle normalleştirme:** `study/protocol.py:normalize_sentence` ile
  `frontend/src/features/study/normalize.ts` aynı kuralı uygular.
- **Simülasyon kuralları:** varsayılan deneme sınırı yok (`MAX_ROUNDS = 0`,
  20 Kasım ön kayıt kararı); ilk-1/ilk-5/MRR yalnızca ilk denemeden ölçülür.
  Simülasyon KSR'si (harf başına bir seçim) ile kullanıcı testi KSR'si (harf
  başına iki seçim + boşluk + seslendir) farklı tanımlıdır, aynı tabloda
  karşılaştırılmaz.

## Veri ve gizlilik kuralları

- **Test kümesi Ocak'a kadar açılmaz.** `test.jsonl` yalnızca sızıntı
  denetiminde okunur; simülasyon varsayılan olarak doğrulama kümesinde ölçer.
- Deney cümleleri (`data/study/sentences.json`) derleme eklenmez ve testler
  başladıktan sonra değiştirilmez; bir test bunu denetler, her kayıt dosyanın
  özetini taşır.
- Derleme cümle eklerken doğal Türkçe olmasına dikkat edin; aynı anlamdaki
  cümleler `group` ile bağlanır, bağlam (`context`) hedef cümleyi içermez.
- KVKK: kamera görüntüsü ve 478 noktalı yüz ağı hiçbir yere yazılmaz. Kayda
  yalnızca ekran konumu ve (en fazla 32 sayılık) öznitelik vektörü girer.
  `data/sessions/` repoya girmez.
- API anahtarları yalnızca `backend/.env` içinde durur.

## Kod kuralları

- Yorumlar, docstring'ler, hata mesajları ve belgeler Türkçedir; tanımlayıcılar
  İngilizce. Rapor (`report/`) İngilizcedir.
- Python 3.10+, ruff (satır 100), mypy strict. Ağır bağımlılıklar (mediapipe,
  torch, transformers) işlev içinde import edilir; testler ve simülasyon
  onlarsız koşmalı.
- Ayarlar kodda sabit değer olarak yazılmaz, `config.py` üzerinden gelir.
- Yeni şema: `AbbreviationScheme`'den türetip `register` ile kaydedin;
  simülasyon ve API otomatik görür. Yeni sağlayıcı: `ExpansionProvider`
  protokolünü uygulayıp `expander.build_provider`'a ve `config.ExpanderProvider`'a ekleyin.
- `main`'e doğrudan push yok, PR açılır. Dal adları: `feat/...`, `fix/...`,
  `docs/...`.
