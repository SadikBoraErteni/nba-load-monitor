# NBA Physical Load Monitor

## Ne bu proje

NBA'in halka açık **per-game player tracking** verisinden (maç başına kat edilen mesafe ve
ortalama hız) sporcu yükü izleyen bir Streamlit uygulaması.

Ana metrik: **ACWR — Acute:Chronic Workload Ratio.** Son 7 günlük yük / son 28 günlük ortalama
yük. 1.5 üstü ani yük artışı demek ve spor biliminde sakatlık riski göstergesi olarak
kullanılıyor. Üstüne takvim bağlamı: dinlenme günü sayısı, back-to-back maçlar.

Kasten box-score panosu **değil**. Fiziksel/tracking tarafında duruyor.

## Neden var

Sahibi: Sadık Bora Erteni (github.com/SadikBoraErteni). Bilgisayar mühendisliği son sınıf,
İstanbul. Basketbol çocukluğundan beri en sevdiği şeylerden biri.

Bu proje **SkillCorner** başvurusu için yapılıyor — Python Developer, Basketball Analysis
(staj, 6 ay, tam uzaktan, Paris/Londra). SkillCorner tek kamera görüntüsünden otomatik tracking
verisi üretip profesyonel kulüplere fiziksel ve taktiksel performans metriği satıyor. Proje
kasten onların sattığı şeyin küçük bir analoğu.

İlandaki must-have'ler ve bu projenin hangisini kapattığı:

| İlan maddesi | Nasıl karşılanıyor |
|---|---|
| Solid Python | Tüm ingest + metrik katmanı |
| Solid SQL | **DuckDB + `sql/` altında gerçek `.sql` dosyaları** |
| Streamlit deneyimi | Uygulamanın kendisi |
| Basketbolla ilgili proje | Konunun tamamı |
| AI coding agents kullanımı | Bu dosya ve geliştirme akışının kendisi |
| Cloud familiarity | Streamlit Community Cloud deploy; opsiyonel S3 |

Ayrıca pytest katmanı, Bosch ve Revolut başvurularında açıkça itiraf etmek zorunda kaldığı
"test deneyimi yok" boşluğunu kapatıyor. Bu yüzden testler süs değil, işin parçası.

## Verilmiş kararlar

- **Sadece son tamamlanmış sezon** (2025-26). İki sezon çekilmeyecek.
- Repo Sadık'ın kendi GitHub hesabında olacak.
- Proje OneDrive **dışında** duruyor: venv + binlerce parquet dosyası OneDrive senkronunu boğar.
- ACWR metriği onaylandı. Yöntem: **günlük seri, oynanmayan gün yük = 0**, akut = son
  7 günün toplamı, kronik = son 28 günün toplamı / 4. Takvim oyuncunun kendi ilk maçından
  başlar (sezon başından değil). **İlk 28 gün ACWR üretilmez** — yarım dolu kronik
  pencereyle bölmek sahte 2-3 değerleri verir.
- **Yük = mesafe (mil), tek başına.** Ortalama hız yüke karıştırılmaz, ayrı yoğunluk
  göstergesi. Elimizde yüksek hızlı koşu mesafesi (HSR) yok; hızı hacimle çarpıp "load"
  uydurmak mülakatta savunulamaz.
- Regular season **+ playoff** çekiliyor (`season_type` kolonuyla filtrelenebilir).
- **Proje metni İngilizce.** Arayüz, README, SQL yorumları, docstring'ler ve test
  isimleri İngilizce — hedef kitle SkillCorner'daki değerlendirici. Bu dosya (CLAUDE.md)
  Türkçe kalıyor, o senin çalışma dosyan.
- **Kronik pencere doluluk filtresi.** ACWR'ın matematiksel tavanı 4.0 (akut pencere
  kronik'in alt kümesi, kronik 4'e bölünüyor). Son 28 günde tek maç oynayan oyuncu
  otomatik 4.0 çıkıyor — bu yük sıçraması değil, taban yokluğu. Lig tablosu
  `games_28d >= 8` ile eliyor (tipik NBA ayı 14-15 maç). Kalibre edildi: 4'te tavan
  vakaları geçiyor, 8'de üst değer 2.96'ya oturuyor.

## Yığın

Python 3.12 · nba_api · pandas · pyarrow (Parquet) · **DuckDB** · Plotly · Streamlit · pytest

Kurulu sürümler (21 Ağu 2026): nba_api 1.11.4 · duckdb 1.5.5 · streamlit 1.62.0 · pandas 3.0.5

> Dikkat: pandas **3.x** kurulu. 2.x'e göre davranış farkları var, örnek kodları körlemesine
> kopyalama.

## Veri hattı

1. `leaguegamelog` → sezonun tüm maç ID'leri (1230 regular season + 85 playoff = 1315)
2. `boxscoreplayertrackv3` → maç başına oyuncu bazında `distance` (mil) ve `speed` (ort. hız)
3. Rate limit'e uyarak sırayla çek; her maçı Parquet'e yaz; **çekilmiş maçı tekrar çekme**
4. DuckDB Parquet'lerin üstüne view kurar; yük, dinlenme günü ve ACWR hesapları SQL'de
5. Streamlit sorguları çağırır ve çizer

> **Endpoint notu (21 Ağu 2026'da doğrulandı).** nba_api 1.11.4'te `boxscoreplayertrackv2`
> **yok**, kaldırılmış — `boxscoreplayertrackv3` kullanılıyor. v3 şeması camelCase ve
> alan adları farklı: `DIST`/`SPD` değil `distance`/`speed`. `minutes` alanı **string**
> ve `"41:45"` formatında geliyor, ondalık dakikaya parse edilmesi gerekiyor
> (`src/transform.py::parse_minutes`, ISO 8601 `"PT41M45.00S"` biçimini de tanır).
> Ölçülen hız: 0.6 s bekleme ile sorunsuz, ~1315 maç ≈ 22 dakika.

## Veri katmanları

`data/raw/{game_id}.parquet` — maç başına ham tracking. **Git'e girmez.** Dosyanın varlığı
"bu maç çekildi" demek; ingest'in defteri bu, ayrı state dosyası yok.

`data/curated/*.parquet` — birleştirilmiş, kolonları seçilmiş, dakikası parse edilmiş
katman (~35 bin satır, ~1 MB). **Git'e girer** — Streamlit Community Cloud uygulamayı
repodan çalıştırdığı için veri repoda olmak zorunda. Ham veri hâlâ dışarıda, deploy edilen
türetilmiş katman.

## Aşamalar

- [x] 0 — venv + bağımlılıklar
- [x] 1 — endpoint doğrulama (v2 yok, v3 kullanılıyor; yukarıdaki endpoint notu)
- [x] 2 — ingest scripti, sezonu Parquet'e yaz
- [x] 3 — DuckDB katmanı + `sql/` sorguları
- [x] 4 — pytest, metrik fonksiyonları
- [x] 5 — Streamlit arayüzü
- [x] 6 — README yazıldı (İngilizce, ekran görüntüleriyle); deploy kaldı
- [ ] 7 — (opsiyonel) Parquet'i S3'e taşı, AWS maddesi gerçek olsun
      → ertelendi: AWS hesabı yok, kredi kartı gerekiyor. `src/config.py::DATA_DIR`
        tek ayar olarak soyutlandı, sonradan eklemek yeniden yazma gerektirmiyor.

## Komutlar

```bash
# venv (Git Bash)
source .venv/Scripts/activate

# veri çek
python -m src.ingest --season 2025-26

# testler
pytest

# uygulama
streamlit run app.py
```

## Kurallar

- Ham veri `data/` altında, git'e **girmez** (.gitignore).
- Hesaplar SQL'de yapılır, pandas'ta değil — SQL'in repoda görünür olması bu projenin amacı.
- Her metrik fonksiyonunun pytest testi olur.
- README son adımda yazılır ve hedef kitlesi işe alan kişidir: hangi soru, hangi veri,
  hangi karar. Kütüphane listesi değil.
