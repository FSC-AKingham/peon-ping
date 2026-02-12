#!/usr/bin/env python3
"""peon-ping: Warcraft III Peon voice lines for Claude Code hooks.

Cross-platform replacement for peon.sh — handles sounds, tab titles,
and notifications on macOS, WSL, and native Windows.
"""
import sys
import os
import json
import re
import random
import time
import glob
import subprocess
import threading
import tempfile

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform():
    if sys.platform == 'darwin':
        return 'mac'
    elif sys.platform == 'win32':
        return 'windows'
    elif sys.platform.startswith('linux'):
        try:
            with open('/proc/version') as f:
                if 'microsoft' in f.read().lower():
                    return 'wsl'
        except OSError:
            pass
        return 'linux'
    return 'unknown'

PLATFORM = detect_platform()

PEON_DIR = os.environ.get('CLAUDE_PEON_DIR',
                          os.path.join(os.path.expanduser('~'), '.claude', 'hooks', 'peon-ping'))
CONFIG = os.path.join(PEON_DIR, 'config.json')
STATE = os.path.join(PEON_DIR, '.state.json')
PAUSED_FILE = os.path.join(PEON_DIR, '.paused')

# ---------------------------------------------------------------------------
# Platform-aware audio playback
# ---------------------------------------------------------------------------

def play_sound(filepath, volume):
    if PLATFORM == 'mac':
        subprocess.Popen(
            ['afplay', '-v', str(volume), filepath],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif PLATFORM == 'wsl':
        wpath = subprocess.check_output(['wslpath', '-w', filepath],
                                        stderr=subprocess.DEVNULL).decode().strip()
        wpath = wpath.replace('\\', '/')
        ps_cmd = (
            "Add-Type -AssemblyName PresentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([Uri]::new('file:///{wpath}')); "
            f"$p.Volume = {volume}; "
            "Start-Sleep -Milliseconds 200; "
            "$p.Play(); "
            "Start-Sleep -Seconds 3; "
            "$p.Close()"
        )
        subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif PLATFORM == 'windows':
        wpath = filepath.replace('\\', '/')
        ps_cmd = (
            "Add-Type -AssemblyName PresentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([Uri]::new('file:///{wpath}')); "
            f"$p.Volume = {volume}; "
            "Start-Sleep -Milliseconds 200; "
            "$p.Play(); "
            "Start-Sleep -Seconds 3; "
            "$p.Close()"
        )
        subprocess.Popen(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

# ---------------------------------------------------------------------------
# Platform-aware notification
# ---------------------------------------------------------------------------

_COLOR_MAP = {
    'red':    (180, 0, 0),
    'blue':   (30, 80, 180),
    'yellow': (200, 160, 0),
}


def send_notification(msg, title, color='red'):
    if PLATFORM == 'mac':
        script = (
            f'display notification "{msg}" with title "{title}"'
        )
        subprocess.Popen(
            ['osascript', '-e', script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    elif PLATFORM in ('wsl', 'windows'):
        rgb_r, rgb_g, rgb_b = _COLOR_MAP.get(color, (180, 0, 0))
        slot_dir = os.path.join(tempfile.gettempdir(), 'peon-ping-popups')
        os.makedirs(slot_dir, exist_ok=True)
        slot = 0
        while True:
            slot_path = os.path.join(slot_dir, f'slot-{slot}')
            try:
                os.mkdir(slot_path)
                break
            except OSError:
                slot += 1
        y_offset = 40 + slot * 90
        # Escape single quotes in msg for PowerShell string
        safe_msg = msg.replace("'", "''")
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) { "
            "  $form = New-Object System.Windows.Forms.Form; "
            "  $form.FormBorderStyle = 'None'; "
            f"  $form.BackColor = [System.Drawing.Color]::FromArgb({rgb_r}, {rgb_g}, {rgb_b}); "
            "  $form.Size = New-Object System.Drawing.Size(500, 80); "
            "  $form.TopMost = $true; "
            "  $form.ShowInTaskbar = $false; "
            "  $form.StartPosition = 'Manual'; "
            "  $form.Location = New-Object System.Drawing.Point("
            f"    ($screen.WorkingArea.X + ($screen.WorkingArea.Width - 500) / 2),"
            f"    ($screen.WorkingArea.Y + {y_offset})"
            "  ); "
            "  $label = New-Object System.Windows.Forms.Label; "
            f"  $label.Text = '{safe_msg}'; "
            "  $label.ForeColor = [System.Drawing.Color]::White; "
            "  $label.Font = New-Object System.Drawing.Font('Segoe UI', 16, [System.Drawing.FontStyle]::Bold); "
            "  $label.TextAlign = 'MiddleCenter'; "
            "  $label.Dock = 'Fill'; "
            "  $form.Controls.Add($label); "
            "  $form.Show() "
            "} "
            "Start-Sleep -Seconds 4; "
            "[System.Windows.Forms.Application]::Exit()"
        )
        ps_exe = 'powershell.exe' if PLATFORM == 'wsl' else 'powershell'

        def _run_notification():
            try:
                subprocess.run(
                    [ps_exe, '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            finally:
                try:
                    os.rmdir(slot_path)
                except OSError:
                    pass

        threading.Thread(target=_run_notification, daemon=True).start()

# ---------------------------------------------------------------------------
# Platform-aware terminal focus check
# ---------------------------------------------------------------------------

_MAC_TERMINALS = {'Terminal', 'iTerm2', 'Warp', 'Alacritty', 'kitty', 'WezTerm', 'Ghostty'}
_WIN_TERMINALS = ['windows terminal', 'powershell', 'cmd.exe', 'command prompt',
                  'conemu', 'cmder', 'alacritty', 'wezterm', 'warp']


def terminal_is_focused():
    if PLATFORM == 'mac':
        try:
            result = subprocess.run(
                ['osascript', '-e',
                 'tell application "System Events" to get name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=2,
            )
            frontmost = result.stdout.strip()
            return frontmost in _MAC_TERMINALS
        except (subprocess.TimeoutExpired, OSError):
            return False
    elif PLATFORM == 'windows':
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.lower()
            return any(t in title for t in _WIN_TERMINALS)
        except Exception:
            return False
    else:
        # WSL / linux / unknown — can't cheaply check; always notify
        return False

# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

def cmd_pause():
    open(PAUSED_FILE, 'w').close()
    print('peon-ping: sounds paused')

def cmd_resume():
    try:
        os.remove(PAUSED_FILE)
    except OSError:
        pass
    print('peon-ping: sounds resumed')

def cmd_toggle():
    if os.path.isfile(PAUSED_FILE):
        cmd_resume()
    else:
        cmd_pause()

def cmd_status():
    if os.path.isfile(PAUSED_FILE):
        print('peon-ping: paused')
    else:
        print('peon-ping: active')

def cmd_packs():
    try:
        active = json.load(open(CONFIG)).get('active_pack', 'peon')
    except Exception:
        active = 'peon'
    packs_dir = os.path.join(PEON_DIR, 'packs')
    for m in sorted(glob.glob(os.path.join(packs_dir, '*', 'manifest.json'))):
        info = json.load(open(m))
        name = info.get('name', os.path.basename(os.path.dirname(m)))
        display = info.get('display_name', name)
        marker = ' *' if name == active else ''
        print(f'  {name:24s} {display}{marker}')

def cmd_pack(pack_arg=None):
    try:
        cfg = json.load(open(CONFIG))
    except Exception:
        cfg = {}
    packs_dir = os.path.join(PEON_DIR, 'packs')
    names = sorted([
        os.path.basename(os.path.dirname(m))
        for m in glob.glob(os.path.join(packs_dir, '*', 'manifest.json'))
    ])
    if not names:
        print('Error: no packs found', file=sys.stderr)
        sys.exit(1)

    if pack_arg is None:
        # Cycle to next pack alphabetically
        active = cfg.get('active_pack', 'peon')
        try:
            idx = names.index(active)
            next_pack = names[(idx + 1) % len(names)]
        except ValueError:
            next_pack = names[0]
    else:
        if pack_arg not in names:
            print(f'Error: pack "{pack_arg}" not found.', file=sys.stderr)
            print(f'Available packs: {", ".join(names)}', file=sys.stderr)
            sys.exit(1)
        next_pack = pack_arg

    cfg['active_pack'] = next_pack
    json.dump(cfg, open(CONFIG, 'w'), indent=2)
    mpath = os.path.join(packs_dir, next_pack, 'manifest.json')
    display = json.load(open(mpath)).get('display_name', next_pack)
    print(f'peon-ping: switched to {next_pack} ({display})')

def cmd_help():
    print("""Usage: peon <command>

Commands:
  --pause        Mute sounds
  --resume       Unmute sounds
  --toggle       Toggle mute on/off
  --status       Check if paused or active
  --packs        List available sound packs
  --pack <name>  Switch to a specific pack
  --pack         Cycle to the next pack
  --help         Show this help""")

# ---------------------------------------------------------------------------
# Update check (non-blocking, once per day on SessionStart)
# ---------------------------------------------------------------------------

def check_for_updates():
    """Run in a background thread."""
    try:
        check_file = os.path.join(PEON_DIR, '.last_update_check')
        now = int(time.time())
        last_check = 0
        if os.path.isfile(check_file):
            try:
                last_check = int(open(check_file).read().strip())
            except (ValueError, OSError):
                pass
        if now - last_check <= 86400:
            return
        with open(check_file, 'w') as f:
            f.write(str(now))

        version_file = os.path.join(PEON_DIR, 'VERSION')
        local_version = ''
        if os.path.isfile(version_file):
            local_version = open(version_file).read().strip()

        import urllib.request
        req = urllib.request.Request(
            'https://raw.githubusercontent.com/tonyyont/peon-ping/main/VERSION',
            headers={'User-Agent': 'peon-ping'},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            remote_version = resp.read().decode().strip()

        update_file = os.path.join(PEON_DIR, '.update_available')
        if remote_version and local_version and remote_version != local_version:
            with open(update_file, 'w') as f:
                f.write(remote_version)
        else:
            try:
                os.remove(update_file)
            except OSError:
                pass
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Project name extraction
# ---------------------------------------------------------------------------

def extract_project_name(cwd):
    if not cwd:
        return 'claude'
    # Handle both / and \ separators
    name = os.path.basename(cwd)
    if not name:
        return 'claude'
    return re.sub(r'[^a-zA-Z0-9 ._-]', '', name) or 'claude'

# ---------------------------------------------------------------------------
# Main hook logic
# ---------------------------------------------------------------------------

def main():
    # Force UTF-8 on Windows where the default console encoding (cp1252)
    # cannot represent characters like ● (U+25CF) and — (U+2014).
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    # --- Handle CLI subcommands (before reading stdin which blocks) ---
    args = sys.argv[1:]
    if args:
        cmd = args[0]
        if cmd == '--pause':
            cmd_pause(); return
        elif cmd == '--resume':
            cmd_resume(); return
        elif cmd == '--toggle':
            cmd_toggle(); return
        elif cmd == '--status':
            cmd_status(); return
        elif cmd == '--packs':
            cmd_packs(); return
        elif cmd == '--pack':
            cmd_pack(args[1] if len(args) > 1 else None); return
        elif cmd in ('--help', '-h'):
            cmd_help(); return
        elif cmd.startswith('--'):
            print(f"Unknown option: {cmd}", file=sys.stderr)
            print("Run 'peon --help' for usage.", file=sys.stderr)
            sys.exit(1)

    # --- Read stdin (hook event JSON from Claude Code) ---
    try:
        input_data = sys.stdin.read()
    except Exception:
        sys.exit(0)

    if not input_data.strip():
        sys.exit(0)

    paused = os.path.isfile(PAUSED_FILE)

    # --- Load config ---
    try:
        cfg = json.load(open(CONFIG))
    except Exception:
        cfg = {}

    if str(cfg.get('enabled', True)).lower() == 'false':
        sys.exit(0)

    volume = cfg.get('volume', 0.5)
    active_pack = cfg.get('active_pack', 'peon')
    pack_rotation = cfg.get('pack_rotation', [])
    annoyed_threshold = int(cfg.get('annoyed_threshold', 3))
    annoyed_window = float(cfg.get('annoyed_window_seconds', 10))
    cats = cfg.get('categories', {})
    cat_enabled = {}
    for c in ['greeting', 'acknowledge', 'complete', 'error', 'permission', 'resource_limit', 'annoyed']:
        cat_enabled[c] = str(cats.get(c, True)).lower() == 'true'

    # --- Parse event JSON ---
    try:
        event_data = json.loads(input_data)
    except json.JSONDecodeError:
        sys.exit(0)

    event = event_data.get('hook_event_name', '')
    ntype = event_data.get('notification_type', '')
    cwd = event_data.get('cwd', '')
    session_id = event_data.get('session_id', '')
    perm_mode = event_data.get('permission_mode', '')

    # --- Load state ---
    try:
        state = json.load(open(STATE))
    except Exception:
        state = {}

    state_dirty = False
    agent_modes = {'delegate'}

    # --- Agent detection ---
    agent_sessions = set(state.get('agent_sessions', []))
    if perm_mode and perm_mode in agent_modes:
        agent_sessions.add(session_id)
        state['agent_sessions'] = list(agent_sessions)
        os.makedirs(os.path.dirname(STATE) or '.', exist_ok=True)
        json.dump(state, open(STATE, 'w'))
        sys.exit(0)
    elif session_id in agent_sessions:
        sys.exit(0)

    # --- Pack rotation: pin a random pack per session ---
    if pack_rotation:
        session_packs = state.get('session_packs', {})
        if session_id in session_packs and session_packs[session_id] in pack_rotation:
            active_pack = session_packs[session_id]
        else:
            active_pack = random.choice(pack_rotation)
            session_packs[session_id] = active_pack
            state['session_packs'] = session_packs
            state_dirty = True

    # --- Project name ---
    project = extract_project_name(cwd)

    # --- Event routing ---
    category = ''
    status = ''
    marker = ''
    notify = ''
    notify_color = ''
    msg = ''

    if event == 'SessionStart':
        category = 'greeting'
        status = 'ready'
    elif event == 'UserPromptSubmit':
        status = 'working'
        if cat_enabled.get('annoyed', True):
            all_ts = state.get('prompt_timestamps', {})
            if isinstance(all_ts, list):
                all_ts = {}
            now = time.time()
            ts = [t for t in all_ts.get(session_id, []) if now - t < annoyed_window]
            ts.append(now)
            all_ts[session_id] = ts
            state['prompt_timestamps'] = all_ts
            state_dirty = True
            if len(ts) >= annoyed_threshold:
                category = 'annoyed'
    elif event == 'Stop':
        category = 'complete'
        status = 'done'
        marker = '\u25cf '
        notify = '1'
        notify_color = 'blue'
        msg = project + '  \u2014  Task complete'
    elif event == 'Notification':
        if ntype == 'permission_prompt':
            category = 'permission'
            status = 'needs approval'
            marker = '\u25cf '
            notify = '1'
            notify_color = 'red'
            msg = project + '  \u2014  Permission needed'
        elif ntype == 'idle_prompt':
            status = 'done'
            marker = '\u25cf '
            notify = '1'
            notify_color = 'yellow'
            msg = project + '  \u2014  Waiting for input'
        else:
            sys.exit(0)
    elif event == 'PermissionRequest':
        category = 'permission'
        status = 'needs approval'
        marker = '\u25cf '
        notify = '1'
        notify_color = 'red'
        msg = project + '  \u2014  Permission needed'
    else:
        # Unknown event — exit cleanly
        sys.exit(0)

    # --- Check if category is enabled ---
    if category and not cat_enabled.get(category, True):
        category = ''

    # --- Pick sound (skip if no category or paused) ---
    sound_file = ''
    if category and not paused:
        pack_dir = os.path.join(PEON_DIR, 'packs', active_pack)
        try:
            manifest = json.load(open(os.path.join(pack_dir, 'manifest.json')))
            sounds = manifest.get('categories', {}).get(category, {}).get('sounds', [])
            if sounds:
                last_played = state.get('last_played', {})
                last_file = last_played.get(category, '')
                candidates = sounds if len(sounds) <= 1 else [s for s in sounds if s['file'] != last_file]
                pick = random.choice(candidates)
                last_played[category] = pick['file']
                state['last_played'] = last_played
                state_dirty = True
                sound_file = os.path.join(pack_dir, 'sounds', pick['file'])
        except Exception:
            pass

    # --- Write state once ---
    if state_dirty:
        os.makedirs(os.path.dirname(STATE) or '.', exist_ok=True)
        json.dump(state, open(STATE, 'w'))

    # --- Update check (SessionStart only, non-blocking) ---
    if event == 'SessionStart':
        threading.Thread(target=check_for_updates, daemon=True).start()

    # --- Show update notice (SessionStart only) ---
    if event == 'SessionStart':
        update_file = os.path.join(PEON_DIR, '.update_available')
        if os.path.isfile(update_file):
            try:
                new_ver = open(update_file).read().strip()
                version_file = os.path.join(PEON_DIR, 'VERSION')
                cur_ver = open(version_file).read().strip() if os.path.isfile(version_file) else '?'
                if new_ver:
                    print(f"peon-ping update available: {cur_ver} \u2192 {new_ver} "
                          f"\u2014 run: curl -fsSL https://raw.githubusercontent.com/tonyyont/peon-ping/main/install.sh | bash",
                          file=sys.stderr)
            except Exception:
                pass

    # --- Show pause status on SessionStart ---
    if event == 'SessionStart' and paused:
        print("peon-ping: sounds paused \u2014 run 'peon --resume' or '/peon-ping-toggle' to unpause",
              file=sys.stderr)

    # --- Build and set tab title ---
    title = f'{marker}{project}: {status}'
    if title.strip():
        sys.stdout.write(f'\033]0;{title}\007')
        sys.stdout.flush()

    # --- Play sound ---
    if sound_file and os.path.isfile(sound_file):
        play_sound(sound_file, volume)

    # --- Smart notification: only when terminal is NOT frontmost ---
    if notify and not paused and PLATFORM != 'windows':
        if not terminal_is_focused():
            send_notification(msg, title, notify_color or 'red')

    # Give background threads a moment to start (matches `wait` in peon.sh)
    time.sleep(0.1)


if __name__ == '__main__':
    main()
