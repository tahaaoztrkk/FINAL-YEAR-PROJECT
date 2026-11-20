# Göz takibi ölçüm yönergesi (Kişi 1)

13 Kasım planındaki göz takibi karar ölçütü:

> 3 kişide (biri gözlüklü) 700 ms dwell ile 10 denemede en az 8 doğru tuş.

Kişi başına yaklaşık 6 dakika: `?olcum` (~1,5 dk) + `?bakis` kalibrasyonu
(~75 sn) + 10 dwell denemesi (~1 dk).

## Hazırlık (bir kez)

- `main`'i çek; #26 ve #27 birleşmediyse ilgili dalları kullan.
- `cd frontend && npm install && npm run dev`
- Ekranın **fiziksel genişliğini** cetvelle ölç (yalnızca görüntü alanı,
  çerçeve hariç). Örnek: 15,6" 16:9 ekran ≈ 34,5 cm.
- Işık önden gelsin, arkada pencere olmasın. Kamera ekrana sabit.

## Her katılımcı için

Katılımcıya kaydın yalnızca yüz noktaları olduğunu, görüntü kaydedilmediğini
söyle ve onayını al. Dosyalarda isim kullanma: `kisi1`, `kisi2`, `kisi3`.

1. **Mesafe.** Katılımcı rahat oturduktan sonra göz–ekran mesafesini cetvelle
   ölç ve not et (hedef 55–65 cm).
2. **`?olcum`** (`http://127.0.0.1:5173/?olcum`)
   - Gözlük seçimini ve çözünürlüğü (1280) ayarla, başlat.
   - 9 kalibrasyon + 8 doğrulama noktası; sonra ekrandaki yazıyla başını
     hafifçe oynatıp aynı 8 nokta.
   - İnen dosyayı `kisi1-...json` olarak yeniden adlandır.
3. **`?bakis`** (`http://127.0.0.1:5173/?bakis`)
   - Kalibrasyonu başlat, ekrandaki yönergeleri izle (~75 sn).
   - İmleç baktığın yeri izliyorsa **D** tuşuna bas: 10 deneme başlar.
   - Yeşil çerçeveli hücreye bak; 700 ms durunca seçim olur (alt kenardaki
     çubuk dolar). Yanlış hücre de seçilir ve yanlış sayılır.
   - Sonuç ekranında **Sonucu indir**; dosyayı `kisi1-bakis-...json` yap.
   - Baş çok oynadıysa deneme arasında **Boşluk** (ortadaki noktaya bak).
     Kalibrasyon bozulduysa **K** ile baştan; o denemeyi sayma, not et.
4. Notları tabloya yaz:

| Kişi | Gözlük | Mesafe (cm) | `?bakis` doğru / 10 | Medyan seçim (sn) | Not |
|---|---|---|---|---|---|
| kisi1 | | | | | |
| kisi2 | | | | | |
| kisi3 | | | | | |

## Analiz

`backend` klasöründe, sanal ortam açıkken:

```bash
python -m gaze_aac.evaluation.gaze_accuracy kisi1-olcum.json --screen-cm 34.5 --distance-cm 60 --out ../results/gaze/kisi1.md
```

Mesafe kişiden kişiye farklıysa her dosyayı kendi mesafesiyle ayrı çalıştır.
Rapor, yeni sunucu modeliyle eski modeli yan yana verir: doğrulama ve baş
oynamış bloklarında derece cinsinden hata, yatay ve dikey hata (cm), 4×3
hücre isabeti.

## Karara ne götürülecek

- Kişi başına `?bakis` doğru sayısı (ölçüt: her kişide ≥ 8/10).
- Kişi başına doğrulama hatası (°), gözlüklü ve gözlüksüz ayrı.
- Dikey hata tuş yarı yüksekliğine (4×3'te ekran yüksekliğinin 1/6'sı)
  yakınsa: daha büyük tuş ya da 3×2 ızgara önerisi (plan, bölüm 6).
