document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const tabs = document.querySelectorAll('.nav-links li');
    const tabContents = document.querySelectorAll('.tab-content');
    const statusIndicator = document.querySelector('.status-indicator');
    const filterInput = document.getElementById('filter-input');
    const modeSelect = document.getElementById('mode-select');
    const themeSelect = document.getElementById('theme-select');
    const replInput = document.getElementById('repl-input');
    
    const containers = {
        console: document.getElementById('console-logs'),
        network: document.getElementById('network-logs'),
        disk: document.getElementById('disk-logs'),
        execution: document.getElementById('execution-logs')
    };
    
    const networkDetails = document.getElementById('network-details');
    
    let allLogs = [];
    let ws = null;
    let selectedNetworkLog = null;

    // Tabs logic
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            tab.classList.add('active');
            const targetId = `tab-${tab.dataset.tab}`;
            document.getElementById(targetId).classList.add('active');
        });
    });

    // WebSocket Connection
    function connectWS() {
        ws = new WebSocket(`ws://${window.location.host}/ws/dashboard`);
        
        ws.onopen = () => {
            statusIndicator.classList.add('connected');
            appendLog({
                timestamp: new Date().toISOString(),
                module: 'System',
                type: 'info',
                data: { text: 'Dashboard connected to proxy backend.' }
            });
        };
        
        ws.onclose = () => {
            statusIndicator.classList.remove('connected');
            setTimeout(connectWS, 2000); // Reconnect
        };
        
        ws.onmessage = (event) => {
            try {
                const log = JSON.parse(event.data);
                allLogs.push(log);
                processLog(log);
            } catch (e) {
                console.error("Failed to parse log", e);
            }
        };
    }
    
    connectWS();

    // Log Processing
    function processLog(log) {
        if (!passesFilter(log, filterInput.value)) return;
        
        const timeStr = new Date(log.timestamp).toLocaleTimeString([], {hour12: false, fractionalSecondDigits: 3});
        
        if (log.module === 'Network') {
            renderNetworkLog(log, timeStr);
        } else if (log.module === 'Disk') {
            renderBasicLog(containers.disk, log, timeStr);
        } else if (log.module === 'Execution') {
            renderBasicLog(containers.execution, log, timeStr);
        } else if (log.module === 'Data' && log.type === 'image_metadata') {
            renderImageMetadata(containers.disk, log, timeStr);
            // Also show a brief info in console
            renderBasicLog(containers.console, {module: 'System', type: 'info', data: {text: `Image metadata loaded for ${log.data.file}. Check Disk tab.`}}, timeStr, 'system');
        } else if (log.module === 'Console') {
            if (log.type === 'eval_result') {
                renderEvalResult(containers.console, log, timeStr);
            } else {
                renderBasicLog(containers.console, log, timeStr);
            }
        } else if (log.module === 'System') {
            if (log.type === 'init' && log.data.language) {
                replInput.placeholder = `Evaluate ${log.data.language} expression...`;
                if (log.data.mode) modeSelect.value = log.data.mode;
            }
            renderBasicLog(containers.console, log, timeStr, 'system');
        } else {
            renderBasicLog(containers.console, log, timeStr);
        }
    }

    function renderImageMetadata(container, log, timeStr) {
        const el = document.createElement('div');
        el.className = 'log-entry image-metadata';
        
        let html = `<h3>Image: ${log.data.file}</h3>`;
        html += `<div><strong>Format:</strong> ${log.data.format} | <strong>Size:</strong> ${log.data.size[0]}x${log.data.size[1]} | <strong>Mode:</strong> ${log.data.mode}</div>`;
        
        const exifCount = Object.keys(log.data.exif).length;
        if (exifCount > 0) {
            html += `<h4>EXIF Data (${exifCount} entries)</h4>`;
            html += `<pre style="max-height: 200px; overflow-y: auto; background: var(--bg-dark); padding: 5px; font-size: 0.9em;">`;
            for (let [k, v] of Object.entries(log.data.exif)) {
                html += `${k}: ${v}\n`;
            }
            html += `</pre>`;
            html += `<button class="btn-strip-exif" style="margin-top: 10px; padding: 5px 10px; background: #e74c3c; color: white; border: none; border-radius: 4px; cursor: pointer;">Strip EXIF Metadata</button>`;
        } else {
            html += `<h4>No EXIF Data found.</h4>`;
        }
        
        el.innerHTML = html;
        
        const btn = el.querySelector('.btn-strip-exif');
        if (btn) {
            btn.addEventListener('click', () => {
                if(ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({action: 'strip_exif', file: log.data.file}));
                    btn.textContent = "Stripping...";
                    btn.disabled = true;
                }
            });
        }
        
        container.appendChild(el);
        scrollToBottom(container);
    }

    function renderBasicLog(container, log, timeStr, customClass='') {
        const el = document.createElement('div');
        el.className = `log-entry ${customClass}`;
        el.dataset.raw = JSON.stringify(log);
        
        const timeEl = document.createElement('div');
        timeEl.className = 'log-time';
        timeEl.textContent = timeStr;
        
        const modEl = document.createElement('div');
        modEl.className = 'log-module';
        modEl.textContent = `[${log.module}]`;
        
        const dataEl = document.createElement('div');
        dataEl.className = 'log-data';
        
        if (log.data && log.data.text) {
            dataEl.textContent = log.data.text;
            if (log.type === 'stderr' || log.type === 'exception') el.classList.add('error');
        } else {
            dataEl.textContent = JSON.stringify(log.data);
        }
        
        el.appendChild(timeEl);
        el.appendChild(modEl);
        el.appendChild(dataEl);
        
        container.appendChild(el);
        scrollToBottom(container);
    }
    
    function renderEvalResult(container, log, timeStr) {
        const el = document.createElement('div');
        el.className = 'log-entry eval_result' + (log.data.is_error ? ' error' : '');
        el.dataset.raw = JSON.stringify(log);
        
        const timeEl = document.createElement('div');
        timeEl.className = 'log-time';
        timeEl.textContent = timeStr;
        
        const modEl = document.createElement('div');
        modEl.className = 'log-module';
        modEl.textContent = `[Eval]`;
        
        const dataEl = document.createElement('div');
        dataEl.className = 'log-data';
        dataEl.textContent = log.data.result;
        
        el.appendChild(timeEl);
        el.appendChild(modEl);
        el.appendChild(dataEl);
        
        container.appendChild(el);
        scrollToBottom(container);
    }
    
    function renderNetworkLog(log, timeStr) {
        const el = document.createElement('div');
        el.className = 'network-item';
        el.dataset.raw = JSON.stringify(log);
        
        let preview = '';
        if (log.type === 'connect') preview = `CONNECT ${log.data.address}`;
        else if (log.type === 'send') preview = `SEND ${log.data.bytes} bytes to ${log.data.address}`;
        else if (log.type === 'recv') preview = `RECV ${log.data.bytes} bytes from ${log.data.address}`;
        
        el.textContent = `${timeStr} - ${preview}`;
        
        el.addEventListener('click', () => {
            document.querySelectorAll('.network-item').forEach(i => i.classList.remove('selected'));
            el.classList.add('selected');
            selectedNetworkLog = log;
            renderNetworkDetails(log);
        });
        
        containers.network.appendChild(el);
        scrollToBottom(containers.network);
    }
    
    function renderNetworkDetails(log) {
        let html = `<h3>Network Event: ${log.type}</h3>`;
        html += `<div><strong>Time:</strong> ${log.timestamp}</div>`;
        if (log.data.address) html += `<div><strong>Address:</strong> ${log.data.address}</div>`;
        if (log.data.bytes) html += `<div><strong>Bytes:</strong> ${log.data.bytes}</div>`;
        
        if (log.data.payload_text) {
            html += `<h4>Payload (Text)</h4><pre>${escapeHtml(log.data.payload_text)}</pre>`;
        }
        if (log.data.payload_hex) {
            html += `<h4>Payload (Hex)</h4><pre>${log.data.payload_hex}</pre>`;
        }
        
        networkDetails.innerHTML = html;
    }
    
    function escapeHtml(unsafe) {
        return (unsafe || '').toString()
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    function scrollToBottom(el) {
        if (el.scrollHeight - el.scrollTop < el.clientHeight + 100) {
            el.scrollTop = el.scrollHeight;
        }
    }

    function passesFilter(log, term) {
        if (!term) return true;
        return JSON.stringify(log).toLowerCase().includes(term.toLowerCase());
    }

    // Filter Logic
    filterInput.addEventListener('input', () => {
        Object.values(containers).forEach(c => c.innerHTML = '');
        allLogs.forEach(processLog);
    });

    // Mode Toggle Logic
    modeSelect.addEventListener('change', (e) => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                action: 'set_mode',
                mode: e.target.value
            }));
        }
    });

    // Theme Toggle Logic
    themeSelect.addEventListener('change', (e) => {
        const theme = e.target.value;
        if (theme === 'dark') {
            document.body.classList.add('theme-dark');
            document.body.classList.remove('theme-light');
        } else if (theme === 'light') {
            document.body.classList.add('theme-light');
            document.body.classList.remove('theme-dark');
        } else {
            document.body.classList.remove('theme-light', 'theme-dark');
        }
    });

    // REPL Console Logic
    replInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && replInput.value.trim() !== '') {
            const code = replInput.value;
            // Echo locally
            renderBasicLog(containers.console, {
                timestamp: new Date().toISOString(),
                module: 'Console',
                type: 'input',
                data: { text: `> ${code}` }
            }, new Date().toLocaleTimeString([], {hour12: false, fractionalSecondDigits: 3}));
            
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: 'evaluate',
                    code: code
                }));
            }
            replInput.value = '';
        }
    });

    // Clear Button
    document.getElementById('btn-clear').addEventListener('click', () => {
        allLogs = [];
        Object.values(containers).forEach(c => c.innerHTML = '');
        networkDetails.innerHTML = 'Select a request to view details';
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({action: 'clear'}));
        }
    });

    // Export Button
    document.getElementById('btn-export').addEventListener('click', () => {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(allLogs, null, 2));
        const anchor = document.createElement('a');
        anchor.setAttribute("href", dataStr);
        anchor.setAttribute("download", "h4_debug_export.json");
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
    });

    // Context Menu Logic
    const contextMenu = document.getElementById('context-menu');
    let contextTargetData = null;

    document.addEventListener('contextmenu', (e) => {
        const entry = e.target.closest('.log-entry') || e.target.closest('.network-item');
        if (entry) {
            e.preventDefault();
            contextTargetData = JSON.parse(entry.dataset.raw);
            contextMenu.style.display = 'block';
            contextMenu.style.left = `${e.pageX}px`;
            contextMenu.style.top = `${e.pageY}px`;
        } else {
            contextMenu.style.display = 'none';
        }
    });

    document.addEventListener('click', () => {
        contextMenu.style.display = 'none';
    });

    document.getElementById('menu-copy').addEventListener('click', () => {
        if (contextTargetData) {
            navigator.clipboard.writeText(JSON.stringify(contextTargetData, null, 2));
        }
    });
    
    document.getElementById('menu-copy-hex').addEventListener('click', () => {
        if (contextTargetData && contextTargetData.data.payload_hex) {
            navigator.clipboard.writeText(contextTargetData.data.payload_hex);
        }
    });
});
