# Kullanıcı Testi Anket Formu

Bu form kâğıda basılır ya da tablette doldurulur. Yanıtlar oturumdan sonra `data/sessions/anket.csv` dosyasına girilir
(şablon: `data/study/anket_sablonu.csv`, sütunlar `katilimci, sus1–sus10, k1–k5`). Analiz `python -m gaze_aac.evaluation.study --survey data/sessions/anket.csv` ile yapılır.

**Ne zaman doldurulur?**

| Bölüm | Zaman | Neden |
|---|---|---|
| Bölüm 1 — SUS-TR | **B bloğu biter bitmez** (A→B sırasında oturumun sonunda, B→A sırasında iki blok arasındaki molada) | H-B2 yalnızca kısaltma sistemini ölçüyor; deneyim tazeyken doldurulur |
| Bölüm 2 — Kısa anket (k1–k5) | **Oturumun en sonunda, bir kez** | Göz yorgunluğu ve tercih gibi maddeler bütün oturumu kapsıyor |

Katılımcı kodu her sayfanın üstüne yazılır (ör. `K07`). Ad soyad bu forma yazılmaz.

---

## Bölüm 1 — Sistem Kullanılabilirlik Ölçeği (SUS-TR)

**Kaynak:** Demirkol, D. ve Şeneler, Ç. (2018). A Turkish translation of the System Usability Scale: The SUS-TR.
*Uşak Üniversitesi Sosyal Bilimler Dergisi*, 11(3), 237–253. https://doi.org/10.29217/uujss.495
Çeviri, ölçeğin yazarı John Brooke'un izniyle yapılmış; 324 üniversite öğrencisinde Cronbach α = 0,84, iki faktörlü yapı.

> **Doğrulandı (10 Kasım 2026, Polat):** Aşağıdaki 10 madde ve ölçek uçları, makalenin Ek'indeki Tablo A2 ile karakter
> karakter karşılaştırıldı (PDF'ten çıkarılan metin, betikle); 10/10 madde birebir aynı. α = 0,84 (Tablo 4) ve izin bilgisi
> de PDF'ten kontrol edildi.
>
> **Maddelerin sözcükleri değiştirilmez**; aksi hâlde geçerlik çalışmasına dayanamayız. 10. maddedeki "bir çok" yazımı
> (bugünkü kurala göre "birçok") kaynaktaki hâlidir, bilerek düzeltilmedi.

**Yönerge (katılımcıya okunur):** "Aşağıdaki ifadeler az önce kullandığınız **kısaltma ve aday listesi sistemi** hakkındadır.
Her ifadeye ne kadar katıldığınızı, ilk aklınıza gelen yanıtı işaretleyerek belirtin. Doğru ya da yanlış yanıt yoktur.
Bir ifadeyi yanıtlayamıyorsanız ortadaki (3) seçeneği işaretleyin."

Ölçek: **1 = Hiç katılmıyorum** · 2 · 3 · 4 · **5 = Tamamen katılıyorum**

| # | İfade | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 1 | Bu sistemi sıklıkla kullanmak isteyeceğimi düşünüyorum. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 | Bu sistemi gereksiz bir şekilde karmaşık buldum. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | Bu sistemin kullanımının kolay olduğunu düşündüm. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 | Bu sistemi kullanabilmek için daha teknik bir kişinin desteğine ihtiyaç duyacağımı düşünüyorum. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 | Bu sistemdeki çeşitli fonksiyonları iyi entegre edilmiş buldum. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 | Bu sistemde çok fazla tutarsızlık olduğunu düşündüm. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 | Birçok insanın bu sistemi kullanmayı çok çabuk öğreneceğini sanıyorum. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 | Bu sistemin kullanımını çok elverişsiz buldum. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 | Bu sistemi kullanırken kendimden çok emin hissettim. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | Bu sistemde bir şeyler yapabilmek için öncelikle bir çok şey öğrenmem gerekti. | ☐ | ☐ | ☐ | ☐ | ☐ |

**Puanlama** (`study.sus_score`): tek numaralı maddelerde (yanıt − 1), çift numaralılarda (5 − yanıt); toplam × 2,5 → 0–100.
Bir madde boş bırakılırsa o katılımcının SUS puanı hesaplanmaz (kod bunu boş hücre olarak işler); katılımcıdan formu teslim
etmeden önce boş madde kalmadığını kontrol etmesi istenir.

---

## Bölüm 2 — Kısa anket (k1–k5)

Bu maddeler bu proje için yazıldı; **geçerlik çalışması yoktur ve bir ölçek oluşturmazlar.** Toplam puan alınmaz, her madde ayrı
ayrı betimsel olarak (medyan ve dağılım) raporlanır ve hipotez testinde kullanılmaz. Teknik plandaki "NASA-TLX ve göz yorgunluğu
analizi kapsam dışı; kısa anket yeterli" kararının karşılığıdır.

**Yönerge:** "Aşağıdaki ifadeler **bugünkü oturumun tamamı** hakkındadır. A sistemi harf harf yazdığınız klavye, B sistemi
kısaltma ve aday listesiyle yazdığınız sistemdir."

Ölçek: **1 = Hiç katılmıyorum** · 2 · 3 · 4 · **5 = Tamamen katılıyorum**

> "Neyi yokluyor" sütunu yalnızca ekip içindir; **basılı formda yer almaz** (maddenin amacını görmek yanıtı etkiler).

| # | İfade | Neyi yokluyor | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|---|
| k1 | Oturum boyunca gözlerim yoruldu. | Göz yorgunluğu (kapsam dışı bırakılan analizin yerine tek madde) | ☐ | ☐ | ☐ | ☐ | ☐ |
| k2 | Oturum boyunca bakmak istediğim bir hedef sık sık istemeden seçildi. | Midas touch: dwell süresinin yeterliliği (dwell iki koşulda aynı, 700 ms) | ☐ | ☐ | ☐ | ☐ | ☐ |
| k3 | B sisteminde aday listesindeki cümleleri okuyup doğrusunu bulmak beni zorladı. | Aday listesinin zihinsel yükü (WPM kazancını yiyebilecek maliyet) | ☐ | ☐ | ☐ | ☐ | ☐ |
| k4 | B sisteminde yazmam gereken cümle çoğunlukla aday listesindeydi. | Önerilerin algılanan isabeti (ölçülen ilk-5 doğrulukla betimsel karşılaştırılır) | ☐ | ☐ | ☐ | ☐ | ☐ |
| k5 | Bir şey söylemem gerekseydi B sistemini A sistemine tercih ederdim. | Genel tercih | ☐ | ☐ | ☐ | ☐ | ☐ |

**Açık uçlu (isteğe bağlı, CSV'ye girmez; raporda alıntı olarak kullanılabilir):**
"Sistemlerde sizi en çok zorlayan şey neydi?" ………………………………………………………………

> Not: k1, k2 ve k3 olumsuz, k4 ve k5 olumlu yönde yazıldı. Ters puanlama yapılmaz, çünkü toplam puan alınmıyor; raporda
> her maddenin yönü belirtilir.
