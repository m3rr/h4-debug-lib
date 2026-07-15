import ctypes
from ctypes import wintypes
import time
import struct
import sys
import os
import threading

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

DEBUG_PROCESS = 0x00000001
DEBUG_ONLY_THIS_PROCESS = 0x00000002
DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001

# Event Codes
EXCEPTION_DEBUG_EVENT = 1
CREATE_THREAD_DEBUG_EVENT = 2
CREATE_PROCESS_DEBUG_EVENT = 3
EXIT_THREAD_DEBUG_EVENT = 4
EXIT_PROCESS_DEBUG_EVENT = 5
LOAD_DLL_DEBUG_EVENT = 6
UNLOAD_DLL_DEBUG_EVENT = 7
OUTPUT_DEBUG_STRING_EVENT = 8
RIP_EVENT = 9

class STARTUPINFO(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]

class EXCEPTION_RECORD(ctypes.Structure):
    pass
EXCEPTION_RECORD._fields_ = [
    ("ExceptionCode", wintypes.DWORD),
    ("ExceptionFlags", wintypes.DWORD),
    ("ExceptionRecord", ctypes.POINTER(EXCEPTION_RECORD)),
    ("ExceptionAddress", ctypes.c_void_p),
    ("NumberParameters", wintypes.DWORD),
    ("ExceptionInformation", ctypes.c_void_p * 15),
]

class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("ExceptionRecord", EXCEPTION_RECORD),
        ("dwFirstChance", wintypes.DWORD),
    ]

class CREATE_THREAD_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("hThread", wintypes.HANDLE),
        ("lpThreadLocalBase", ctypes.c_void_p),
        ("lpStartAddress", ctypes.c_void_p),
    ]

class CREATE_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("hFile", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("lpBaseOfImage", ctypes.c_void_p),
        ("dwDebugInfoFileOffset", wintypes.DWORD),
        ("nDebugInfoSize", wintypes.DWORD),
        ("lpThreadLocalBase", ctypes.c_void_p),
        ("lpStartAddress", ctypes.c_void_p),
        ("lpImageName", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
    ]

class EXIT_THREAD_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("dwExitCode", wintypes.DWORD),
    ]

class EXIT_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("dwExitCode", wintypes.DWORD),
    ]

class LOAD_DLL_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("hFile", wintypes.HANDLE),
        ("lpBaseOfDll", ctypes.c_void_p),
        ("dwDebugInfoFileOffset", wintypes.DWORD),
        ("nDebugInfoSize", wintypes.DWORD),
        ("lpImageName", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
    ]

class UNLOAD_DLL_DEBUG_INFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
    ]

class OUTPUT_DEBUG_STRING_INFO(ctypes.Structure):
    _fields_ = [
        ("lpDebugStringData", ctypes.c_void_p),
        ("fUnicode", wintypes.WORD),
        ("nDebugStringLength", wintypes.WORD),
    ]

class RIP_INFO(ctypes.Structure):
    _fields_ = [
        ("dwError", wintypes.DWORD),
        ("dwType", wintypes.DWORD),
    ]

class DEBUG_EVENT_UNION(ctypes.Union):
    _fields_ = [
        ("Exception", EXCEPTION_DEBUG_INFO),
        ("CreateThread", CREATE_THREAD_DEBUG_INFO),
        ("CreateProcessInfo", CREATE_PROCESS_DEBUG_INFO),
        ("ExitThread", EXIT_THREAD_DEBUG_INFO),
        ("ExitProcess", EXIT_PROCESS_DEBUG_INFO),
        ("LoadDll", LOAD_DLL_DEBUG_INFO),
        ("UnloadDll", UNLOAD_DLL_DEBUG_INFO),
        ("DebugString", OUTPUT_DEBUG_STRING_INFO),
        ("RipInfo", RIP_INFO),
    ]

class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [
        ("dwDebugEventCode", wintypes.DWORD),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
        ("u", DEBUG_EVENT_UNION),
    ]

def read_process_memory(hProcess, address, size):
    buffer = ctypes.create_string_buffer(size)
    bytesRead = ctypes.c_size_t()
    if kernel32.ReadProcessMemory(hProcess, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytesRead)):
        return buffer.raw[:bytesRead.value]
    return b""

def psutil_daemon(pid, client, stop_event):
    import psutil
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
        
    seen_files = set()
    seen_conns = set()
    
    while not stop_event.is_set():
        try:
            # Poll network
            conns = proc.connections(kind='all')
            for c in conns:
                conn_id = f"{c.laddr}-{c.raddr}-{c.status}"
                if conn_id not in seen_conns:
                    seen_conns.add(conn_id)
                    addr = str(c.raddr) if c.raddr else str(c.laddr)
                    client.send("Network", "connect", {"address": f"{c.status} {addr}"})
                    
            # Poll files
            files = proc.open_files()
            for f in files:
                if f.path not in seen_files:
                    seen_files.add(f.path)
                    client.send("Disk", "open", {"file": f.path, "mode": f.mode if hasattr(f, 'mode') else 'r'})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        except Exception:
            pass
        
        time.sleep(0.1)

class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]

def debug_process(command, client):
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()

    # Create Pipe for stdout/stderr
    hReadPipe = wintypes.HANDLE()
    hWritePipe = wintypes.HANDLE()
    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.bInheritHandle = True
    sa.lpSecurityDescriptor = None

    if kernel32.CreatePipe(ctypes.byref(hReadPipe), ctypes.byref(hWritePipe), ctypes.byref(sa), 0):
        # Ensure the read handle to the pipe is not inherited
        kernel32.SetHandleInformation(hReadPipe, 1, 0) # HANDLE_FLAG_INHERIT = 1
        
        si.hStdError = hWritePipe
        si.hStdOutput = hWritePipe
        si.dwFlags |= 0x00000100 # STARTF_USESTDHANDLES

    creation_flags = DEBUG_PROCESS

    # Convert command list to string for Windows
    import shutil
    resolved_exe = shutil.which(command[0])
    if resolved_exe:
        command[0] = resolved_exe
        
    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in command)

    if not kernel32.CreateProcessW(
        None, ctypes.c_wchar_p(cmd_str), None, None, True, # bInheritHandles=True
        creation_flags, None, None, ctypes.byref(si), ctypes.byref(pi)):
        err = ctypes.GetLastError()
        err_msg = f"Failed to CreateProcess: {err}"
        if err == 2:
            err_msg += f" (File Not Found). Windows could not locate the executable '{command[0]}'. Make sure the path is correct."
        elif err == 5:
            err_msg += " (Access Denied). The executable may require Administrator privileges, or it may be blocked by Windows Defender/DRM. Try running h4-debug from an Administrator terminal."
        elif err == 740:
            err_msg += " (Elevation Required). The executable requires Administrator privileges. Please run h4-debug from an Administrator terminal."
        client.send("System", "error", {"text": err_msg})
        print(f"[h4-debug] {err_msg}")
        if hWritePipe:
            kernel32.CloseHandle(hReadPipe)
            kernel32.CloseHandle(hWritePipe)
        return

    # Close our write end of the pipe so the read thread unblocks when the process exits
    if hWritePipe:
        kernel32.CloseHandle(hWritePipe)
        
    def stream_pipe(handle, client):
        buffer = ctypes.create_string_buffer(4096)
        bytes_read = wintypes.DWORD()
        while True:
            if not kernel32.ReadFile(handle, buffer, 4096, ctypes.byref(bytes_read), None) or bytes_read.value == 0:
                break
            text = buffer.raw[:bytes_read.value].decode('utf-8', 'replace').strip('\r\n\x00')
            if text:
                for line in text.splitlines():
                    client.send("Console", "stdout", {"text": line})
        kernel32.CloseHandle(handle)
        
    pipe_thread = None
    if hReadPipe:
        pipe_thread = threading.Thread(target=stream_pipe, args=(hReadPipe, client), daemon=True)
        pipe_thread.start()

    process_handle = None
    debug_event = DEBUG_EVENT()
    
    daemon_stop_event = threading.Event()
    daemon_thread = None

    while True:
        if not kernel32.WaitForDebugEvent(ctypes.byref(debug_event), 1000): # 1 sec timeout to yield
            # Check if process exited
            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(pi.hProcess, ctypes.byref(exit_code)) and exit_code.value != 259: # STILL_ACTIVE
                break
            continue

        continue_status = DBG_CONTINUE

        if debug_event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT:
            process_handle = debug_event.u.CreateProcessInfo.hProcess
            client.send("System", "info", {"text": f"Process Created: PID {debug_event.dwProcessId}"})
            
            # Start psutil daemon for disk and network tracking
            daemon_thread = threading.Thread(target=psutil_daemon, args=(debug_event.dwProcessId, client, daemon_stop_event), daemon=True)
            daemon_thread.start()
            
            if debug_event.u.CreateProcessInfo.hFile:
                kernel32.CloseHandle(debug_event.u.CreateProcessInfo.hFile)

        elif debug_event.dwDebugEventCode == LOAD_DLL_DEBUG_EVENT:
            if debug_event.u.LoadDll.hFile:
                kernel32.CloseHandle(debug_event.u.LoadDll.hFile)
            # Address resolution of DLL names can be complex in Win32, so we just log the event natively.
            # Real debuggers use GetMappedFileName on the lpBaseOfDll.
            pass # Keep output clean unless we resolve name

        elif debug_event.dwDebugEventCode == OUTPUT_DEBUG_STRING_EVENT:
            if process_handle:
                info = debug_event.u.DebugString
                data = read_process_memory(process_handle, info.lpDebugStringData, info.nDebugStringLength * (2 if info.fUnicode else 1))
                if data:
                    text = data.decode('utf-16' if info.fUnicode else 'ansi', 'replace').strip('\x00\r\n')
                    if text:
                        client.send("Console", "stdout", {"text": f"[DEBUG] {text}"})

        elif debug_event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT:
            exc = debug_event.u.Exception.ExceptionRecord.ExceptionCode
            # Ignore standard breakpoint exceptions (0x80000003)
            if exc != 0x80000003:
                # Log exception
                continue_status = DBG_EXCEPTION_NOT_HANDLED

        elif debug_event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT:
            client.send("System", "info", {"text": f"Process Exited with code {debug_event.u.ExitProcess.dwExitCode}"})
            daemon_stop_event.set()
            kernel32.ContinueDebugEvent(debug_event.dwProcessId, debug_event.dwThreadId, continue_status)
            break

        kernel32.ContinueDebugEvent(debug_event.dwProcessId, debug_event.dwThreadId, continue_status)
    
    daemon_stop_event.set()
    if daemon_thread:
        daemon_thread.join(timeout=1.0)
        
    if process_handle:
        kernel32.CloseHandle(pi.hThread)
        kernel32.CloseHandle(pi.hProcess)
