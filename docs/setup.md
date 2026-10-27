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

```bash
cd backend
python -m gaze_aac.data.build_corpus --seed-only
```

Bu komut `data/raw/seed_sentences.jsonl` dosyasına 30 çekirdek cümle yazar.
Ekip bunu ~3.000 cümleye genişletir: her kategori için 40–50 örnek yazılır,
bir API modelinden çeşitlendirme istenir, sonra dört kişi 750'şer cümleyi
elden geçirir.

Derlem hazır olunca:

```bash
python -m gaze_aac.data.build_corpus
```

Tekrarları atar, %80/%10/%10 böler, eğitim çiftlerini üretir.
**Test kümesini Ocak'a kadar açmayın.**

## Simülasyon

```bash
python -m gaze_aac.evaluation.simulate --providers mock --schemes S1 S2 S3 S4
```

Sonuç `results/simulation.csv` dosyasına yazılır. Rapora giden tablo budur.

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

`.env` dosyasında `EXPANDER_PROVIDER=hf_local` yapın.

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
