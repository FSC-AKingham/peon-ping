"""Shared fixtures for peon-ping pytest tests."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

# Locate peon.py relative to this file
PEON_PY = os.path.join(os.path.dirname(__file__), '..', 'peon.py')

PEON_MANIFEST = {
    "name": "peon",
    "display_name": "Orc Peon",
    "categories": {
        "greeting": {
            "sounds": [
                {"file": "Hello1.wav", "line": "Ready to work?"},
                {"file": "Hello2.wav", "line": "Yes?"},
            ]
        },
        "acknowledge": {
            "sounds": [
                {"file": "Ack1.wav", "line": "Work, work."},
            ]
        },
        "complete": {
            "sounds": [
                {"file": "Done1.wav", "line": "Something need doing?"},
                {"file": "Done2.wav", "line": "Ready to work?"},
            ]
        },
        "error": {
            "sounds": [
                {"file": "Error1.wav", "line": "Me not that kind of orc!"},
            ]
        },
        "permission": {
            "sounds": [
                {"file": "Perm1.wav", "line": "Something need doing?"},
                {"file": "Perm2.wav", "line": "Hmm?"},
            ]
        },
        "annoyed": {
            "sounds": [
                {"file": "Angry1.wav", "line": "Me busy, leave me alone!"},
            ]
        },
    },
}

KERRIGAN_MANIFEST = {
    "name": "sc_kerrigan",
    "display_name": "Sarah Kerrigan (StarCraft)",
    "categories": {
        "greeting": {
            "sounds": [
                {"file": "Hello1.wav", "line": "What now?"},
            ]
        },
        "complete": {
            "sounds": [
                {"file": "Done1.wav", "line": "I gotcha."},
            ]
        },
    },
}

DEFAULT_CONFIG = {
    "active_pack": "peon",
    "volume": 0.5,
    "enabled": True,
    "categories": {
        "greeting": True,
        "acknowledge": True,
        "complete": True,
        "error": True,
        "permission": True,
        "resource_limit": True,
        "annoyed": True,
    },
    "annoyed_threshold": 3,
    "annoyed_window_seconds": 10,
}

PEON_SOUNDS = [
    'Hello1.wav', 'Hello2.wav', 'Ack1.wav', 'Done1.wav', 'Done2.wav',
    'Error1.wav', 'Perm1.wav', 'Perm2.wav', 'Angry1.wav',
]

KERRIGAN_SOUNDS = ['Hello1.wav', 'Done1.wav']


@pytest.fixture
def peon_dir(tmp_path):
    """Create an isolated peon-ping test environment."""
    d = tmp_path / 'peon-ping'
    d.mkdir()

    # Peon pack
    peon_sounds = d / 'packs' / 'peon' / 'sounds'
    peon_sounds.mkdir(parents=True)
    (d / 'packs' / 'peon' / 'manifest.json').write_text(json.dumps(PEON_MANIFEST))
    for f in PEON_SOUNDS:
        (peon_sounds / f).write_bytes(b'')

    # Kerrigan pack
    kerr_sounds = d / 'packs' / 'sc_kerrigan' / 'sounds'
    kerr_sounds.mkdir(parents=True)
    (d / 'packs' / 'sc_kerrigan' / 'manifest.json').write_text(json.dumps(KERRIGAN_MANIFEST))
    for f in KERRIGAN_SOUNDS:
        (kerr_sounds / f).write_bytes(b'')

    # Config
    (d / 'config.json').write_text(json.dumps(DEFAULT_CONFIG))

    # State
    (d / '.state.json').write_text('{}')

    # VERSION
    (d / 'VERSION').write_text('1.0.0')

    return d


def run_peon(peon_dir, json_input, args=None):
    """Run peon.py with given stdin JSON, returning (exit_code, stdout, stderr).

    Uses CLAUDE_PEON_DIR to point at the test directory.
    Mocks subprocess.Popen so no real audio/notifications fire.
    """
    cmd_args = args or []
    env = os.environ.copy()
    env['CLAUDE_PEON_DIR'] = str(peon_dir)

    proc = subprocess.run(
        [sys.executable, PEON_PY] + cmd_args,
        input=json_input,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        encoding='utf-8',
        errors='replace',
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_peon_cli(peon_dir, *args):
    """Run peon.py with CLI arguments (no stdin)."""
    env = os.environ.copy()
    env['CLAUDE_PEON_DIR'] = str(peon_dir)

    proc = subprocess.run(
        [sys.executable, PEON_PY] + list(args),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        encoding='utf-8',
        errors='replace',
    )
    return proc.returncode, proc.stdout, proc.stderr
