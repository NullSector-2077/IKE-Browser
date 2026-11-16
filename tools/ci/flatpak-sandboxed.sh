#!/bin/bash
# Runs a command inside the installed I.K.E. Flatpak with Chromium's sandbox
# ON, in a CI container (.github/workflows/flatpak.yml). Runs as root and
# starts the Flatpak as an ordinary user, because Chromium refuses to start
# its sandbox as root. Chromium's sandbox inside Flatpak (the patches of the
# Qt WebEngine base application) starts its processes through the Flatpak
# portal (org.freedesktop.portal.Flatpak) on the session bus; the container
# has no desktop session, so a private session bus and Flatpak's own portal
# service are started for the command.
#
#   tools/ci/flatpak-sandboxed.sh APP_ID COMMAND [ARGS...]
#
# The command runs with --command=COMMAND, the checkout shared read-write.
set -euo pipefail
app="$1"; shift
cmd="$1"; shift
uid=1001

# Ubuntu's kernel lets only programs with an AppArmor profile create user
# namespaces; bubblewrap, which Flatpak uses, needs them for a normal user.
sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 >/dev/null 2>&1 || true
if ! getent passwd "$uid" >/dev/null; then
    echo "tester:x:$uid:$uid::/home/tester:/bin/bash" >> /etc/passwd
    echo "tester:x:$uid:" >> /etc/group
fi
mkdir -p /home/tester /tmp/xdg-tester
chown "$uid:$uid" /home/tester /tmp/xdg-tester
chmod 700 /tmp/xdg-tester
chmod -R a+rwX "$PWD"

portal=$(find / -xdev -type f -name flatpak-portal 2>/dev/null | head -n1 || true)
test -n "$portal" || { echo "Flatpak's portal service not found"; exit 1; }

python3 - "$uid" "$portal" "$app" "$cmd" "$PWD" "$@" <<'EOF'
import os, sys
uid, portal, app, cmd, cwd, *args = sys.argv[1:]
uid = int(uid)
os.setgroups([])
os.setgid(uid)
os.setuid(uid)
env = {k: v for k, v in os.environ.items() if not k.startswith(("DBUS_", "XDG_"))}
env.update(HOME="/home/tester", USER="tester", LOGNAME="tester", XDG_RUNTIME_DIR="/tmp/xdg-tester")
inner = ('"$0" --replace & sleep 2; exec flatpak run --filesystem="$1" --env=QT_QPA_PLATFORM=offscreen '
         '--cwd="$1" --command="$2" "$3" "${@:4}"')
os.chdir(cwd)
os.execvpe("dbus-run-session", ["dbus-run-session", "--", "bash", "-c", inner, portal, cwd, cmd, app, *args], env)
EOF
