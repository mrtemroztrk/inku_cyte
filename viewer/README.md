# inc_tests viewer

Yerel tarayıcı uygulaması: 88 kuyu × 13 zaman noktası × 4 kanal (3'ü 17 düzlemli
z-stack) verisini kanalları **üst üste bindirerek** inceler.

## Çalıştırma

```bash
python3 viewer/scan_stats.py      # bir kez: ölçek istatistikleri (~1-2 dk)
python3 viewer/app.py             # açılışta URL'yi yazar
```

Port: varsayılan **8791**; meşgulse otomatik olarak sonraki boş porta geçer ve
gerçek adresi başlangıçta yazar (`[viewer] → http://127.0.0.1:8791`). Başka bir
port istersen `INC_PORT=9000 python3 viewer/app.py`.

Bağımlılıklar: `fastapi uvicorn numpy tifffile pillow` (hepsi zaten kurulu).

Ortam değişkenleri:

| değişken | varsayılan | ne yapar |
|---|---|---|
| `INC_DATA` | `../data/inc_tests` | veri kökü (`wells/` klasörünü içeren dizin) |
| `INC_PORT` | `8791` | tercih edilen port (meşgulse üstüne çıkar) |
| `INC_PLANE_CACHE_MB` | `1500` | RAM'de tutulan çözülmüş düzlem bütçesi |
| `INC_MIP_CACHE_MB` | `600` | MIP önbelleği |
| `INC_UM_PER_PX` | `1.24` | ölçek çubuğu varsayımı (aşağıya bakın) |

## Neler var

- **Kanal overlay** — BF taban katman, Green/Orange/NIR üzerine toplamalı (additive)
  bindirilir. Kanal başına iki denetim: **aç/kapa** ve **parlaklık**. Renk kutusundan
  renk değiştirilir. Kanal ayarları tüm panellerde ortaktır, yani karşılaştırmalar
  aynı ölçekte.
- **Varsayılanlar cihazın kendi çıktısına göre ayarlı** (aşağıdaki bölüm) —
  ilk açılışta ek ayar gerekmez; `sıfırla` her zaman bu hâle döndürür.
- **Zaman** — slider, ok tuşları, oynat/durdur (kareler önce önbelleğe alınır).
  Gerçek tarih/saat ve başlangıçtan geçen süre üstte.
- **z** — **MIP açık başlar** (17 düzlemin maksimum projeksiyonu); kapatıp slider
  veya ↑/↓ ile düzlem düzlem gezilebilir.
- **Karşılaştırma** — 1 / 2 / 4 panel; paneller zoom, pan, z, zaman ve kontrastı
  paylaşır. Plakadan shift+tıkla ile sonraki panele kuyu atanır.
- **Plaka haritası** — 96'lık ızgara, ko-kültür / bileşik / T hücresi durumuna göre
  renkli; görüntülenmemiş kolon 9 soluk. Hover'da kuyu koşulu.
- **Piksel değeri** — imleç altındaki ham float değerleri (kontrastı gerçek sayılara
  göre ayarlamak için).
- **Zaman serisi** — kuyu başına kanal başına sinyal eğrisi (ortalama / p99 /
  sinyal alanı), **arkaplan çıkarılmış** (her karenin kendi medyanı) — yoksa
  kuyunun arkaplan ofseti eğriyi domine ediyor. İlk ölçüm z-yığınlarını okur,
  sonra `viewer/cache/series/` içinden gelir; `precompute.py series` ile önden
  üretilebilir.

## Varsayılanlar cihazın kendi çıktısına göre ayarlandı

`extras/vid119_B2/` Incucyte'ın **kendi kompozit çıktısı** (B02, 13 zaman noktası).
Yer gerçeği olarak kullanılıp şunlar geri hesaplandı:

- **Brightfield penceresi [57,5 – 187,5], tam opaklıkta.** Referansın gri bileşeni
  BF tif'lerine `gri ≈ 1,95·BF − 112` ile oturuyor, 13 zaman noktasında sabit
  (R² ≈ 0,98). BF'yi yarı opaklıkta göstermek görüntüyü soluklaştırıyordu.
- **Piksel boyutu 2,798 µm/px.** Referansın kendi ölçek yazısı "2,91 × 3,94 mm";
  1040 ve 1408 piksele bölününce ikisi de 2,798 veriyor (Incucyte 4×).
- **Floresan beyaz noktası** MIP'te arkaplan + p99,5, tek düzlemde arkaplan + p99,9.
- **MIP varsayılan olarak açık** — kalın sferoidin tek düzlemi büyük ölçüde odak
  dışı sis; projeksiyon referansla eşleşen görünüm.

Bir uyarı: referansın **floresan** katmanları z-stack'lerle piksel düzeyinde
örtüşmüyor (16× küçültmede bile r ≈ 0,13) — aynı nesneler aynı yerlerde çıkıyor
ama muhtemelen ayrı bir 2D tarama. BF birebir uyduğu için kuyu/zaman doğru.
Yani floresan kalibrasyonu görsel eşleşmeye dayanıyor, birebir uyuma değil.

## Kontrast: basit hâli ve gelişmiş hâli

Normal kullanımda kanal kartında iki şey var: **aç/kapa** ve **parlaklık**
(×0,25 – ×4; pencereyi daraltır, siyah noktayı oynatmaz). Renk kutusuna basarak
kanal rengi de değiştirilir. Fazlası **Gelişmiş** panelinde:

| mod | siyah nokta | beyaz nokta | ne zaman |
|---|---|---|---|
| **arkaplan** (floresan varsayılanı) | o karenin medyanı | medyan + global açıklık | genel inceleme; arkaplan düşer, parlaklık kuyular arası karşılaştırılabilir kalır |
| **mutlak** (BF varsayılanı) | sabit `lo` | sabit `hi` | cihazın penceresi; gerçek yoğunluk farkı |
| **oto** | karenin p1'i | karenin p99,8'i | tek bir tuhaf kareyi kurtarmak için |
| **elle** | slider | slider | kendi eşiğiniz |

Arkaplan modu neden gerekli: floresan kanallar float32 ve **arkaplan seviyesi
kuyudan kuyuya kayıyor** — orange kanalında B04 ≈ 43, A04 ≈ 15 birim, T hücresi
sinyali bunun kuyruğunda. Sabit tek bir siyah nokta plakanın yarısını beyazlatıyor.

`scan_stats.py` istatistikleri plakadan örnekleyerek ölçer; tek düzlem ve MIP için
ayrı ayrı, hem mutlak hem medyana göre. NIR MIP piksellerinin yalnızca %0,66'sı
sıfırın üstünde olduğu için tüm piksellerin p99,5'i arkaplanın *içine* düşüyor —
o durumda arkaplan üstü popülasyonun p95'i kullanılıyor (`hi_from` alanı hangisinin
seçildiğini söyler).

## Kanal hangi hücre tipi?

Dosya adları yalnızca `Orange_Tcells` / `NIR_deadCells` / `Green_Zstacks` diyor.
Plaka haritasıyla çapraz kontrol edilince (t0, 88 kuyu, gruplara göre ortalama):

| kanal | hücre tipi | kanıt |
|---|---|---|
| **orange** | **T hücresi** | "more T cells" kuyularında sinyal 4,8–5,9; T hücresiz kuyularda 1,6–1,9 (3×). Plaka haritasının `t_cells` kolonuyla tam örtüşüyor. |
| **green** | **tümör (PDA 30364)** | Tüm gruplarda 0,129–0,149 — makrofaj veya CAF varlığıyla hiç değişmiyor. Her kuyuda eşit yoğunlukta (2000 hücre) olan tek hücre tipi PDA. |
| **nir** | ölü hücreler | dosya adı; çok seyrek (piksellerin %0,06'sı) |

> **Makrofajların ve CAF'ların ayrı bir floresan kanalı yok.** Hangi kuyuda
> oldukları `plate_map.csv`'den bilinir (`macrophages`, `cafs` kolonları), ama
> görüntüde tümör hücrelerinden ayırt edilemezler. "Nerede makrofaj var" sorusu
> bu veriyle kuyu düzeyinde yanıtlanabilir, piksel düzeyinde yanıtlanamaz.

## 3B / derinlik modu

Üst çubuktaki **3B / derinlik** üç görünüm sunar; sırayla daha çok varsayım
gerektirirler:

| görünüm | ne gösterir | varsayım |
|---|---|---|
| **derinlik haritası** | Tek görüntü, renk = sinyalin ağırlıklı ortalama katmanı (mavi = sığ, kırmızı = derin) | **yok** — sadece katman indeksi |
| **kesit** (XZ / YZ) | Dikey kesit; infiltrasyon derinliğini uzamsal olarak gösterir | z adımı (en/boy oranı için) |
| **3B izdüşüm** | Döndürülebilir paralel izdüşüm (sürükle) | z adımı + isteğe bağlı `z abartı` |

Yanındaki **katman dağılımı** paneli sayısal cevabı verir: kanal başına her z
katmanının o kanalın toplam sinyalindeki payı, odak düzlemi ve ağırlık merkezi.

Ölçülmüş örnek (B04, t12): tümör sinyali 17 katmana yaklaşık eşit dağılmış
(katman başına %4–8), **T hücrelerinin %26'sı z03–z04'te**, **ölü hücrelerin
%64'ü tek katmanda (z04)**. Aynı ölçüm H06'da T hücrelerini z12–z14'te buluyor —
yani dağılım kuyuya göre gerçekten değişiyor.

### Sınırlar — okumadan yorumlamayın

- **z adımı dosyalarda yok** ve veriden çıkarılamıyor. Gelişmiş panelindeki
  `z adımı` alanına tarama protokolündeki değeri girin; kesit ve izdüşümün
  ölçeği tamamen buna bağlı. Derinlik haritası etkilenmez.
- **z00 mutlak bir yükseklik değil.** Odak kuyu başına ayarlandığı için kuyular
  arasında *dağılımın şeklini* karşılaştırın, katman numarasını değil.
- **Eksenel çözünürlük düşük.** 2,798 µm/px bir 4× objektif demek (NA ≈ 0,13),
  odak derinliği onlarca mikron. Beklenen şey derinlik *dilimleri*, ince 3B yapı
  değil; odak dışı sis her düzlemde var. Dekonvolüsyon uygulanmıyor.
- **z-stack yalnızca floresan kanallarda var**; brightfield tek düzlem, o yüzden
  3B modunda yok.

## Nicel analiz — `analyze.py`

Tüm plakayı 3B segmentleyip kuyu × zaman başına tek satır çıkarır.

```bash
python3 viewer/analyze.py --check                # ÖNCE BUNU: plaka haritasına karşı kontrol
python3 viewer/analyze.py --all --jobs 6         # 1144 örnek, ~35 dk → summary.csv
python3 viewer/analyze.py --wells B04,B01 --t all
```

Çıktı: `viewer/cache/analysis/summary.csv` (+ örnek başına JSON, yeniden
çalıştırmada önbellekten okunur; `--force` ile sıfırlanır).

### Ne ölçülüyor

| grup | kolonlar | tanım |
|---|---|---|
| tümör | `tumour_count`, `tumour_hull_mm2`, `tumour_hull_frac`, `tumour_volume_um3`, `tumour_mean_z` | green kanalı 3B bağlı bileşenler + konumlarının **dışbükey kabuğu** (agregat teritoryası; düzleştirme/eşik parametresi yok) |
| T hücresi | `t_count`, `t_inside_hull`, **`infiltration_ratio`**, `t_median_dist_um`, `t_frac_within_{25,50,100}um`, `t_enrich_*` | orange kanalı 3B nesneler; kabuk içi/dışı ve en yakın tümör hücresine uzaklık |
| ölüm | `dead_count`, **`dead_on_tumour` / `dead_on_tcell` / `dead_on_both` / `dead_on_neither`**, `dead_frac_inside_hull`, `dead_median_dist_um` | NIR nesneleri, **neyin üstünde olduklarına göre sınıflandırılmış** |
| derinlik | `*_mean_z`, JSON'da `*_by_z` | katman başına nesne sayısı |

### Neden yüzde değil oran

"Tümörün içindeki T hücresi yüzdesi" kuyular arasında karşılaştırılamaz: kabuk bir
kuyuda alanın %23'ünü, başka birinde %72'sini kaplıyor — ikincisinde rastgele
dağılmış T hücreleri bile %70 "içeride" çıkar. Bu yüzden ana sayı:

```
infiltration_ratio = (kabuk içi T yoğunluğu) / (kabuk dışı T yoğunluğu)
```

**1,0 = rastgele dağılım · <1 = dışlanma · >1 = zenginleşme.** Uzaklık metrikleri
de aynı normalizasyonu taşır: gözlenen "50 µm içinde" oranı, aynı kuyuda düzgün
dağılmış rastgele noktaların ulaştığı orana bölünür (`*_enrich_*`).

Ölçülen örnek (4. gün): **B04** (PDA+CAF+MAC, +T) → `infiltration_ratio` 0,00,
medyan uzaklık 872 µm: kompakt sferoid T hücrelerini tamamen dışlıyor. **B01**
(yalnız PDA, +T) → 0,77, medyan 123 µm: orada tümör kompakt değil, T hücreleri
tümör hücreleri arasında.

### Bunu yorumlamadan önce bilmeniz gerekenler

- **Turuncu kanalda T hücresi olmayan bir arkaplan popülasyonu var.** T hücresi
  eklenmeyen kuyularda da 51–374 nesne sayılıyor; T eklenen kuyularda ortalama
  yalnızca **2,5×** fazla. Yani `t_count` mutlak bir T hücresi sayısı değil.
  Karşılaştırmayı **eşleşmiş koşullar arasında** yapın (aynı ko-kültür, T'li vs
  T'siz) ve `infiltration_ratio`'yu yalnızca T eklenen kuyularda yorumlayın.
- **Kapsanma XY'de ölçülüyor, XYZ'de değil.** 4× objektifin odak derinliği onlarca
  mikron olduğu için nesneler z boyunca yayılıyor; 3B kapsanma testi bu yayılmayı
  ölçmüş olurdu. Derinlik sayıları betimleyici, kapsanma testi değil.
- **Eşikler plaka geneli** (`channel_stats.json` → `off_hi` × `THR_FRAC`), kare
  başına değil — yoksa her kuyu farklı ölçeklenir ve sayımlar karşılaştırılamaz.
- **µm³ hacimler z adımına bağlı** (`--z-step`, dosyalarda kayıtlı değil).
  Voxel sayıları (`tumour_vox`) bu varsayımdan bağımsız.
- `dead_on_*` sınıflaması NIR nesnesinin green/orange maskesiyle örtüşmesine
  dayanıyor (XY'de 1 binlenmiş piksel ≈ 5,6 µm genişletilmiş). Yoğun bölgelerde
  bir NIR noktası hem tümöre hem T hücresine değebilir — `dead_on_both` bu.

## Dosyaları uygulama dışında açmak

Floresan tif'ler float32 ve küçük sayısal aralıkta (green ≈ 0–5, ince bir kuyrukla
~300'e kadar). Genel görüntüleyiciler float TIFF'i 0–255 gri varsaydığı için görüntü
**siyah** görünür — dosya bozuk değildir. `export.py` aynı ölçeklemeyi uygulayıp
8-bit PNG/TIFF yazar:

```bash
# bir kuyu, son zaman noktası, MIP, RGB overlay
python3 viewer/export.py B04 --t 12 --mip --composite

# iki kuyunun tüm zaman noktaları, kanallar ayrı gri görüntü olarak
python3 viewer/export.py A04 B04 --t all --mip --separate

# tek z düzlemi, ImageJ/QuPath için 8-bit TIFF
python3 viewer/export.py B04 --t 12 --z 8 --separate --format tif

# tüm plaka, son zaman noktasında kuyu başına bir kompozit
python3 viewer/export.py --all --t 12 --mip --composite -o export/plate_t12
```

`--mode rel|abs|auto`, `--gain`, `--gamma`, `--bf-opacity`, `--scale 0.5`,
`--channels green,orange` seçenekleriyle uygulamadaki ayarların aynısı verilebilir.

Fiji/ImageJ float görüntüleri açarken genelde otomatik ölçekler; siyah kalırsa
*Image → Adjust → Brightness/Contrast → Auto*.

## Ölçek çubuğu

TIFF'lerde kalibrasyon yok (`XResolution` = 72 dpi sabit değeri), ama Incucyte'ın
kendi kompozit çıktısı alanı **2,91 × 3,94 mm** olarak etiketliyor. 1040 × 1408
piksele bölününce **2,798 µm/px** (Incucyte 4×) — varsayılan bu. Gelişmiş
panelindeki `µm/px` alanından değiştirilebilir.

## Mimari

Sunucu her kanalı **ayrı 8-bit gri PNG** olarak yollar; renklendirme, opaklık ve
toplamalı harmanlama tarayıcıda yapılır — böylece renk/opaklık değişimi sıfır
ağ maliyetlidir. Yalnızca kontrast sunucuda uygulanır, çünkü floresan kanallar
float32 ve dinamik aralıkları çok farklı (green ~0–6, orange ~4–1235, NIR ~0–3);
8 bit'e indirmeden önce ölçeklemek gerekiyor.

- `app.py` — FastAPI; dosya indeksi, düzlem/MIP için bayt bütçeli LRU, PNG kodlama
- `static/app.js` — paneller, canvas kompozit, plaka ızgarası, zaman çizgisi
- `scan_stats.py` — ölçek istatistiklerini plakadan örnekleyerek hesaplar
- `precompute.py` — plaka önizleme küçük resimlerini ve kuyu serilerini önden üretir
- `export.py` — uygulama dışında açılabilir 8-bit PNG/TIFF üretir
- `cache/` — `channel_stats.json`, `thumbs/`, `series/` (silinebilir, yeniden üretilir)

### API

| yol | döner |
|---|---|
| `GET /api/meta` | kuyular, zaman noktaları, kanallar, plaka haritası, aralıklar |
| `GET /api/frame/{well}/{ch}?t&z&mip&gamma&w` + `lo`/`hi` (mutlak) **veya** `off_lo`/`off_hi` (medyana göre) **veya** hiçbiri (oto) | 8-bit gri PNG; `X-Range` başlığı uygulanan aralığı verir |
| `GET /api/autorange/{well}/{ch}?t&z&mip` | o kare için yüzdelik aralık + medyan |
| `GET /api/pixel/{well}?x&y&t&z&mip` | tüm kanalların ham değeri |
| `GET /api/thumb/{well}?t&mode&size` | küçük önizleme (`bf`/`green`/`orange`/`nir`/`composite`) |
| `GET /api/wellseries/{well}?stride` | kanal başına zaman serisi |
| `GET /api/zprofile/{well}?t` | kanal başına her z katmanının payı, odak ve ağırlık merkezi |
| `GET /api/depth/{well}/{ch}?t` | derinlik-renkli görüntü (renk = katman) |
| `GET /api/ortho/{well}?t&plane=xz\|yz&x&y&z_step_um` | dikey kesit |
| `GET /api/render3d/{well}?t&az&el&z_step_um&z_exag&crop&scale` | döndürülebilir izdüşüm |
| `GET /api/extra/{t}` | VID119 RGB kompoziti (yalnız B02) |
| `GET /api/stats` | önbellek durumu |

## Kısayollar

`← →` zaman · `↑ ↓` z · `boşluk` oynat · `1–4` kanal · `M` MIP · `R` görünümü
sıfırla · tekerlek yakınlaştır · sürükle kaydır · `?` yardım
