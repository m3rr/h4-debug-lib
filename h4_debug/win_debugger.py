import ctypes
from ctypes import wintypes
import time
import struct
import sys
import os

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

def debug_process(command, client):
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()

    creation_flags = DEBUG_PROCESS

    # Convert command list to string for Windows
    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in command)

    if not kernel32.CreateProcessW(
        None, ctypes.c_wchar_p(cmd_str), None, None, False,
        creation_flags, None, None, ctypes.byref(si), ctypes.byref(pi)):
        client.send("System", "error", {"text": f"Failed to CreateProcess: {ctypes.GetLastError()}"})
        return

    process_handle = None
    debug_event = DEBUG_EVENT()

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
            kernel32.ContinueDebugEvent(debug_event.dwProcessId, debug_event.dwThreadId, continue_status)
            break

        kernel32.ContinueDebugEvent(debug_event.dwProcessId, debug_event.dwThreadId, continue_status)
    
    if process_handle:
        kernel32.CloseHandle(pi.hThread)
        kernel32.CloseHandle(pi.hProcess)
