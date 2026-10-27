# Kurulum ve çalışma

Windows + VS Code içindir. macOS/Linux'ta yalnızca sanal ortam etkinleştirme
komutu değişir (`source .venv/bin/activate`).

## Gereksinimler

- Python 3.10–3.12 ([python.org](https://www.python.org/downloads/), kurulumda
  "Add Python to PATH" işaretlenmeli)
- Node.js 20 LTS ([nodejs.org](https://nodejs.org))
- Git
- VS Code — açılışta önerilen eklentileri kurmayı kabul edin

## İlk kurulum

Depoyu klonlayın ve VS Code'da **klasörü** açın (tek dosyayı değil):

```bash
git clone <repo-url> FINAL-YEAR-PROJECT
cd FINAL-YEAR-PROJECT
code .
```

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

`-e` ile kurulum "düzenlenebilir" moddur: kodu değiştirdiğinizde yeniden
kurmanız gerekmez.

Doğrulayın:

```bash
pytest
uvicorn gaze_aac.main:app --reload --port 8010
```

`http://127.0.0.1:8010/docs` açılmalı ve `/health` uç noktası `"status": "ok"`
dönmeli.

### Frontend

Yeni bir terminalde:

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

`http://127.0.0.1:5173` açılır. Bağlantı göstergesi yeşil olmalı. Fareyi
tuşların üstünde 700 ms tutun — halka dolar ve seçim gerçekleşir.

## VS Code içinden çalıştırma

`F5` ile hata ayıklayıcı başlar. Hazır yapılandırmalar:

- **Backend (uvicorn)** — servisi yeniden yükleme açık olarak başlatır
- **Simülasyon** — dört şemayı karşılaştırır
- **Testler** — pytest'i ayrıntılı modda koşar

`Ctrl+Shift+P` → `Tasks: Run Task` ile: frontend dev sunucusu, lint,
sözleşme tiplerini üretme.

## Veri hattı

Ham derlem repoda tutulur: `data/corpus/aac_sentences.jsonl`. Her satır bir
cümle ve kategorisi:

```json
{"text": "Su istiyorum.", "category": "temel_ihtiyac"}
```

Aynı anlamı farklı söyleyen cümleler `"group"` alanıyla bağlanır
(`"su_istemek"` gibi). Bölme grup bazında yapılır, yani bir grubun bütün
cümleleri aynı kümeye düşer. Grubun ilki dışındakiler `"note": "çıkarılacak"`
ile işaretli; gözden geçirince silin ya da notu kaldırıp tutun.

Şu an 6 kategoride 300 taslak cümle var. Hedef ~3.000: yeni cümleleri bu
dosyaya ekleyip PR açın, böylece her ekleme gözden geçirilir. Doğal olmayan
Türkçe cümleler sonuçları sessizce bozar; emin olmadığınız cümleyi eklemeyin.

Derlemi işlemek için:

```bash
cd backend
python -m gaze_aac.data.build_corpus
```

Tekrarları atar, %80/%10/%10 böler, eğitim çiftlerini `data/processed/`
altına yazar. **Test kümesini Ocak'a kadar açmayın.**

Her eğitim cümlesi dört şemanın her biri için bir çift üretir. Çiftlerin
yaklaşık dörtte birine bir kayıt daha eklenir: ilk birkaç kelimesi açık
yazılmış kısaltma (`su i` → "Su istiyorum."). Doğru cümle listede çıkmayınca
kullanıcı böyle devam eder; model bu biçimi eğitimde görmezse orada ne
yapacağını bilemez. Oranı `--reveal-share` değiştirir, `0` kapatır.

## Simülasyon

```bash
python -m gaze_aac.evaluation.simulate --providers mock ngram --schemes S1 S2 S3 S4
```

Sağlayıcılar yalnızca eğitim kümesini görür, ölçüm doğrulama kümesinde
yapılır (`--corpus` ve `--train` ile değiştirilebilir). Sonuç
`results/simulation.csv` dosyasına yazılır. Rapora giden tablo budur.
Cümlelerde bağlam alanı yoksa "bağlam var" koşulu atlanır, çünkü aynı istemi
ikinci kez koşmaktan farkı olmaz.

Açık yazılan kelimenin maliyeti, harf sayısından o kelimenin kısaltmasının
seçim sayısı düşülerek hesaplanır (S1'de 1, S2–S3'te 2, S4'te harf +
etiketler). Eskiden her şemada 1 düşülüyordu; bu S2–S4'ü haksız yere
cezalandırıyordu ve doğrulama kümesinde n-gram KSR'sini S2'de %7,8'den
%18,1'e, S4'te %15,2'den %19,8'e çıkardı. Bu değişiklikten önceki sonuçlarla
karşılaştırma yapmayın.

`mock` sağlayıcısı yalnızca derlemdeki cümleleri bulabildiği için doğrulama
kümesinde %0 çıkar; bu beklenen sonuçtur. Karşılaştırmanın asıl tabanı
`ngram`'dır.

Demoda n-gram modelini denemek için backend `.env` dosyasında
`EXPANDER_PROVIDER=ngram` yapın. Demo, simülasyondan farklı olarak
derlemin tamamını kullanır.

## Kamera moduna geçiş

Sadece göz takibi üstünde çalışan kişinin yapması gerekir:

```bash
pip install -e ".[gaze]"
python scripts/download_model.py
```

Ardından `.env` dosyasında `GAZE_SOURCE=webcam` yapın.

## Dil modeline geçiş

Yerel model 16 GB GPU belleği ister (4-bit yüklemeyle). Dizüstü bilgisayarda
denemeyin; Colab veya Kaggle kullanın.

```bash
pip install -e ".[llm]"
```

`.env` dosyasında `EXPANDER_PROVIDER=hf_local` yapın. İnce ayarlı modeli
kullanmak için `HF_ADAPTER_PATH` değişkenine adaptör klasörünü yazın; boşsa
model sıfır atış çalışır.

## İnce ayar (QLoRA)

En kolayı Colab defteri: `notebooks/qlora_colab.ipynb` dosyasını GitHub'da
açıp "Open in Colab" deyin ya da Colab'da **Dosya → Not defteri aç → GitHub**
ile bu repoyu seçin. Çalışma zamanını **T4 GPU** yapıp hücreleri sırayla
çalıştırın. Defter adaptörü ve sonuçları Google Drive'a yazar.

Elle çalıştırmak isterseniz:

```bash
pip install -e ".[llm]"
pip install unsloth                          # isteğe bağlı, ~2 kat hız
python -m gaze_aac.data.build_corpus
python -m gaze_aac.nlp.finetune --dry-run    # GPU gerekmez
python -m gaze_aac.nlp.finetune --out <adaptör klasörü> --resume
```

`--dry-run` modeli yüklemeden veriyi denetler: şemalara göre kayıt sayısı,
doğrulama ve test cümlelerinin eğitime sızıp sızmadığı, adım sayısı ve kaba
süre. Sızıntı bulursa eğitimi başlatmaz.

Ayarlar teknik plandan gelir: r=16, alpha=32, lr=2e-4, 3 epoch, batch 4,
grad_accum 4. Tek fark uzunluk sınırı: 256 yerine 384, çünkü ek etiketi
listesini taşıyan S4 istemleri 256'ya yaklaşabilir ve sığmayan kayıt atılır.
Dolgu toplu işteki en uzun kayda göre yapıldığı için bunun bellek ya da süre
maliyeti yok. Her ayar komut satırından değiştirilebilir (`--help`).

- Kayıp yalnızca cümle üstünden hesaplanır, istem kayba katılmaz.
- Her epoch sonunda doğrulama kaybı ölçülür; en iyi epoch adaptör olarak
  kaydedilir. Veri az olduğu için son epoch'ta model ezberlemeye başlayabilir.
- Colab bağlantısı koparsa aynı komutu `--resume` ile yeniden çalıştırın,
  son epoch'tan devam eder.
- Unsloth kuruluysa onunla, değilse PEFT ile yüklenir (`--backend`).
  T4'te Unsloth'u tercih edin: Gemma 2 fp16'da taşabiliyor ve PEFT yolu
  bf16 destekli GPU'da (L4, A100) en sağlıklısı. Kayıp NaN çıkarsa betik
  uyarır.
- Adaptör klasöründeki `training_info.json` ayarları, veri boyutunu,
  doğrulama kaybını, GPU'yu, süreyi ve kodun commit'ini tutar. Rapordaki
  ayar tablosunu buradan alın.

Karşılaştırma doğrulama kümesinde, iki ayrı koşuyla yapılır (her koşu modeli
bir kez yükler):

```bash
python -m gaze_aac.evaluation.simulate --providers ngram hf_local --out results/val_sifir_atis.csv
python -m gaze_aac.evaluation.simulate --providers hf_local --adapter <adaptör klasörü> --out results/val_lora.csv
```

Tabloda sıfır atış `hf_local`, ince ayarlı model `hf_local+lora` olarak
görünür. Eğitimde ve çıkarımda istem aynı fonksiyondan üretilir
(`nlp/prompts.py`); S4 etiketleri arayüzden küçük harfle gelse de istemde
büyük harfe çevrilir.

API modelini üst sınır karşılaştırması olarak kullanmak için
`EXPANDER_PROVIDER=openai_compatible` ve `LLM_*` değişkenlerini doldurun.
**API anahtarını `.env` dosyasına yazın, koda gömmeyin** — `.gitignore`
`.env` dosyasını zaten dışarıda tutuyor.

## Sık karşılaşılanlar

**`[WinError 10013] ... bir yuvaya erişilmeye çalışıldı`** — port Windows
tarafından rezerve edilmiş. Hyper-V, WSL ve Docker Desktop açılışta dinamik
port aralıkları kapar ve 8000 sık sık bu aralığa düşer. Hangi aralıkların
kapalı olduğuna bakın:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

Projenin varsayılanı bu yüzden 8010. O da kapalıysa listedeki aralıklara
düşmeyen bir port seçin ve iki yerde ayarlayın:

```powershell
uvicorn gaze_aac.main:app --reload --port 8010
```

`frontend/.env` içinde:

```
BACKEND_PORT=8010
```

Vite vekili bu değeri okur; başka hiçbir yeri değiştirmeniz gerekmez.

**`ModuleNotFoundError: gaze_aac`** — sanal ortam etkin değil veya
`pip install -e .` çalıştırılmadı. `.venv\Scripts\activate` sonrası tekrar
deneyin.

**VS Code yanlış Python'u kullanıyor** — `Ctrl+Shift+P` →
`Python: Select Interpreter` → `backend/.venv` içindekini seçin.

**Arayüz bağlanamıyor** — backend'in ayakta olduğundan emin olun. Vite
vekili `frontend/.env` içindeki `BACKEND_PORT` portuna bakar (varsayılan
8010); uvicorn'un aynı portla başlatıldığını kontrol edin.

**`npm install` çok yavaş** — kurumsal ağlarda olur. `npm config set
registry https://registry.npmjs.org/` deneyin.

## Takım kuralları

- `main` dalına doğrudan push yok; PR açın
- Dal adları: `feat/gaze-kalibrasyon`, `fix/dwell-titreme`
- Cuma akşamı herkes dalını `main`'e birleştirir
- Haftada en az bir kez uçtan uca sistem çalıştırılır; bozuksa o hafta
  önceliği odur
- Mesaj sözleşmesini değiştiren kişi aynı PR'da tipleri yeniden üretir
  ve `docs/ws-protocol.md` dosyasını günceller
