const net = require('net');
const http = require('http');
const https = require('https');
const fs = require('fs');

const mode = process.env.H4_DEBUG_MODE || 'Normal';
const port = parseInt(process.env.H4_DEBUG_PORT || '8008', 10) + 1;
const isTelemetryThread = false;

const messageQueue = [];
let client = null;
let connected = false;

function connectTelemetry() {
    client = net.createConnection({ port: port, host: '127.0.0.1' }, () => {
        connected = true;
        sendQueue();
    });

    client.on('error', () => {
        connected = false;
        setTimeout(connectTelemetry, 1000);
    });

    client.on('close', () => {
        connected = false;
        setTimeout(connectTelemetry, 1000);
    });
}

function sendQueue() {
    if (!connected || !client) return;
    while (messageQueue.length > 0) {
        const msg = messageQueue.shift();
        try {
            client.write(JSON.stringify(msg) + '\n');
        } catch (e) {
            messageQueue.unshift(msg);
            break;
        }
    }
}

function sendEvent(module, type, data) {
    if (mode === 'Normal' && module !== 'System') return; // Do not send if normal, unless system init
    const msg = {
        timestamp: new Date().toISOString(),
        module: module,
        type: type,
        data: data,
        thread: 'Main'
    };
    messageQueue.push(msg);
    sendQueue();
}

// Start connection
connectTelemetry();

sendEvent('System', 'init', {
    mode: mode,
    pid: process.pid,
    language: 'node.js',
    version: process.version
});

// Patch Console
const originalLog = console.log;
const originalError = console.error;
const originalWarn = console.warn;

console.log = function(...args) {
    sendEvent('Console', 'stdout', { text: args.join(' ') });
    originalLog.apply(console, args);
};
console.error = function(...args) {
    sendEvent('Console', 'stderr', { text: args.join(' ') });
    originalError.apply(console, args);
};
console.warn = function(...args) {
    sendEvent('Console', 'stdout', { text: '[WARN] ' + args.join(' ') });
    originalWarn.apply(console, args);
};

// Patch HTTP
const originalHttpRequest = http.request;
http.request = function(...args) {
    let url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].href) ? args[0].href : JSON.stringify(args[0]);
    sendEvent('Network', 'connect', { address: url });
    return originalHttpRequest.apply(http, args);
};

const originalHttpsRequest = https.request;
https.request = function(...args) {
    let url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].href) ? args[0].href : JSON.stringify(args[0]);
    sendEvent('Network', 'connect', { address: url });
    return originalHttpsRequest.apply(https, args);
};

// Patch File System (read sync as example)
const originalReadFileSync = fs.readFileSync;
fs.readFileSync = function(...args) {
    sendEvent('Disk', 'open', { file: args[0], mode: 'r' });
    return originalReadFileSync.apply(fs, args);
};

// Unhandled Rejection
process.on('unhandledRejection', (reason, promise) => {
    sendEvent('Execution', 'exception', {
        type: 'UnhandledRejection',
        value: String(reason),
        file: 'unknown',
        line: 0
    });
});

process.on('uncaughtException', (err) => {
    sendEvent('Execution', 'exception', {
        type: err.name,
        value: err.message,
        file: err.stack,
        line: 0
    });
    // Rethrow to maintain standard behavior
    throw err;
});
