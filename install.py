#!/usr/bin/env python3
"""peon-ping cross-platform installer.

Works both via local clone and remote download (urllib).
Re-running updates core files; config/state are preserved.
"""
import sys
import os
import json
import glob
import shutil
import subprocess

REPO_BASE = 'https://raw.githubusercontent.com/tonyyont/peon-ping/main'
PACKS = [
    'peon', 'peon_fr', 'peon_pl', 'peasant', 'peasant_fr',
    'ra2_soviet_engineer', 'sc_battlecruiser', 'sc_kerrigan',
]

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
HOME = os.path.expanduser('~')
INSTALL_DIR = os.path.join(HOME, '.claude', 'hooks', 'peon-ping')
SETTINGS = os.path.join(HOME, '.claude', 'settings.json')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def download(url, dest):
    """Download a file from url to dest using urllib."""
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'peon-ping-installer'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, 'wb') as f:
        f.write(data)


def find_python_cmd():
    """Return the python command name available on this system."""
    for cmd in ['python3', 'python']:
        try:
            subprocess.run([cmd, '--version'], capture_output=True, check=True)
            return cmd
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return None


def find_script_dir():
    """Detect if running from a local clone."""
    candidate = os.path.dirname(os.path.abspath(__file__))
    if os.path.isfile(os.path.join(candidate, 'peon.py')):
        return candidate
    return None


def check_prerequisites():
    """Verify platform requirements."""
    supported = ('mac', 'wsl', 'windows')
    if PLATFORM not in supported:
        print(f'Error: peon-ping requires macOS, WSL, or Windows. Detected: {PLATFORM}')
        sys.exit(1)

    if find_python_cmd() is None:
        print('Error: python3 or python is required')
        sys.exit(1)

    if PLATFORM == 'mac':
        if shutil.which('afplay') is None:
            print('Error: afplay is required (should be built into macOS)')
            sys.exit(1)
    elif PLATFORM == 'wsl':
        if shutil.which('powershell.exe') is None:
            print('Error: powershell.exe is required (should be available in WSL)')
            sys.exit(1)
        if shutil.which('wslpath') is None:
            print('Error: wslpath is required (should be built into WSL)')
            sys.exit(1)
    elif PLATFORM == 'windows':
        if shutil.which('powershell') is None and shutil.which('powershell.exe') is None:
            print('Error: powershell is required (should be built into Windows)')
            sys.exit(1)

    claude_dir = os.path.join(HOME, '.claude')
    if not os.path.isdir(claude_dir):
        print(f'Error: {claude_dir} not found. Is Claude Code installed?')
        sys.exit(1)


# ---------------------------------------------------------------------------
# Core files to install
# ---------------------------------------------------------------------------

CORE_FILES = ['peon.py', 'peon.sh', 'completions.bash', 'VERSION', 'uninstall.sh', 'uninstall.py']


def install_core_files(script_dir, updating):
    """Copy or download core files and packs."""
    for pack in PACKS:
        os.makedirs(os.path.join(INSTALL_DIR, 'packs', pack, 'sounds'), exist_ok=True)

    if script_dir:
        # Local clone — copy files directly
        for pack in PACKS:
            src_pack = os.path.join(script_dir, 'packs', pack)
            dst_pack = os.path.join(INSTALL_DIR, 'packs', pack)
            if os.path.isdir(src_pack):
                # Copy manifest
                src_manifest = os.path.join(src_pack, 'manifest.json')
                if os.path.isfile(src_manifest):
                    shutil.copy2(src_manifest, os.path.join(dst_pack, 'manifest.json'))
                # Copy sounds
                src_sounds = os.path.join(src_pack, 'sounds')
                if os.path.isdir(src_sounds):
                    for f in os.listdir(src_sounds):
                        shutil.copy2(os.path.join(src_sounds, f),
                                     os.path.join(dst_pack, 'sounds', f))

        for fname in CORE_FILES:
            src = os.path.join(script_dir, fname)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(INSTALL_DIR, fname))

        if not updating:
            config_src = os.path.join(script_dir, 'config.json')
            if os.path.isfile(config_src):
                shutil.copy2(config_src, os.path.join(INSTALL_DIR, 'config.json'))
    else:
        # Remote — download from GitHub
        print('Downloading from GitHub...')
        for fname in CORE_FILES:
            download(f'{REPO_BASE}/{fname}', os.path.join(INSTALL_DIR, fname))

        for pack in PACKS:
            manifest_path = os.path.join(INSTALL_DIR, 'packs', pack, 'manifest.json')
            download(f'{REPO_BASE}/packs/{pack}/manifest.json', manifest_path)
            # Parse manifest to get sound files
            with open(manifest_path) as f:
                manifest = json.load(f)
            seen = set()
            for cat in manifest.get('categories', {}).values():
                for s in cat.get('sounds', []):
                    fname = s['file']
                    if fname not in seen:
                        seen.add(fname)
                        download(
                            f'{REPO_BASE}/packs/{pack}/sounds/{fname}',
                            os.path.join(INSTALL_DIR, 'packs', pack, 'sounds', fname),
                        )

        if not updating:
            download(f'{REPO_BASE}/config.json', os.path.join(INSTALL_DIR, 'config.json'))

    # Make peon.sh executable on unix
    if PLATFORM != 'windows':
        peon_sh = os.path.join(INSTALL_DIR, 'peon.sh')
        if os.path.isfile(peon_sh):
            os.chmod(peon_sh, 0o755)


def install_skill(script_dir):
    """Install the peon-ping-toggle skill."""
    skill_dir = os.path.join(HOME, '.claude', 'skills', 'peon-ping-toggle')
    os.makedirs(skill_dir, exist_ok=True)

    if script_dir:
        src = os.path.join(script_dir, 'skills', 'peon-ping-toggle', 'SKILL.md')
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(skill_dir, 'SKILL.md'))
        else:
            print('Warning: skills/peon-ping-toggle not found in local clone, skipping skill install')
    else:
        download(f'{REPO_BASE}/skills/peon-ping-toggle/SKILL.md',
                 os.path.join(skill_dir, 'SKILL.md'))


def register_hooks():
    """Register peon-ping hooks in Claude Code settings.json."""
    print()
    print('Updating Claude Code hooks in settings.json...')

    if os.path.isfile(SETTINGS):
        with open(SETTINGS) as f:
            settings = json.load(f)
    else:
        settings = {}

    hooks = settings.setdefault('hooks', {})

    python_cmd = find_python_cmd()
    hook_script = os.path.join(INSTALL_DIR, 'peon.py')
    hook_cmd = f'{python_cmd} {hook_script}'

    peon_hook = {'type': 'command', 'command': hook_cmd, 'timeout': 10}
    peon_entry = {'matcher': '', 'hooks': [peon_hook]}

    events = ['SessionStart', 'UserPromptSubmit', 'Stop', 'Notification', 'PermissionRequest']
    for event in events:
        event_hooks = hooks.get(event, [])
        # Remove existing notify.sh, peon.sh, or peon.py entries
        event_hooks = [
            h for h in event_hooks
            if not any(
                'notify.sh' in hk.get('command', '') or
                'peon.sh' in hk.get('command', '') or
                'peon.py' in hk.get('command', '')
                for hk in h.get('hooks', [])
            )
        ]
        event_hooks.append(peon_entry)
        hooks[event] = event_hooks

    settings['hooks'] = hooks
    with open(SETTINGS, 'w') as f:
        json.dump(settings, f, indent=2)
        f.write('\n')

    print('Hooks registered for: ' + ', '.join(events))


def add_shell_alias():
    """Add the peon alias to shell RC files (macOS/WSL) or create peon.cmd (Windows)."""
    if PLATFORM == 'windows':
        # Create peon.cmd wrapper
        python_cmd = find_python_cmd()
        peon_script = os.path.join(INSTALL_DIR, 'peon.py')
        cmd_path = os.path.join(INSTALL_DIR, 'peon.cmd')
        with open(cmd_path, 'w') as f:
            f.write('@echo off\n')
            f.write(f'{python_cmd} "{peon_script}" %*\n')
        print(f'Created {cmd_path}')
        print(f'  Add {INSTALL_DIR} to your PATH for the "peon" command,')
        print(f'  or run: {python_cmd} "{peon_script}" --help')
    else:
        # Unix: add alias to shell RC files
        python_cmd = find_python_cmd()
        alias_line = f'alias peon="{python_cmd} ~/.claude/hooks/peon-ping/peon.py"'
        completion_line = '[ -f ~/.claude/hooks/peon-ping/completions.bash ] && source ~/.claude/hooks/peon-ping/completions.bash'

        for rcname in ['.zshrc', '.bashrc']:
            rcfile = os.path.join(HOME, rcname)
            if not os.path.isfile(rcfile):
                continue
            content = open(rcfile).read()

            lines_to_add = []
            if 'alias peon=' not in content:
                lines_to_add.append(f'\n# peon-ping quick controls\n{alias_line}')
                print(f'Added peon alias to {rcname}')
            if 'peon-ping/completions.bash' not in content:
                lines_to_add.append(completion_line)
                print(f'Added tab completion to {rcname}')

            if lines_to_add:
                with open(rcfile, 'a') as f:
                    f.write('\n'.join(lines_to_add) + '\n')


def verify_sounds():
    """Check that sound files were installed."""
    print()
    for pack in PACKS:
        sound_dir = os.path.join(INSTALL_DIR, 'packs', pack, 'sounds')
        count = 0
        if os.path.isdir(sound_dir):
            for f in os.listdir(sound_dir):
                if f.endswith(('.wav', '.mp3', '.ogg')):
                    count += 1
        if count == 0:
            print(f'[{pack}] Warning: No sound files found!')
        else:
            print(f'[{pack}] {count} sound files installed.')


def backup_notify_sh():
    """Backup existing notify.sh on fresh install."""
    notify_sh = os.path.join(HOME, '.claude', 'hooks', 'notify.sh')
    if os.path.isfile(notify_sh):
        backup = notify_sh + '.backup'
        shutil.copy2(notify_sh, backup)
        print()
        print('Backed up notify.sh \u2192 notify.sh.backup')


def test_sound():
    """Play a test sound to verify audio works."""
    print()
    print('Testing sound...')
    config_path = os.path.join(INSTALL_DIR, 'config.json')
    try:
        active_pack = json.load(open(config_path)).get('active_pack', 'peon')
    except Exception:
        active_pack = 'peon'

    pack_dir = os.path.join(INSTALL_DIR, 'packs', active_pack, 'sounds')
    test_file = None
    if os.path.isdir(pack_dir):
        for f in sorted(os.listdir(pack_dir)):
            if f.endswith(('.wav', '.mp3', '.ogg')):
                test_file = os.path.join(pack_dir, f)
                break

    if not test_file:
        print('Warning: No sound files found. Sounds may not play.')
        return

    if PLATFORM == 'mac':
        subprocess.run(['afplay', '-v', '0.3', test_file],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif PLATFORM == 'wsl':
        wpath = subprocess.check_output(['wslpath', '-w', test_file],
                                        stderr=subprocess.DEVNULL).decode().strip()
        wpath = wpath.replace('\\', '/')
        ps_cmd = (
            "Add-Type -AssemblyName PresentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([Uri]::new('file:///{wpath}')); "
            "$p.Volume = 0.3; "
            "Start-Sleep -Milliseconds 200; "
            "$p.Play(); "
            "Start-Sleep -Seconds 3; "
            "$p.Close()"
        )
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif PLATFORM == 'windows':
        wpath = test_file.replace('\\', '/')
        ps_cmd = (
            "Add-Type -AssemblyName PresentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([Uri]::new('file:///{wpath}')); "
            "$p.Volume = 0.3; "
            "Start-Sleep -Milliseconds 200; "
            "$p.Play(); "
            "Start-Sleep -Seconds 3; "
            "$p.Close()"
        )
        subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print('Sound working!')


def init_state(updating):
    """Initialize state file on fresh install."""
    if not updating:
        state_file = os.path.join(INSTALL_DIR, '.state.json')
        with open(state_file, 'w') as f:
            f.write('{}')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Detect update vs fresh install
    updating = os.path.isfile(os.path.join(INSTALL_DIR, 'peon.sh')) or \
               os.path.isfile(os.path.join(INSTALL_DIR, 'peon.py'))

    if updating:
        print('=== peon-ping updater ===')
        print()
        print('Existing install found. Updating...')
    else:
        print('=== peon-ping installer ===')
        print()

    check_prerequisites()

    script_dir = find_script_dir()
    install_core_files(script_dir, updating)
    install_skill(script_dir)
    add_shell_alias()
    verify_sounds()

    if not updating:
        backup_notify_sh()

    register_hooks()
    init_state(updating)
    test_sound()

    print()
    if updating:
        print('=== Update complete! ===')
        print()
        print('Updated: peon.py, peon.sh, manifest.json')
        print('Preserved: config.json, state')
    else:
        print('=== Installation complete! ===')
        print()
        print(f'Config: {os.path.join(INSTALL_DIR, "config.json")}')
        print('  - Adjust volume, toggle categories, switch packs')
        print()
        print(f'Uninstall: python {os.path.join(INSTALL_DIR, "uninstall.py")}')

    print()
    print('Quick controls:')
    print('  /peon-ping-toggle  \u2014 toggle sounds in Claude Code')
    print('  peon --toggle      \u2014 toggle sounds from any terminal')
    print('  peon --status      \u2014 check if sounds are paused')
    print()
    print('Ready to work!')


if __name__ == '__main__':
    main()
