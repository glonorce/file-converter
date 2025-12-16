// ===== DocuForge Pro - Real-Time Progress Controller =====

const i18n = {
    en: {
        input_title: "Source Files",
        input_desc: "Drag & Drop PDFs here",
        output_title: "Destination",
        output_desc: "Click to select folder",
        start: "Start Conversion",
        queue_title: "Process Queue",
        empty_queue: "Add some PDFs to get started",
        waiting: "Waiting",
        processing: "Processing",
        done: "Completed",
        error: "Error",
        settings: "Configuration",
        workers: "CPU Workers",
        recommended: "Recommended",
        tables: "Extract Tables",
        images: "Extract Images",
        charts: "Extract Charts (Beta)",
        ocr: "OCR Mode",
        stats: "Statistics",
        total_files: "Files",
        processed: "Done",
        speed: "sec/file",
        ready: "Ready",
        running: "Running",
        complete: "Complete",
        pages: "pages"
    },
    tr: {
        input_title: "Kaynak Dosyalar",
        input_desc: "PDF'leri buraya sürükleyin",
        output_title: "Hedef Klasör",
        output_desc: "Klasör seçmek için tıklayın",
        start: "Dönüştürmeyi Başlat",
        queue_title: "İşlem Kuyruğu",
        empty_queue: "Başlamak için PDF ekleyin",
        waiting: "Bekliyor",
        processing: "İşleniyor",
        done: "Tamamlandı",
        error: "Hata",
        settings: "Ayarlar",
        workers: "CPU İşçileri",
        recommended: "Önerilen",
        tables: "Tabloları Çıkar",
        images: "Resimleri Çıkar",
        charts: "Grafikleri Çıkar (Beta)",
        ocr: "OCR Modu",
        stats: "İstatistikler",
        total_files: "Dosya",
        processed: "Bitti",
        speed: "sn/dosya",
        ready: "Hazır",
        running: "Çalışıyor",
        complete: "Tamamlandı",
        pages: "sayfa"
    }
};

// State
let currentLang = 'tr';
let selectedFiles = [];
let selectedPath = null;
let isProcessing = false;
let startTime = null;

document.addEventListener('DOMContentLoaded', async () => {
    // Elements
    const dropInput = document.getElementById('dropInput');
    const dropOutput = document.getElementById('dropOutput');
    const fileInput = document.getElementById('fileInput');
    const convertBtn = document.getElementById('convertBtn');
    const fileListEl = document.getElementById('fileList');
    const globalProgress = document.getElementById('globalProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');

    // ===== System Info =====
    try {
        const res = await fetch('/api/info');
        const info = await res.json();
        const slider = document.getElementById('workerInput');
        slider.max = info.cpu_count;
        slider.value = info.optimal_workers;
        document.getElementById('recWorker').textContent = info.optimal_workers;
        document.getElementById('workerVal').textContent = info.optimal_workers;
        slider.oninput = (e) => document.getElementById('workerVal').textContent = e.target.value;
    } catch (e) {
        console.log('API info not available');
    }

    // ===== Toggle Switches =====
    const toggleSwitch = (id) => {
        const el = document.getElementById(id);
        el.classList.toggle('active');
        return el.classList.contains('active');
    };

    document.getElementById('tableSwitch').onclick = () => toggleSwitch('tableSwitch');
    document.getElementById('imageSwitch').onclick = () => toggleSwitch('imageSwitch');
    document.getElementById('chartSwitch').onclick = () => toggleSwitch('chartSwitch');
    document.getElementById('ocrSwitch').onclick = () => toggleSwitch('ocrSwitch');

    // ===== Theme Toggle =====
    document.getElementById('themeBtn').onclick = () => {
        const isLight = document.body.getAttribute('data-theme') === 'light';
        document.body.setAttribute('data-theme', isLight ? 'dark' : 'light');
        const icon = document.getElementById('themeIcon');
        icon.innerHTML = isLight
            ? '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>'
            : '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
    };

    // ===== Language Toggle =====
    document.getElementById('langBtn').onclick = () => {
        currentLang = currentLang === 'en' ? 'tr' : 'en';
        document.getElementById('langLabel').textContent = currentLang.toUpperCase();
        applyTranslations();
    };

    function applyTranslations() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (i18n[currentLang][key]) el.textContent = i18n[currentLang][key];
        });
    }

    // ===== File Selection =====
    dropInput.onclick = () => fileInput.click();
    fileInput.onchange = (e) => addFiles(e.target.files);

    // Drag & Drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
        dropInput.addEventListener(event, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    dropInput.addEventListener('dragover', () => dropInput.classList.add('dragover'));
    dropInput.addEventListener('dragleave', () => dropInput.classList.remove('dragover'));
    dropInput.addEventListener('drop', (e) => {
        dropInput.classList.remove('dragover');
        addFiles(e.dataTransfer.files);
    });

    function addFiles(files) {
        if (!files.length) return;
        const newFiles = Array.from(files).filter(f => f.type === 'application/pdf');
        selectedFiles = [...selectedFiles, ...newFiles];

        if (selectedFiles.length > 0) {
            dropInput.classList.add('selected');
            document.getElementById('fileSummary').innerHTML = `<strong>${selectedFiles.length}</strong> files loaded`;
            renderQueue();
            updateStats();
            updateState();
        }
    }

    // ===== Output Selection =====
    dropOutput.onclick = async () => {
        try {
            const res = await fetch('/api/browse', { method: 'POST' });
            const data = await res.json();
            if (data.path) {
                selectedPath = data.path;
                const folderName = selectedPath.split(/[/\\]/).pop();
                document.getElementById('pathSummary').innerHTML = `<strong>${folderName}</strong>`;
                dropOutput.classList.add('selected');
                updateState();
            }
        } catch (e) {
            console.error('Browse failed:', e);
        }
    };

    // ===== Queue Rendering =====
    function renderQueue() {
        if (selectedFiles.length === 0) {
            fileListEl.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="48" height="48">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
                        <line x1="9" y1="9" x2="9.01" y2="9"/>
                        <line x1="15" y1="9" x2="15.01" y2="9"/>
                    </svg>
                    <p data-i18n="empty_queue">${i18n[currentLang].empty_queue}</p>
                </div>`;
            return;
        }

        fileListEl.innerHTML = '';
        document.getElementById('queueCount').textContent = `${selectedFiles.length} files`;

        selectedFiles.forEach((file, index) => {
            const status = file._status || i18n[currentLang].waiting;
            const progress = file._progress || 0;
            const isDone = file._done || false;
            const isError = file._error || false;

            const card = document.createElement('div');
            card.className = `file-card ${file._processing ? 'processing' : ''} ${isDone ? 'done' : ''} ${isError ? 'error' : ''}`;
            card.id = `file-card-${index}`;

            let icon = '📄';
            if (file._processing) icon = '⚡';
            if (isDone) icon = '✅';
            if (isError) icon = '❌';

            card.innerHTML = `
                <div class="f-icon">${icon}</div>
                <div class="f-info">
                    <span class="f-name">${file.name}</span>
                    <span class="f-status" id="status-${index}">${status}</span>
                </div>
                <div class="f-progress">
                    <div class="f-fill" id="fill-${index}" style="width: ${progress}%"></div>
                </div>
            `;
            fileListEl.appendChild(card);
        });
    }

    // ===== Stats Update =====
    function updateStats() {
        document.getElementById('statTotal').textContent = selectedFiles.length;
        const processed = selectedFiles.filter(f => f._done).length;
        document.getElementById('statProcessed').textContent = processed;

        if (startTime && processed > 0) {
            const elapsed = (Date.now() - startTime) / 1000;
            const avgSpeed = (elapsed / processed).toFixed(1);
            document.getElementById('statSpeed').textContent = avgSpeed;
        }
    }

    // ===== State Management =====
    function updateState() {
        if (selectedFiles.length && selectedPath && !isProcessing) {
            convertBtn.disabled = false;
        } else {
            convertBtn.disabled = true;
        }
    }

    function setStatus(text) {
        document.getElementById('statusText').textContent = text;
        const dot = document.querySelector('.status-dot');
        if (isProcessing) {
            dot.style.background = 'var(--accent-orange)';
        } else {
            dot.style.background = 'var(--accent-green)';
        }
    }

    // ===== Real-Time Progress Update =====
    function updateFileUI(fileIdx, status, progress, done = false, error = false) {
        const file = selectedFiles[fileIdx];
        if (!file) return;

        file._status = status;
        file._progress = progress;
        file._done = done;
        file._error = error;
        file._processing = !done && !error;

        // Update DOM directly for speed
        const statusEl = document.getElementById(`status-${fileIdx}`);
        if (statusEl) statusEl.textContent = status;

        const fillEl = document.getElementById(`fill-${fileIdx}`);
        if (fillEl) fillEl.style.width = `${progress}%`;

        const card = document.getElementById(`file-card-${fileIdx}`);
        if (card) {
            card.className = `file-card ${file._processing ? 'processing' : ''} ${done ? 'done' : ''} ${error ? 'error' : ''}`;
            const iconEl = card.querySelector('.f-icon');
            if (iconEl) {
                if (file._processing) iconEl.textContent = '⚡';
                if (done) iconEl.textContent = '✅';
                if (error) iconEl.textContent = '❌';
            }
        }
    }

    // ===== SSE-Based Conversion with Real Page Progress =====
    convertBtn.onclick = async () => {
        if (!selectedFiles.length || !selectedPath || isProcessing) return;

        isProcessing = true;
        startTime = Date.now();
        updateState();
        setStatus(i18n[currentLang].running);

        // Show global progress
        globalProgress.classList.add('active');
        progressFill.style.width = '0%';
        progressText.textContent = '0%';

        const workers = document.getElementById('workerInput').value;
        const tables = document.getElementById('tableSwitch').classList.contains('active');
        const images = document.getElementById('imageSwitch').classList.contains('active');
        const charts = document.getElementById('chartSwitch').classList.contains('active');
        // OCR Logic: Active = 'auto', Inactive = 'off' (User Request)
        const ocr = document.getElementById('ocrSwitch').classList.contains('active') ? 'auto' : 'off';

        // Prepare FormData with ALL files
        const formData = new FormData();
        selectedFiles.forEach(file => formData.append('files', file));
        formData.append('output_path', selectedPath);
        formData.append('workers', workers);
        formData.append('tables', tables);
        formData.append('images', images);
        formData.append('charts', charts);
        formData.append('ocr', ocr);

        // Reset file states
        selectedFiles.forEach((file, idx) => {
            file._status = i18n[currentLang].waiting;
            file._progress = 0;
            file._done = false;
            file._error = false;
            file._processing = false;
        });
        renderQueue();

        try {
            // Use SSE streaming endpoint
            const response = await fetch('/api/convert-stream', {
                method: 'POST',
                body: formData
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || ''; // Keep incomplete data

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const event = JSON.parse(line.slice(6));
                            handleSSEEvent(event);
                        } catch (e) {
                            console.log('SSE parse error:', e);
                        }
                    }
                }
            }
        } catch (err) {
            console.error('Stream error:', err);
            // Fallback: mark all as error
            selectedFiles.forEach((file, idx) => {
                if (!file._done) {
                    updateFileUI(idx, 'Network Error', 100, false, true);
                }
            });
        }

        isProcessing = false;
        setStatus(i18n[currentLang].complete);
        updateState();
        updateStats();

        // Hide progress after 3s
        setTimeout(() => {
            globalProgress.classList.remove('active');
        }, 3000);
    };

    function handleSSEEvent(event) {
        const { type, file_idx, pages_done, total_pages, percent, error } = event;

        switch (type) {
            case 'file_start':
                updateFileUI(file_idx, `${i18n[currentLang].processing}...`, 5);
                break;

            case 'progress':
                // Real page-by-page progress!
                const statusText = `${pages_done}/${total_pages} ${i18n[currentLang].pages} (${percent}%)`;
                updateFileUI(file_idx, statusText, percent);

                // Update global progress
                const totalFiles = selectedFiles.length;
                const completedFiles = selectedFiles.filter(f => f._done).length;
                const currentProgress = ((completedFiles + (percent / 100)) / totalFiles) * 100;
                progressFill.style.width = `${currentProgress}%`;
                progressText.textContent = `${Math.round(currentProgress)}%`;
                break;

            case 'file_done':
                updateFileUI(file_idx, i18n[currentLang].done, 100, true, false);
                updateStats();
                break;

            case 'file_error':
                const errMsg = error?.substring(0, 25) || i18n[currentLang].error;
                updateFileUI(file_idx, errMsg, 100, false, true);
                break;

            case 'complete':
                progressFill.style.width = '100%';
                progressText.textContent = '100%';
                break;
        }
    }

    // Initial translations
    applyTranslations();
});
