# Kullanıcı Testi Oturum Yönergesi ve Kontrol Listesi

**Sorumlu:** Polat Elmas · **Durum:** TASLAK (17 Kasım) · **Dayandığı belgeler:** `docs/hipotezler.md` (ön kayıt),
`data/study/anket_formu.md`, `docs/setup.md` → "Kullanıcı testi"

Bu belge bir oturumu baştan sona, her katılımcıda **aynı şekilde** yürütmek içindir. **Bütün oturumları aynı kişi (Polat)
yürütür**; böylece deneyi yürütenden gelebilecek farklar sabit kalır. Deneyi yürüten kişi okunacak
metinleri (» ile başlayan satırlar) olduğu gibi okur; kendi sözleriyle açıklama eklemez. Katılımcılar arasındaki tek fark
sistemin koda göre belirlediği koşul sırası olmalı.

İşaretler: **[BEKLENİYOR]** henüz repoda olmayan bir parçaya bağlı adım · **[EKİPLE]** ekipte netleşecek nokta

---

## 1. Oturumun özeti (yaklaşık 40 dk)

| # | Adım | Süre | Not |
|---|---|---|---|
| 1 | Karşılama, onam formu | 5 dk | Onam imzalanmadan hiçbir kayıt başlamaz |
| 2 | Demografi formu | 2 dk | `katilimcilar.csv` alanları |
| 3 | Eğitim | 5 dk | A ve B koşulları, dwell |
| 4 | Kalibrasyon | ≤ 3 dk | En fazla 2 tekrar |
| 4b | Serbest deneme | 2 dk | Yalnızca bakarak seçmeye alışma; iki koşulda ortak |
| 5 | Blok 1 (2 alıştırma + 10 cümle) | 8–10 dk | Sıra koddan gelir |
| 6 | Mola + yeniden kalibrasyon | 2–3 dk | Blok 1 B ise SUS-TR burada |
| 7 | Blok 2 (2 alıştırma + 10 cümle) | 8–10 dk | |
| 8 | Anketler | 3–4 dk | Blok 2 B ise SUS-TR, sonra k1–k5 |
| 9 | Kapanış | 1 dk | |

---

## 2. Oturumdan bir gün önce

- [ ] Katılımcıya saat ve yer hatırlatıldı; gözlük ya da lens kullanıyorsa her zamanki gibi gelmesi söylendi.
- [ ] Katılımcı kodu verildi: bir sonraki boş `K` numarası (`K01`, `K02`…). Kod sırası atlanmaz; tek numaralar A→B, çift
      numaralar B→A ile başlar, dengenin bozulmaması için **katılımcı sayısı çift** tutulur.
- [ ] Ad–kod eşleşmesi yalnızca ayrı ve şifreli dosyaya yazıldı (repoya değil).

## 3. Oturumdan önce kontrol listesi (katılımcı gelmeden 30 dk önce)

**Ortam**
- [ ] Oda: perde kapalı ya da ışık sabit; ekranın arkasında pencere yok, yüzde güçlü gölge yok.
- [ ] Çene desteği takılı; göz–ekran mesafesi **60 cm**, şerit metreyle ölçüldü.
- [ ] Harici 1080p kamera ekranın üst ortasında, sabit.
- [ ] Bilgisayar prize takılı; bildirimler, güncellemeler ve diğer uygulamalar kapalı (GPU belleği sınırlı).

**Yazılım**
- [ ] Sunucu ve arayüz çalışıyor; tarayıcı **tam ekran**, adres `http://localhost:5173/?deney`.
- [ ] `.env`: `DWELL_MS=700`, `GAZE_SOURCE=webcam`.
- [ ] Sağlayıcı **ince ayarlı model** (`mock` değil; `mock` ile alınan kayıt analizde uyarı verir).
      **[EKİPLE — Taha]** Kullanıcı testinde hangi sağlayıcı kullanılacak? `setup.md` `hf_local` diyor (16 GB GPU ister);
      demo dizüstünde `llamacpp` çalışıyor. Hangisi seçilirse bütün katılımcılarda aynı kalır.
- [ ] `data/study/sentences.json` değişmedi (kayıttaki özet önceki katılımcılarınkiyle aynı olmalı).
- [ ] Bir prova cümlesi `P` koduyla denendi, ardından sayfa yenilendi (her katılımcıdan önce yenilenir).

**Malzeme**
- [ ] Basılı: onam formu, demografi formu, SUS-TR (Bölüm 1), kısa anket (Bölüm 2; "Neyi yokluyor" sütunu olmadan), kalem.
- [ ] Bu belgenin sonundaki **deneyci not formu** (her katılımcıya bir tane).
- [ ] Saat ya da kronometre (cümle başına 3 dk kuralı için), su.

---

## 4. Oturum akışı

### 4.1 Karşılama ve onam (5 dk)

» "Hoş geldiniz, katıldığınız için teşekkür ederiz. Bugün gözle yazı yazmayı sağlayan bir sistemi deneyeceksiniz. Ölçtüğümüz
şey sizin başarınız değil, sistemin ne kadar iyi çalıştığı. Kamera yüzünüzü görecek ama **görüntü kaydedilmiyor**; yalnızca
gözünüzün nereye baktığına dair sayılar kaydediliyor. Oturum yaklaşık 40 dakika sürecek. İstediğiniz an, gerekçe göstermeden
bırakabilirsiniz; o zaman verileriniz silinir. Formu okuyup sorunuz varsa sorun."

- [ ] Onam formu imzalandı. İmzalanmazsa oturum burada biter, hiçbir şey kaydedilmez.

### 4.2 Demografi (2 dk)

- [ ] Yaş aralığı, gözlük/lens durumu, daha önce göz takibi kullanıp kullanmadığı yazıldı (`yas_araligi`, `gozluk_lens`,
      `goz_takibi_deneyimi`). Ad soyad bu forma yazılmaz.

### 4.3 Eğitim (5 dk)

Ekranda klavye açıkken okunur:

» "Ekrandaki bir kutuya yaklaşık yarım saniyeden biraz fazla bakarsanız o kutu seçilir. Harfler gruplar hâlinde duruyor: önce
harfin bulunduğu gruba, sonra harfe bakıyorsunuz. Bir yere yalnızca bakmak istiyorsanız gözünüzü fazla bekletmeyin."

» "İki farklı yöntem deneyeceksiniz. **A yönteminde** cümleyi harf harf yazıp Seslendir'e bakıyorsunuz. **B yönteminde**
yalnızca kelimelerin ilk harflerini yazıyorsunuz, örneğin 'saat kaç' için *s* ve *k*. Sonra Tamamla'ya bakıyorsunuz;
sistem birkaç cümle öneriyor, doğru olanı seçiyorsunuz. Doğru cümle listede yoksa bir kelimeyi açık yazıp yeniden
deneyebilirsiniz."

» "Her bölümde ekranın üstünde yazmanızı istediğimiz cümle görünecek. Cümle doğru seslendirilince kendiliğinden sıradakine
geçilir. Hız önemli ama acele etmeyin; yanlış yazarsanız Sil ile düzeltebilirsiniz."

- [ ] Katılımcı anladığını söyledi. Eğitimde **örnek cümle olarak deney cümlelerinden hiçbiri kullanılmaz.** Örnek ('saat kaç')
      deney ve alıştırma cümlelerindeki hiçbir kelimeyi içermez; 'su istiyorum' gibi bir örnek, dört deney cümlesindeki
      '… istiyorum' kalıbını önceden öğreteceği için kullanılmaz.
- [ ] Ardından kalibrasyon (4.4), sonra serbest deneme (4.4b).

### 4.4 Kalibrasyon (≤ 3 dk)

**[BEKLENİYOR — Yusuf]** Kalibrasyon ekranı (9 nokta + doğrulama noktaları) henüz repoda yok; adım bu ekrana göre güncellenecek.

» "Şimdi ekranda sırayla noktalar çıkacak. Her noktaya, kaybolana kadar bakın. Başınızı çene desteğinde sabit tutun."

- [ ] Doğrulama hatası (kalibrasyona **girmeyen** doğrulama noktalarından, derece) not formuna yazıldı.
- [ ] Hata eşiği aşarsa yeniden kalibrasyon; **en fazla 2 tekrar.** Üçüncü denemede de aşarsa:
      » "Sistem bugün sizin gözünüzü yeterince doğru izleyemedi; bu sizinle değil, sistemle ilgili. Katkınız için teşekkür ederiz."
      Katılımcı **her iki koşuldan** dışlanır, nedeni not formuna yazılır. Kodu yeniden kullanılmaz. Dahil edilen
      katılımcılarda A→B (tek kod) ve B→A (çift kod) sayısı eşit olana kadar katılımcı alınmaya devam edilir.
      *Eşik: ön kayıtta 2,5°; 20 Kasım karar toplantısındaki ekip ölçümlerine göre kesinleşecek.*

### 4.4b Serbest deneme (2 dk)

Amaç: Bakarak seçmeye alışmanın birinci blokta olmasını önlemek. Yoksa ilk blok yavaş çıkar ve sıra etkisi büyür. Deneme
yalnızca **iki koşulda ortak olan** becerileri çalıştırır: grup ve harf seçmek, Sil. Kısaltma ve aday listesi burada
gösterilmez, çünkü bu B koşuluna fazladan alıştırma vermek olur.

» "Şimdi iki dakika serbestçe deneyin. Önce 'evet' kelimesini harf harf yazın, sonra bir harfi Sil ile silin. Kalan sürede
istediğiniz harflere bakabilirsiniz."

- [ ] Kelimeler (`evet`, gerekirse `tamam`) deney ve alıştırma cümlelerinde geçmez (17 Kasım'da kontrol edildi).
- [ ] Süre 2 dakikayı geçmez; katılımcı erken bitirirse bekletilmez.
- [ ] **[EKİPLE — Yusuf]** Serbest deneme `?deney` modunun dışında yapılıyor. Mod değişince kalibrasyon kaybolmamalı ya da
      deneme `?deney` içinde bir "serbest deneme" adımı olarak yapılabilmeli. Aksi hâlde 4.4 deneme sonrasında tekrarlanır.

### 4.5 Blok 1 (8–10 dk)

- [ ] Durum çubuğuna katılımcı kodu yazıldı (`K..`), **Deneyi başlat**.
- [ ] Sistemin gösterdiği koşul (A ya da B) not formuna yazıldı. Deneyi yürüten koşulu **seçmez**.
- [ ] İlk iki cümle alıştırmadır:
      » "İlk iki cümle alıştırma, ölçülmüyor. Sorunuz olursa şimdi sorun."
- [ ] Ölçülen 10 cümle boyunca deneyi yürüten **yalnızca** Bölüm 5'teki cümleleri kullanır.

### 4.6 Mola ve yeniden kalibrasyon (2–3 dk)

» "Bu bölüm bitti. İki dakika gözlerinizi dinlendirin, isterseniz su için."

- [ ] **Blok 1 B ise:** SUS-TR şimdi doldurulur.
      » "Bu formdaki ifadeler az önce kullandığınız, kısaltma ve aday listesiyle yazdığınız sistem hakkında. İlk aklınıza
      gelen yanıtı işaretleyin; emin değilseniz ortadaki seçeneği işaretleyin."
- [ ] Yeniden kalibrasyon (4.4'teki kurallarla), ardından **Bloğu başlat**.

### 4.7 Blok 2 (8–10 dk)

- [ ] 4.5'teki gibi; alıştırma cümleleri yine söylenir.

### 4.8 Anketler (3–4 dk)

- [ ] **Blok 2 B ise:** SUS-TR (4.6'daki metinle).
- [ ] Kısa anket (k1–k5), herkes için oturumun en sonunda:
      » "Bu ifadeler bugünkü oturumun tamamı hakkında. A sistemi harf harf yazdığınız, B sistemi kısaltma ve aday listesiyle
      yazdığınız sistem."
- [ ] Formlarda boş madde kalmadığı katılımcıyla birlikte kontrol edildi (boş SUS maddesi o kişinin SUS puanını düşürür).
- [ ] İsteğe bağlı açık uçlu soru soruldu, yanıt not formuna yazıldı.

### 4.9 Kapanış (1 dk)

» "Teşekkür ederiz. Verileriniz yalnızca kodunuzla saklanıyor. Sonuçları merak ederseniz proje bitince paylaşabiliriz.
Lütfen kullandığınız cümleleri diğer katılımcılarla paylaşmayın."

---

## 5. Oturum sırasında müdahale kuralları

Deneyi yürüten katılımcının yerine karar vermez ve ipucu vermez. Yalnızca şu cümleler kullanılır:

| Durum | Ne yapılır / söylenir |
|---|---|
| Katılımcı "hangi harfe bakmalıyım?" diye sorar | » "Ekrandaki cümleyi yazmaya çalışın; nasıl yazacağınız size kalmış." |
| B'de doğru cümle listede yok, katılımcı takıldı | » "Bir kelimeyi açık yazıp yeniden deneyebilirsiniz." (Eğitimde söylenen kural; başka ipucu yok.) |
| Bir cümle **3 dakikada** bitmedi | **Atla.** » "Bu cümleyi geçiyoruz, sorun değil." Not formuna yazılır. (Analizde atlanan cümleler ayrıca sayılır ve 180 sn verilmiş hâliyle duyarlılık analizi yapılır; ön kayıt Bölüm 3.3.) |
| Katılımcı gözünün yorulduğunu söyler | Cümle bitince kısa mola verilir; süre not formuna yazılır. |
| Kamera yüzü kaybediyor, imleç kayıyor | Cümle bitince yeniden kalibrasyon; olay not formuna yazılır. |
| Yazılım çöker ya da bağlantı kopar | Arayüz yeniden bağlanır, deney kaldığı yerden sürer (yarım cümle baştan başlar). Saat ve olay not formuna yazılır. |
| Katılımcı rahatsızlık duyar ya da bırakmak ister | Oturum hemen durdurulur, gerekçe sorulmaz. Onamını geri çekerse verisi silinir. |

---

## 6. Oturumdan sonra (10 dk)

- [ ] `data/sessions/<kod>/` altında kayıt dosyası var ve boş değil.
- [ ] Anket ve demografi yanıtları **iki kez** girildi: önce `anket_giris1.csv` / `katilimcilar_giris1.csv`, en az bir saat sonra
      kâğıda yeniden bakarak `..._giris2.csv` (satır sırası aynı). İki dosya `diff` ile karşılaştırıldı; her fark kâğıttan
      düzeltildi, ardından dosya `anket.csv` / `katilimcilar.csv` olarak kaydedildi.
- [ ] Kâğıt formlar kodla etiketlenip kilitli bir yerde saklandı.
- [ ] Not formundaki olağan dışı her durum (atlama, çökme, yeniden kalibrasyon, dışlama) aynı gün ekip kanalına yazıldı.
- [ ] Dışlama kararları **ön kayıttaki kurallara göre** verildi; kural dışında hiçbir katılımcı ya da cümle çıkarılmadı.

---

## 7. Deneyci not formu (her katılımcı için)

| Alan | Değer |
|---|---|
| Katılımcı kodu | K__ |
| Tarih, başlangıç–bitiş saati | |
| Deneyi yürüten | Polat (farklıysa nedeni) |
| Gözlük / lens | |
| Kalibrasyon 1: hata (°), deneme sayısı | |
| Blok 1 koşulu (A/B) | |
| Kalibrasyon 2: hata (°), deneme sayısı | |
| Blok 2 koşulu (A/B) | |
| Atlanan cümleler (blok, sıra, neden) | |
| Molalar, çökmeler, yeniden kalibrasyonlar (saat, ne oldu) | |
| Dışlandı mı? Nedeni | |
| Açık uçlu yanıt | |
| Diğer notlar | |

---

## Açık noktalar

- **[EKİPLE — Taha]** Kullanıcı testindeki sağlayıcı (`hf_local` mi, `llamacpp` mi) ve kullanılacak adaptör sürümü.
- **[BEKLENİYOR — Yusuf]** Kalibrasyon ekranı ve doğrulama noktalarından hata hesabı (`purpose: "validate"`).
- **Etik kurul:** Danışman henüz karar vermedi; en kötü durumda test yalnızca ekip üyeleriyle yapılacak. O durumda da bu
  yönerge aynen uygulanır; ekip üyelerinin sistemi tanıdığı için sonuçları iyimser olabileceği raporda sınırlılık olarak yazılır.
- 25 Kasım fare provası: 4.4 atlanır (`GAZE_SOURCE=mouse`), geri kalan adımlar ve süreler bu yönergeyle denenir; prova `P` koduyla yapılır.
