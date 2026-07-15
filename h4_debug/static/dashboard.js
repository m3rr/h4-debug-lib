document.addEventListener('DOMContentLoaded', () => {
    // UI Elements
    const tabs = document.querySelectorAll('.nav-links li');
    const tabContents = document.querySelectorAll('.tab-content');
    const statusIndicator = document.querySelector('.status-indicator');
    const filterInput = document.getElementById('filter-input');
    
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
        } else if (log.module === 'Console') {
            renderBasicLog(containers.console, log, timeStr);
        } else if (log.module === 'System') {
            renderBasicLog(containers.console, log, timeStr, 'system');
        } else {
            renderBasicLog(containers.console, log, timeStr);
        }
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
