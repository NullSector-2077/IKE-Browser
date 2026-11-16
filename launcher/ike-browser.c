/* I.K.E. launcher: starts the browser with the system's python3.
 *
 * Built by the PKGBUILD and installed as /usr/bin/ike-browser.
 * ICE_LIBDIR overrides the installation folder.
 *
 *   gcc -O2 -o ike-browser ike-browser.c
 */
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv) {
    const char *libdir = getenv("ICE_LIBDIR");
    char boot[PATH_MAX];
    char **args;
    int i;

    if (libdir == NULL || *libdir == '\0')
        libdir = "/usr/lib/ike-browser";
    if (snprintf(boot, sizeof boot, "%s/ike_boot.py", libdir) >= (int)sizeof boot)
        return 1;
    args = calloc((size_t)argc + 2, sizeof *args);
    if (args == NULL)
        return 1;
    args[0] = "python3";
    args[1] = boot;
    for (i = 1; i < argc; i++)
        args[i + 1] = argv[i];
    args[argc + 1] = NULL;
    execvp("python3", args);
    fprintf(stderr, "ike-browser: cannot start python3\n");
    return 127;
}
