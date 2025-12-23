# DocuForge Debug System

Merkezi debug loglama sistemi. Production'da **kapalı** tutulur, sorun çıkınca ilgili alan açılır.

## Kullanım

### Debug Alanlarını Açma/Kapama

`docuforge/debug/config.py` dosyasındaki `DEBUG_FLAGS` değerlerini değiştir:

```python
DEBUG_FLAGS = {
    "chunk_lifecycle": True,   # Açık - chunk oluşturma/silme takibi
    "executor_lifecycle": False, # Kapalı
    ...
}
```

### Log Dosyaları

Tüm debug logları `docuforge/debug/logs/` klasörüne yazılır:
- `chunk_lifecycle.txt` - Chunk oluşturma, erişim, silme
- `executor_lifecycle.txt` - Executor submit/shutdown
- `text_extraction.txt` - Metin çıkarma işlemleri
- vb.

### Kod İçi Kullanım

```python
from docuforge.debug import debug_log

# Basit log
debug_log("chunk_lifecycle", "Chunk created", path=str(chunk_path), size=file_size)

# Birden fazla context
debug_log("executor_lifecycle", "BEFORE_SUBMIT", 
    file="test.pdf",
    chunks_exist={"chunk1.pdf": True, "chunk2.pdf": True})
```

## Debug Alanları

| Alan | Açıklama |
|------|----------|
| `chunk_lifecycle` | Chunk PDF oluşturma, erişim, silme |
| `executor_lifecycle` | ProcessPoolExecutor submit/shutdown |
| `text_extraction` | Metin çıkarma, satır yeniden yapılandırma |
| `table_extraction` | Tablo algılama (neural + legacy) |
| `image_extraction` | Görsel çıkarma |
| `chart_extraction` | Grafik/chart algılama |
| `ocr_detection` | OCR tetikleme kararları |
| `ocr_processing` | OCR işleme detayları |
| `text_cleaning` | Watermark temizleme |
| `zone_cleaning` | Header/footer algılama |
| `memory_usage` | GC, bellek temizleme |
| `performance` | Zamanlama bilgileri |
| `api_requests` | API istek/yanıt |
| `sse_events` | SSE stream olayları |

## .gitignore

`config.py` ve debug klasörleri gitignore'da:
- `docuforge/debug/config.py` - Lokal ayarlar
- `chunk_debug.txt` - Eski debug dosyası
