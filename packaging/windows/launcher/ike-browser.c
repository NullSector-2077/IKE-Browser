/* I.K.E. launcher for Windows: ike-browser.exe.
 *
 * Starts the browser inside this very process: it loads the Python that the
 * installer put in the "python" folder next to it (python3XX.dll) and runs
 * ike_boot.py with the arguments it was given. So the program the user sees
 * in the task bar, in Task Manager and in a firewall question is
 * "ike-browser.exe" with I.K.E.'s icon and name, not "python.exe"; and no
 * console window opens, because this is a windowed program.
 *
 * It never looks for a Python anywhere else: not on PATH, not in the
 * registry, not in the current folder (SetDllDirectory("") takes the current
 * folder out of the search for libraries). There is no override through the
 * environment either.
 *
 * Built by packaging/windows/build.py:
 *   cl /O2 /W4 /MT /DUNICODE /D_UNICODE ike-browser.c ike-browser.res
 *      /link /SUBSYSTEM:WINDOWS /MANIFEST:EMBED /MANIFESTINPUT:ike-browser.exe.manifest
 *
 * Output: a windowed program has no console. "ike-browser.exe --version"
 * prints where its output is sent: "ike-browser.exe --version | more".
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <wchar.h>

#define PATH_CHARS 32768

typedef int (__cdecl *py_main_t)(int, wchar_t **);

/* What went wrong: to the error output when there is one (a terminal that
 * redirects it, a script, the automatic checks - no window that waits for a
 * click there), otherwise in a message box. */
static int fail(const wchar_t *what) {
    HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
    if (err != NULL && err != INVALID_HANDLE_VALUE) {
        char text[1024];
        DWORD written;
        int n = WideCharToMultiByte(CP_UTF8, 0, what, -1, text, (int)sizeof text - 2, NULL, NULL);
        if (n > 0) {
            text[n - 1] = '\n';
            WriteFile(err, text, (DWORD)n, &written, NULL);
            return 1;
        }
    }
    MessageBoxW(NULL, what, L"I.K.E.", MB_OK | MB_ICONERROR);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show) {
    wchar_t *dir, *path, *boot, **args;
    WIN32_FIND_DATAW found;
    HANDLE search;
    HMODULE python = NULL;
    py_main_t py_main;
    DWORD length;
    int i;

    (void)instance; (void)previous; (void)command_line; (void)show;
    SetDllDirectoryW(L"");

    dir = calloc(PATH_CHARS, sizeof *dir);
    path = calloc(PATH_CHARS, sizeof *path);
    boot = calloc(PATH_CHARS, sizeof *boot);
    args = calloc((size_t)__argc + 2, sizeof *args);
    if (dir == NULL || path == NULL || boot == NULL || args == NULL)
        return 1;

    /* the folder this program lies in */
    length = GetModuleFileNameW(NULL, dir, PATH_CHARS);
    if (length == 0 || length >= PATH_CHARS)
        return fail(L"I.K.E. cannot find its own folder.");
    while (length > 0 && dir[length - 1] != L'\\' && dir[length - 1] != L'/')
        length--;
    if (length == 0)
        return fail(L"I.K.E. cannot find its own folder.");
    dir[length - 1] = L'\0';

    if (swprintf(boot, PATH_CHARS, L"%ls\\ike_boot.py", dir) < 0
            || GetFileAttributesW(boot) == INVALID_FILE_ATTRIBUTES)
        return fail(L"I.K.E. is not complete (ike_boot.py is missing). Please install it again.");

    /* python\python3XX.dll: the one library of that name the installer put there
     * ("python3.dll", without a version, only passes calls on to it) */
    if (swprintf(path, PATH_CHARS, L"%ls\\python\\python3*.dll", dir) < 0)
        return 1;
    search = FindFirstFileW(path, &found);
    if (search != INVALID_HANDLE_VALUE) {
        do {
            if (_wcsicmp(found.cFileName, L"python3.dll") == 0
                    || (found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY))
                continue;
            if (swprintf(path, PATH_CHARS, L"%ls\\python\\%ls", dir, found.cFileName) < 0)
                continue;
            /* its own folder first for the libraries it needs (the C run time) */
            python = LoadLibraryExW(path, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);
        } while (python == NULL && FindNextFileW(search, &found));
        FindClose(search);
    }
    if (python == NULL)
        return fail(L"I.K.E. is not complete (its Python run time is missing). Please install it again.");
    py_main = (py_main_t)GetProcAddress(python, "Py_Main");
    if (py_main == NULL)
        return fail(L"I.K.E. is not complete (its Python run time is damaged). Please install it again.");

    /* ike-browser.exe <arguments>  ->  python ike_boot.py <arguments> */
    args[0] = __wargv[0];
    args[1] = boot;
    for (i = 1; i < __argc; i++)
        args[i + 1] = __wargv[i];
    args[__argc + 1] = NULL;
    return py_main(__argc + 1, args);
}
