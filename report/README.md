# Bitirme raporu (LaTeX)

Rapor İngilizce yazılır. **Çalışılan kopya Overleaf'tedir**; bu klasör ekibin görebildiği ortak kopyadır.

## Overleaf'e yükleme

1. Bu klasörü zip'le (`report/` içeriği: `main.tex`, `references.bib`, `chapters/`).
2. Overleaf → New Project → Upload Project → zip'i seç.
3. Menu → Compiler: pdfLaTeX, Main document: `main.tex`.

Overleaf'te yapılan değişiklikler haftada bir (Cuma birleştirmesinde) zip olarak indirilip bu klasöre PR'la geri konur.

## Kurallar

- `references.bib`'e bir kaynak, ekipten biri kaynağı açıp kontrol ettikten sonra girer. Girişin üstüne kimin ve ne zaman
  kontrol ettiği yazılır.
- Yöntem ve hipotez metinleri `docs/hipotezler.md` (ön kayıt) ile aynı olmalı; fark varsa "Deviations" bölümünde açıklanır.
- Bitmemiş yerler `\todo{...}` ile işaretlenir; teslimden önce PDF'te "TODO" araması sıfır sonuç vermeli.

## Yerelde derleme

```bash
cd report && latexmk -pdf main.tex
```
