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
        pages: "pages",
        tags: "Removable Tags",
        warning_line1: "Output may contain errors",
        warning_line2: "Verification recommended",
        ocr_off: "Off",
        ocr_auto: "Auto",
        ocr_on: "On"
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
        pages: "sayfa",
        tags: "Silinecek Etiketler",
        warning_line1: "Çıktıda hatalar olabilir",
        warning_line2: "Kontrol etmenizde fayda var",
        ocr_off: "Kapalı",
        ocr_auto: "Otomatik",
        ocr_on: "Açık"
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
    const btnIcon = document.getElementById('btnIcon');
    const btnText = document.getElementById('btnText');
    const fileListEl = document.getElementById('fileList');
    const globalProgress = document.getElementById('globalProgress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');

    // Abort controller for stopping processing
    let abortController = null;

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

    // OCR Selector - 3-state (off/auto/on)
    document.querySelectorAll('.ocr-btn').forEach(btn => {
        btn.onclick = () => {
            document.querySelectorAll('.ocr-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        };
    });

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

        // Adjust OCR button size for Turkish (longer words)
        const ocrBtns = document.querySelectorAll('.ocr-btn');
        ocrBtns.forEach(btn => {
            btn.style.fontSize = currentLang === 'tr' ? '0.6rem' : '0.7rem';
            btn.style.padding = currentLang === 'tr' ? '4px 8px' : '4px 12px';
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

        // Clear completed/processed files when adding new ones
        selectedFiles = selectedFiles.filter(f => !f._done && !f._error);
        selectedFiles = [...selectedFiles, ...newFiles];

        // Reset stats for fresh start
        startTime = null;
        document.getElementById('statSpeed').textContent = '0';
        document.getElementById('counterCurrent').textContent = '0';
        document.getElementById('elapsedTime').textContent = '00:00';

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
        if (isProcessing) return;  // Don't allow change during processing
        try {
            const res = await fetch('/api/browse', { method: 'POST' });
            const data = await res.json();
            if (data.path && data.path.trim() !== '') {
                selectedPath = data.path;
                const folderName = selectedPath.split(/[/\\]/).pop();
                document.getElementById('pathSummary').innerHTML = `<strong>${folderName}</strong><br><small style="opacity:0.6">Click to change</small>`;
                dropOutput.classList.add('selected');
                updateState();
            }
            // If cancelled (empty path), just do nothing - allow retry
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

            // Show remove button ONLY if NOT processing globally
            const showRemove = !isProcessing;
            // Show view button only if done
            const showView = isDone && file._outputPath;

            card.innerHTML = `
                <div class="f-icon">${icon}</div>
                <div class="f-info">
                    <span class="f-name">${file.name}</span>
                    <span class="f-status" id="status-${index}">${status}</span>
                </div>
                <div class="f-progress">
                    <div class="f-fill" id="fill-${index}" style="width: ${progress}%"></div>
                </div>
                <div class="f-actions">
                    ${showView ? `<button class="f-view" data-path="${file._outputPath}" title="Görüntüle">👁</button>` : ''}
                    ${showRemove ? `<button class="f-remove" data-index="${index}" title="Remove">×</button>` : ''}
                </div>
            `;
            fileListEl.appendChild(card);
        });

        // Add remove handlers
        document.querySelectorAll('.f-remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.target.dataset.index);
                selectedFiles.splice(idx, 1);
                renderQueue();
                updateStats();
                updateState();
                if (selectedFiles.length === 0) {
                    dropInput.classList.remove('selected');
                    document.getElementById('fileSummary').innerHTML = '';
                    // Reset all stats when no files left
                    startTime = null;
                    document.getElementById('statSpeed').textContent = '0';
                    document.getElementById('elapsedTime').textContent = '00:00';
                } else {
                    document.getElementById('fileSummary').innerHTML = `<strong>${selectedFiles.length}</strong> files loaded`;
                }
            });
        });

        // Add view handlers - open MD in new tab
        document.querySelectorAll('.f-view').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const mdPath = e.target.dataset.path;
                if (mdPath) {
                    window.open(`/api/view-md?path=${encodeURIComponent(mdPath)}`, '_blank');
                }
            });
        });
    }

    // ===== Stats Update =====
    function updateStats() {
        const total = selectedFiles.length;
        const processed = selectedFiles.filter(f => f._done).length;

        // Update stats cards
        document.getElementById('statTotal').textContent = total;
        document.getElementById('statProcessed').textContent = processed;

        // Update large counter
        document.getElementById('counterCurrent').textContent = processed;
        document.getElementById('counterTotal').textContent = total;

        if (startTime && processed > 0) {
            const elapsed = (Date.now() - startTime) / 1000;
            const avgSpeed = (elapsed / processed).toFixed(1);
            document.getElementById('statSpeed').textContent = avgSpeed;
        }
    }

    // ===== Elapsed Time Timer =====
    let elapsedInterval = null;

    function startElapsedTimer() {
        const elapsedEl = document.getElementById('elapsedTime');
        elapsedInterval = setInterval(() => {
            if (!startTime) return;
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const mins = Math.floor(elapsed / 60).toString().padStart(2, '0');
            const secs = (elapsed % 60).toString().padStart(2, '0');
            elapsedEl.textContent = `${mins}:${secs}`;
        }, 1000);
    }

    function stopElapsedTimer() {
        if (elapsedInterval) {
            clearInterval(elapsedInterval);
            elapsedInterval = null;
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

    // Lock/unlock inputs during processing and toggle button
    function lockInputs() {
        document.body.classList.add('processing');  // CSS handles hiding/disabling
        dropInput.classList.add('locked');
        dropOutput.classList.add('locked');
        // Transform button to stop mode
        convertBtn.classList.add('stop-mode');
        btnIcon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>`;
        btnText.textContent = 'Durdur';
        convertBtn.disabled = false;
    }

    function unlockInputs() {
        document.body.classList.remove('processing');  // CSS handles showing/enabling
        dropInput.classList.remove('locked');
        dropOutput.classList.remove('locked');
        // Transform button back to start mode
        convertBtn.classList.remove('stop-mode');
        btnIcon.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="5 3 19 12 5 21 5 3" />
        </svg>`;
        btnText.textContent = i18n[currentLang].start;
    }

    // Stop processing function
    function stopProcessing() {
        if (abortController) {
            // Cancel backend workers
            fetch('/api/cancel', { method: 'POST' }).catch(() => { });

            abortController.abort();
            isProcessing = false;
            unlockInputs();
            stopElapsedTimer();
            setStatus(i18n[currentLang].ready);
            updateState();
            // Mark remaining files as stopped
            selectedFiles.forEach((file, idx) => {
                if (!file._done && !file._error) {
                    file._status = 'Durduruldu';
                    file._error = true;
                }
            });
            renderQueue();
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
        // If in stop mode, stop processing
        if (convertBtn.classList.contains('stop-mode')) {
            stopProcessing();
            return;
        }

        if (!selectedFiles.length || !selectedPath || isProcessing) return;

        isProcessing = true;
        startTime = Date.now();
        abortController = new AbortController();
        updateState();
        lockInputs();  // Lock inputs during processing
        setStatus(i18n[currentLang].running);

        // Start elapsed timer and reset counter
        document.getElementById('elapsedTime').textContent = '00:00';
        startElapsedTimer();
        updateStats();

        // Show global progress
        globalProgress.classList.add('active');
        progressFill.style.width = '0%';
        progressText.textContent = '0%';

        const workers = document.getElementById('workerInput').value;
        const tables = document.getElementById('tableSwitch').classList.contains('active');
        const images = document.getElementById('imageSwitch').classList.contains('active');
        const charts = document.getElementById('chartSwitch').classList.contains('active');
        // OCR: Get value from active button (off/auto/on)
        const ocrActiveBtn = document.querySelector('.ocr-btn.active');
        const ocr = ocrActiveBtn ? ocrActiveBtn.dataset.value : 'auto';

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
                body: formData,
                signal: abortController.signal
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
        abortController = null;
        unlockInputs();  // Unlock inputs after processing
        renderQueue();   // Refresh UI to show X buttons
        stopElapsedTimer();
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
                // Save output path for View button
                if (event.path) {
                    selectedFiles[file_idx]._outputPath = event.path;
                }
                updateFileUI(file_idx, i18n[currentLang].done, 100, true, false);
                updateStats();
                renderQueue();  // Re-render to show View button
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

    // ===== Tag Management =====
    const tagInput = document.getElementById('tagInput');
    const addTagBtn = document.getElementById('addTagBtn');
    const tagList = document.getElementById('tagList');

    // Load existing tags
    async function loadTags() {
        try {
            const resp = await fetch('/api/tags');
            const data = await resp.json();
            renderTags(data.tags || []);
        } catch (e) {
            console.error('Failed to load tags:', e);
        }
    }

    // Render tags as chips
    function renderTags(tags) {
        tagList.innerHTML = '';
        tags.forEach(tag => {
            const chip = document.createElement('div');
            chip.className = 'tag-chip';
            chip.innerHTML = `
                <span>${tag}</span>
                <button class="remove-tag" title="Remove">&times;</button>
            `;
            chip.querySelector('.remove-tag').addEventListener('click', () => removeTag(tag));
            tagList.appendChild(chip);
        });
    }

    // Add tag
    async function addTag() {
        const pattern = tagInput.value.trim();
        if (!pattern) return;

        try {
            const formData = new FormData();
            formData.append('pattern', pattern);

            const resp = await fetch('/api/tags', {
                method: 'POST',
                body: formData
            });
            const data = await resp.json();

            if (data.success) {
                tagInput.value = '';
                loadTags();
            }
        } catch (e) {
            console.error('Failed to add tag:', e);
        }
    }

    // Remove tag
    async function removeTag(pattern) {
        try {
            const formData = new FormData();
            formData.append('pattern', pattern);

            await fetch('/api/tags', {
                method: 'DELETE',
                body: formData
            });
            loadTags();
        } catch (e) {
            console.error('Failed to remove tag:', e);
        }
    }

    // Event listeners
    addTagBtn.addEventListener('click', addTag);
    tagInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addTag();
    });

    // Load tags on startup
    loadTags();

    // Apply translations on startup (for OCR button sizing)
    applyTranslations();
});
