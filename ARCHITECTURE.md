# DocuForge Mimari Referansı (TR)

## Genel Bakış
## Genel Bakış
DocuForge; PDF belgelerini yapay zeka (LLM) uyumlu, sürüm kontrolüne uygun (Git) ve temiz bilgi içeren Markdown formatına dönüştürmek için tasarlanmış modern bir ETL hattıdır. Tüm işlemler yerel (Local) olarak gerçekleştirilir, gizliliği korur.

## 1. Sistem Çekirdeği
- **PipelineController:** Çıkarma akışını yönetir; CLI, Web ve İşçi (Worker) ortamlarında tutarlı davranış sağlar.
- **Config Stratejisi:** Pydantic üzerinden ortam değişkenleriyle ezilebilen YAML tabanlı yapılandırma.

## 2. Nöral-Uzamsal Motor (Neural-Spatial Engine)
`docuforge.src.extraction.engine_neural` altında bulunan bu motor, görsel-anlamsal analiz ile eski parser'ların yerini alır.

### A. Vizyon Korteksi (Vision Cortex)
- Sayfa geometrisini `pdfplumber` vektör nesnelerini kullanarak analiz eder.
- Kenarlıksız (borderless) tablo sütunları için boşluk nehirlerini (whitespace rivers) tespit eder.
- Yanlış tablo tespitini önlemek için grafik/chart bölgelerini tanır.

### B. Tablo Tespiti
- **Hibrit Tespit:** Çizgi-ızgara analizi (kenarlı) ve boşluk nehri analizini (kenarlıksız) birleştirir.
- **Adaptif Eşikleme:** Geometrik hizalamayı doğrulayarak "BEL 1982 Paradoksu"nu (seyrek satırlar sorunu) çözer.

### C. Yapı Ayrıştırma (Structure Parsing)
- **Karakter İnşası (CharacterReconstructor):** Boşluk sorunlarını ("G ü ç" -> "Güç") düzeltmek için ham karakterleri (`page.chars`) dinamik boşluk eşikleriyle (`size * 0.20`) birleştirir.
- **Akıllı Footer Temizliği:** Tablo yapılarına karışan sayfa numaralarını otomatik olarak temizler.

### D. İçerik İyileştirme (TextHealer)
- Tablo hücresi işleme sürecine entegre edilmiştir.
- Sözlük tabanlı düzeltme için SymSpell kullanır.
- Türkçe ekleri ve kopuk karakterleri onarır.

## 3. Pipeline Akışı
1. **Düzen Analizi:** Nöral Motor sayfayı tablo ve grafikler için tarar.
2. **Maskeleme:** Tespit edilen tablo bölgeleri `ignore_regions` olarak toplanır.
3. **Yapı Çıkarımı:** Ana metin, dublikasyonu önlemek için maskelenmiş tablo bölgeleri *hariç tutularak* çıkarılır.
4. **Tablo Çıkarımı:** Nöral Motor tabloları ayrıştırır, içeriği iyileştirir ve Markdown üretir.
5. **Montaj:** Metin, Tablolar ve Grafikler temiz bir Markdown belgesinde birleştirilir.
6. **Temizlik:** Footer sayfa numaraları ve regex artıkları temizlenir.

## 4. Önemli Dosyalar
- `src/extraction/engine_neural.py`: Nöral Motorun çekirdek mantığı.
- `src/extraction/structure.py`: Maskeleme destekli metin çıkarıcı.
- `src/cleaning/healer.py`: Metin düzeltme aracı.
- `src/core/controller.py`: Ana pipeline mantığı.

---

# DocuForge Architecture Reference (EN)

## Overview
## Overview
DocuForge is a modern ETL pipeline designed to convert complex PDFs into AI-ready (LLM), version-controllable (Git), and strictly clean Markdown. It prioritizes 100% data privacy by processing everything locally.

## 1. System Core
- **PipelineController:** Orchestrates the extraction flow, ensuring consistent behavior across CLI, Web, and Worker environments.
- **Config Strategy:** YAML-based configuration with environment overrides via Pydantic.

## 2. Neural-Spatial Engine (Primary Extractor)
Located in `docuforge.src.extraction.engine_neural`, this engine replaces heuristic parsing with visual-semantic analysis.

### A. Vision Cortex
- Analyzes page geometry using `pdfplumber` vector objects.
- Detects whitespace rivers for borderless table columns.
- Identifies chart/graph regions to prevent misclassification.

### B. Table Detection
- **Hybrid Detection:** Combines line-grid analysis (bordered) and whitespace river analysis (borderless).
- **Adaptive Thresholding:** Solves "BEL 1982 Paradox" (sparse rows) by validating geometric alignment.

### C. Structure Parsing
- **CharacterReconstructor:** Reconstructs words from raw characters (`page.chars`) using dynamic gap thresholds (`size * 0.20`) to fix spacing issues.
- **Smart Footer Pruning:** Automatically removes page numbers that merge into table structures.

### D. Content Healing (TextHealer)
- Integrated into table cell processing.
- Uses SymSpell for dictionary-based correction.
- Fixes Turkish suffixes and orphaned characters.

## 3. Pipeline Flow
1. **Layout Analysis:** Neural Engine scans page for tables and charts.
2. **Masking:** Detected table regions are collected as `ignore_regions`.
3. **Structure Extraction:** Main text is extracted, *excluding* the masked table regions to prevent duplication.
4. **Table Extraction:** Neural Engine parses tables, heals content, and generates Markdown.
5. **Assembly:** Text, Tables, and Charts are combined into a clean Markdown document.
6. **Cleanup:** Footer page numbers and regex artifacts are removed.

## 4. Key Files
- `src/extraction/engine_neural.py`: Core logic for Neural Engine.
- `src/extraction/structure.py`: Text extractor with masking support.
- `src/cleaning/healer.py`: Text correction utility.
- `src/core/controller.py`: Main pipeline logic.
