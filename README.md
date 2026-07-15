<div align="center">
  <h1>🚀 h4-debug</h1>
  <p><b>The Universal Application Proxy Debugger & F12-Style Web Console</b></p>
  <br />
</div>

> **h4-debug** is a ridiculously powerful, injection-free, cross-language runtime debugger. It seamlessly attaches to arbitrary scripts, applications, and native Windows executables to stream highly detailed runtime telemetry (Console, Network, Disk, Exceptions, and System Events) to an elegant, real-time web dashboard.

---

## 📖 Table of Contents

- [The Core Philosophy (Why No Injection?)](#-the-core-philosophy-why-no-injection)
- [How It Works Under the Hood](#-how-it-works-under-the-hood)
  - [Native Executables (Windows Native Debugger)](#native-executables-windows-native-debugger)
  - [Node.js Deep Hooking](#nodejs-deep-hooking)
  - [Python Introspection](#python-introspection)
- [Installation](#-installation)
- [Usage](#-usage)
- [Advanced Details & Edge Cases](#-advanced-details--edge-cases)
- [Contributing](#-contributing)

---

## 🛡 The Core Philosophy (Why No Injection?)

In the world of application tracing and reverse engineering, a common approach to gathering deep runtime telemetry is **Dynamic API Hooking** (e.g., injecting custom DLLs, patching memory in real-time using trampolines, or running Kernel-mode ETW rootkits).

**`h4-debug` rejects this methodology completely.**

Instead of mutating the target process or injecting rogue binaries, `h4-debug` achieves perfect observability through **100% native, sanctioned OS and runtime APIs**. 

### Why is this better?
1. **Zero Anti-Cheat / DRM Tripping**: By avoiding memory modification, `h4-debug` runs perfectly against heavily guarded applications. We act as a legitimate OS-level debugger, rather than operating like malware.
2. **Infinite Stability**: API hooking is notorious for causing arbitrary segmentation faults, race conditions, and application crashes. By using passive OS telemetry and standard runtime intercepts, the target application runs with maximum stability.
3. **No Rootkits Required**: You do not need to compile or install dangerous kernel-mode drivers to get network and disk observability.
4. **Universal Compatibility**: Our architecture allows us to drop in and debug Python, Node.js, and raw `.exe` binaries with the exact same UX.

---

## ⚙ How It Works Under the Hood

The `h4-debug` architecture consists of two primary components:
1. **The Telemetry Server**: A fast, asynchronous `FastAPI` instance managing real-time WebSocket connections and serving the UI dashboard.
2. **The Handlers / Interceptors**: Language/target-specific wrappers that boot the target application and transparently route its telemetry back to the server.

### Native Executables (Windows Native Debugger)

When you run `h4-debug app.exe`, the tool leverages the raw Windows Win32 Debugging API (`kernel32.dll`) via `ctypes`.

- **Event Loop Integration**: We spawn the process using `CreateProcessW` with the `DEBUG_PROCESS` flag. We then capture `WaitForDebugEvent`, natively intercepting `CREATE_PROCESS_DEBUG_EVENT`, `LOAD_DLL_DEBUG_EVENT`, thread lifecycles, and unhandled exceptions.
- **Hidden Debug Strings**: GUI applications (like Unity mods, game launchers, or heavy desktop apps) do not pipe logs to `stdout`. Instead, they typically use `OutputDebugString`. `h4-debug` intercepts `OUTPUT_DEBUG_STRING_EVENT`, uses `ReadProcessMemory` to safely read the buffer in real-time, and routes it to your console.
- **Piped stdout/stderr**: For console-based native applications, we dynamically generate anonymous pipes (`CreatePipe`) equipped with `STARTF_USESTDHANDLES` to natively capture all standard command-line output.
- **Disk & Network Polling**: Because we refuse to inject DLLs to hook `ws2_32.dll` (Network) or `ntdll.dll` (Disk), we launch a hyper-efficient, high-frequency background daemon (`psutil`). This daemon polls the target process 10 times a second, intelligently indexing newly opened file descriptors (`fd`) and newly active TCP/UDP endpoints, streaming live Disk and Network events directly to the dashboard.

*(Note: Debugging installers or protected executables often requires Administrator privileges. `h4-debug` gracefully detects `ERROR_ACCESS_DENIED` [Error 5] or `ERROR_ELEVATION_REQUIRED` [Error 740] and halts, prompting you to elevate your terminal rather than crashing).*

### Node.js Deep Hooking

When you execute `h4-debug node app.js`, the tool dynamically sets the `NODE_OPTIONS=--require ...` environment variable before executing the Node binary.

- **Console & Errors**: Overrides `console.log`, `console.error`, etc., intercepting the arguments and beaming them to the dashboard before passing them along to the original `stdout`. Automatically catches `uncaughtException` and `unhandledRejection`.
- **Network Interception**: Hot-patches the native `http.request` and `https.request` modules to trace the exact URL, method, and protocol of outbound network calls.
- **Disk Tracing**: Hooks raw filesystem methods like `fs.open`, `fs.readFile`, and `fs.writeFile`, logging the file paths being accessed.

### Python Introspection

For `h4-debug python main.py`, the debugger alters `PYTHONPATH` and injects a custom `sitecustomize.py`.
- **Seamless Boot**: Because `sitecustomize.py` is loaded before any user code executes, we establish the Telemetry Client instantly.
- **Module Hooking**: We hot-patch `sys.stdout` and `sys.stderr` to mirror all terminal output. We also monkey-patch popular HTTP libraries (like `urllib`, `requests`, and `aiohttp`) to provide granular network request visibility.

---

## 📦 Installation

Install globally via `pip`:

```bash
pip install h4-debug --upgrade
```

*Requires Python 3.8+*

---

## 🚀 Usage

Using `h4-debug` is incredibly simple. Just prefix your standard commands with `h4-debug`:

**1. Debug a Windows Executable (GUI or Console):**
```bash
# Note: Run your terminal as Administrator if the .exe requires elevation!
h4-debug installer.exe --silent
h4-debug game_launcher.exe
```

**2. Debug a Node.js Application:**
```bash
h4-debug node index.js
h4-debug npm start
```

**3. Debug a Python Script:**
```bash
h4-debug python app.py
```

### The Dashboard

Once executed, `h4-debug` immediately spins up a local web server (usually at `http://localhost:8999`) and provides a URL in the terminal. Open that URL to view the real-time F12-style developer dashboard!

The dashboard is broken into intuitive tabs:
- **Console**: See standard output, errors, and native `OutputDebugString` traces.
- **Network**: Monitor outbound HTTP/HTTPS connections and raw TCP/UDP socket activity.
- **Disk**: Track file read/write operations and active open file handles.
- **System**: Observe process creation, DLL loads, unhandled exceptions, and debugger state.

---

## 🛠 Advanced Details & Edge Cases

### The "Access Denied" Error (Native Debugging)
If you attempt to debug a Windows executable and immediately see an `Error 5` or `Error 740` in your terminal or dashboard, this means the OS has rejected the debugger attachment. 
- **The Fix**: This is an intended security mechanism in Windows. If an application requests Administrative privileges in its manifest, a non-elevated debugger cannot attach to it. Simply close your terminal, re-open it as **Administrator**, and run the command again.

### The Network / Disk Polling Interval
The native execution wrapper utilizes a `10Hz` (0.1s) polling loop to track open files and socket connections without risking application stability. While this is incredibly robust and will catch the vast majority of I/O (like an installer downloading a payload), microsecond-length file touches might occasionally slip past the poll. This is a deliberate architectural trade-off to ensure 100% stability and zero injection risk.

---

<div align="center">
  <i>Built for developers who demand total observability without compromising stability.</i>
</div>
