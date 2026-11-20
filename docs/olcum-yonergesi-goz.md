# Göz takibi ölçüm yönergesi (Kişi 1)

13 Kasım planındaki göz takibi karar ölçütü:

> 3 kişide (biri gözlüklü) 700 ms dwell ile 10 denemede en az 8 doğru tuş.

Kişi başına yaklaşık 6 dakika: `?olcum` (~1,5 dk) + `?bakis` kalibrasyonu
(~75 sn) + 10 dwell denemesi (~1 dk).

Sabit koşullar: **en az 3 kişi, en az biri gözlüklü · göz–ekran 60 cm ·
tam ekran**. Çıkacak sayılar:

- `?olcum`: kişi başına derece cinsinden hata, **baş sabit** ve **baş oynamış**
  ayrı ayrı.
- `?bakis`: kişi başına 4×3 ızgarada 700 ms dwell ile 10 denemeden kaçı doğru
  tuşa düştü.

**Kayıtlar repoya girmez.** İndirilen JSON'lar kişisel veridir (yüz
noktaları); kendi bilgisayarında kalır, `.gitignore` onları dışarıda tutar.
Ekiple yalnızca özet sayılar paylaşılır (aşağıdaki tablo ve analiz raporu).

## Hazırlık (bir kez)

- `main`'i çek; #26 ve #27 birleşmediyse ilgili dalları kullan.
- `cd frontend && npm install && npm run dev`
- Ekranın **fiziksel genişliğini** cetvelle ölç (yalnızca görüntü alanı,
  çerçeve hariç). Örnek: 15,6" 16:9 ekran ≈ 34,5 cm.
- Işık önden gelsin, arkada pencere olmasın. Kamera ekrana sabit.

## Her katılımcı için

Katılımcıya kaydın yalnızca yüz noktaları olduğunu, görüntü kaydedilmediğini
söyle ve onayını al. Dosyalarda isim kullanma: `kisi1`, `kisi2`, `kisi3`.

1. **Mesafe.** Katılımcının gözü ekrandan **60 cm** uzakta olsun; cetvelle
   ayarla. Ölçüm boyunca sandalyeyi oynatmasın.
2. **`?olcum`** (`http://127.0.0.1:5173/?olcum`)
   - Gözlük seçimini ve çözünürlüğü (1280) ayarla, başlat. Sayfa tam ekrana
     geçer; geçmezse F11 ile tam ekran yap, ölçümü yeniden başlat.
   - 9 kalibrasyon + 8 doğrulama noktası; sonra ekrandaki yazıyla başını
     hafifçe oynatıp aynı 8 nokta.
   - İnen dosyayı `kisi1-...json` olarak yeniden adlandır.
3. **`?bakis`** (`http://127.0.0.1:5173/?bakis`)
   - Kalibrasyonu başlat (tam ekran), ekrandaki yönergeleri izle (~75 sn).
   - İmleç baktığın yeri izliyorsa **D** tuşuna bas: 10 deneme başlar.
   - Yeşil çerçeveli hücreye bak; 700 ms durunca seçim olur (alt kenardaki
     çubuk dolar). Yanlış hücre de seçilir ve yanlış sayılır.
   - Sonuç ekranında **Sonucu indir**; dosyayı `kisi1-bakis-...json` yap.
   - Baş çok oynadıysa deneme arasında **Boşluk** (ortadaki noktaya bak).
     Kalibrasyon bozulduysa **K** ile baştan; o denemeyi sayma, not et.
4. Notları tabloya yaz:

| Kişi | Gözlük | Baş sabit ° | Baş oynamış ° | `?bakis` doğru / 10 | Medyan seçim (sn) | Not |
|---|---|---|---|---|---|---|
| kisi1 | | | | | | |
| kisi2 | | | | | | |
| kisi3 | | | | | | |

Derece sütunları analiz raporunun "Özet" tablosundan gelir.

## Analiz

`backend` klasöründe, sanal ortam açıkken:

```bash
python -m gaze_aac.evaluation.gaze_accuracy kisi1-olcum.json kisi2-olcum.json kisi3-olcum.json --screen-cm 34.5 --distance-cm 60 --out ../results/gaze/olcum-ozet.md
```

Rapor yalnızca sayı içerir; paylaşılacak olan budur. Başta özet (kişi başına
baş sabit / baş oynamış hata, derece), sonra ızgara düzenine göre tuş isabeti
(4×3, 3×3, 3×2, 2×2), en sonda kişi başına ayrıntı (yeni ve eski model yan
yana).

## Karara ne götürülecek

- Kişi başına `?bakis` doğru sayısı (ölçüt: her kişide ≥ 8/10).
- Kişi başına doğrulama hatası (°), gözlüklü ve gözlüksüz ayrı.
- Tuş boyutu ve ızgara: rapordaki "Tuş boyutu" tablosu ve `?bakis` doğru
  sayıları birlikte; karar kuralı `docs/oneri-canli-bakis-mesaji.md`'de
  (Yusuf'la birlikte).
