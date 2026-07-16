import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
DEBUG_PROCESS = 1

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

def test(cmd):
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()

    cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    print("Executing:", cmd_str)
    
    if not kernel32.CreateProcessW(
        None, ctypes.c_wchar_p(cmd_str), None, None, True,
        DEBUG_PROCESS, None, None, ctypes.byref(si), ctypes.byref(pi)):
        err = ctypes.GetLastError()
        print("Error:", err)
        if err == 5:
            print("ACCESS_DENIED!")
    else:
        print("Success! PID:", pi.dwProcessId)
        kernel32.TerminateProcess(pi.hProcess, 0)
        kernel32.CloseHandle(pi.hProcess)
        kernel32.CloseHandle(pi.hThread)

test(["cmd.exe", "/c", "echo", "hello"])
