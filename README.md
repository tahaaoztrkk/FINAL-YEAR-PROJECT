# Göz Takibiyle Türkçe İletişim Sistemi

Konuşma ve hareket yeteneğini kaybetmiş kullanıcıların yalnızca göz hareketiyle,
kısaltılmış girdi üzerinden Türkçe cümle kurmasını sağlayan sistem.

Kullanıcı `s i` yazar, sistem "su istiyorum" cümlesini üretir ve seslendirir.

## Mimari

```
frontend/          React + TypeScript arayüz (klavye, dwell, aday listesi)
backend/           FastAPI servisi
  gaze/            Göz takibi: landmark, öznitelik, kalibrasyon, filtre, dwell
  nlp/             Kısaltma şemaları ve cümle genişletme
  data/            AAC derlemi ve eğitim çifti üretimi
  evaluation/      KSR, ilk-k doğruluk, simülasyon
  schemas/         İstemci–sunucu mesaj sözleşmesi (tek doğruluk kaynağı)
docs/              Mimari, protokol ve kurulum belgeleri
data/              Derlem ve türetilmiş veri (repoya girmez)
```

Veri akışı: kamera → landmark → bakış tahmini → dwell seçimi → kısaltma →
dil modeli → aday cümleler → seslendirme.

Ayrıntı için [docs/architecture.md](docs/architecture.md).

## Hızlı başlangıç

İlk iş: `vscode-config/` klasöründeki dört dosyayı `.vscode/` içine kopyalayın.

```powershell
New-Item -ItemType Directory -Force .vscode
Copy-Item vscode-config\*.json .vscode\
Remove-Item -Recurse vscode-config
```

Sonrası iki terminal gerektirir.

**Backend**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
copy .env.example .env
uvicorn gaze_aac.main:app --reload --port 8010
```

`http://127.0.0.1:8010/docs` adresinde API dokümanı açılır.

**Frontend**

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

`http://127.0.0.1:5173` adresinde arayüz açılır.

İlk kurulumda hiçbir model indirilmez: bakış kaynağı fare, genişletici ise
kural tabanlı sahte sağlayıcıdır. Gerçek bileşenlere geçiş `.env` üzerinden
yapılır (`GAZE_SOURCE`, `EXPANDER_PROVIDER`).

## Geliştirme

```bash
cd backend
pytest                  # testler
ruff check src tests    # lint
ruff format src tests   # biçimlendirme
mypy src                # tip denetimi
```

Mesaj sözleşmesi değiştiğinde TypeScript tiplerini yeniden üretin:

```bash
python scripts/export_schema.py
```

## Takım

| Katman | Sahip |
| --- | --- |
| `backend/src/gaze_aac/gaze` | Kişi 1 |
| `backend/src/gaze_aac/nlp`, `data`, `evaluation` | Kişi 2 |
| `frontend`, `backend/src/gaze_aac/api` | Kişi 3 |
| `docs`, deney protokolü, rapor | Kişi 4 |

Dal adlandırma: `feat/gaze-kalibrasyon`, `fix/dwell-titreme`.
`main` dalına doğrudan push yapılmaz, PR açılır.
# FINAL-YEAR-PROJECT
