# Bitirme raporu (LaTeX)

Rapor İngilizce yazılır. **Tek kaynak bu klasördür** (Overleaf kullanılmıyor; 23 Kasım kararı).

## Nasıl çalışıyoruz

- Her bölüm ya da büyük değişiklik ayrı bir dalda yazılır ve PR'la `main`'e girer. Yorumlar PR'da satır satır yapılır.
- Bölüm sahipleri: Yöntem, deney ve analiz → Polat; Sistem → ilgili kısmın sahibi (Berkay, Yusuf, Taha); Model, derlem ve Çalışma A → Taha.
- `report/` altında bir dosyaya dokunan her PR'da GitHub Actions raporu derler (`.github/workflows/report.yml`). Derleme hatası
  PR'ın "Checks" kısmında görünür.

## PDF'i görmek

PR sayfası → **Checks** → "Report PDF" → çalıştırma sayfasının altındaki **Artifacts** → `rapor-pdf` (zip içinde `main.pdf`;
30 gün saklanır). Aynı sayfadaki özette kalan `\todo` sayısı yazar. `main`'deki son hâlin PDF'i için: Actions → Report PDF →
en son `main` çalıştırması.

## Kurallar

- `references.bib`'e bir kaynak, ekipten biri kaynağı açıp kontrol ettikten sonra girer. Girişin üstüne kimin ve ne zaman
  kontrol ettiği yazılır.
- Yöntem ve hipotez metinleri `docs/hipotezler.md` (ön kayıt) ile aynı olmalı; fark varsa "Deviations" bölümünde açıklanır.
- Bitmemiş yerler `\todo{...}` ile işaretlenir; teslimden önce PDF'te "TODO" araması sıfır sonuç vermeli.

## Yerelde derleme

```bash
cd report && latexmk -pdf main.tex
```
