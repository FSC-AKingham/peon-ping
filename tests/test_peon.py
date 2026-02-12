"""Cross-platform pytest tests for peon.py.

Port of peon.bats — tests event routing, config, agent detection,
sound picking, annoyed easter egg, pause/resume, pack management,
update notices, and CLI subcommands.

Sound playback is tested indirectly: since peon.py calls subprocess.Popen
for audio and notifications, and the test environment has dummy (empty) sound
files, the subprocess calls will fail silently but the logic paths are still
exercised. The important thing is that peon.py exits 0 and writes correct
state.
"""
import json
import os
import time

import pytest

from conftest import run_peon, run_peon_cli


# ============================================================
# Event routing
# ============================================================

class TestEventRouting:
    def test_session_start_exits_ok(self, peon_dir):
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert rc == 0

    def test_session_start_picks_greeting_sound(self, peon_dir):
        """Verify state shows a greeting sound was picked."""
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'greeting' in state.get('last_played', {})
        assert 'Hello' in state['last_played']['greeting']

    def test_notification_permission_prompt_picks_permission_sound(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"Notification","notification_type":"permission_prompt","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'permission' in state.get('last_played', {})
        assert 'Perm' in state['last_played']['permission']

    def test_permission_request_picks_permission_sound(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"PermissionRequest","tool_name":"Bash","tool_input":{},"cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'permission' in state.get('last_played', {})
        assert 'Perm' in state['last_played']['permission']

    def test_notification_idle_prompt_no_sound(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"Notification","notification_type":"idle_prompt","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        # idle_prompt does not map to a sound category
        assert state.get('last_played', {}) == {}

    def test_stop_picks_complete_sound(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"Stop","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'complete' in state.get('last_played', {})
        assert 'Done' in state['last_played']['complete']

    def test_user_prompt_submit_no_sound_normally(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}

    def test_unknown_event_exits_cleanly(self, peon_dir):
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SomeOtherEvent","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert rc == 0

    def test_unknown_notification_type_exits_cleanly(self, peon_dir):
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"Notification","notification_type":"something_else","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert rc == 0


# ============================================================
# Disabled config
# ============================================================

class TestDisabledConfig:
    def test_enabled_false_skips_everything(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "enabled": False, "active_pack": "peon", "volume": 0.5, "categories": {},
        }))
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert rc == 0
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}

    def test_category_disabled_skips_sound(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "active_pack": "peon", "volume": 0.5, "enabled": True,
            "categories": {"greeting": False},
        }))
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert rc == 0
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}


# ============================================================
# Missing config (defaults)
# ============================================================

class TestMissingConfig:
    def test_missing_config_uses_defaults(self, peon_dir):
        os.remove(peon_dir / 'config.json')
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert rc == 0
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'greeting' in state.get('last_played', {})


# ============================================================
# Agent/teammate detection
# ============================================================

class TestAgentDetection:
    def test_accept_edits_not_suppressed(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"acceptEdits"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'greeting' in state.get('last_played', {})

    def test_delegate_mode_suppresses_sound(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"agent1","permission_mode":"delegate"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}
        assert 'agent1' in state.get('agent_sessions', [])

    def test_agent_session_remembered(self, peon_dir):
        # First event marks as agent
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"agent2","permission_mode":"delegate"}')
        # Second event from same session still suppressed
        run_peon(peon_dir,
            '{"hook_event_name":"Notification","notification_type":"permission_prompt","cwd":"/tmp/myproject","session_id":"agent2","permission_mode":""}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}

    def test_default_permission_mode_not_agent(self, peon_dir):
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'greeting' in state.get('last_played', {})


# ============================================================
# Sound picking (no-repeat)
# ============================================================

class TestSoundPicking:
    def test_avoids_immediate_repeats(self, peon_dir):
        """Run greeting multiple times — should see variety."""
        sounds = []
        for _ in range(10):
            run_peon(peon_dir,
                '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
            state = json.loads((peon_dir / '.state.json').read_text())
            sounds.append(state['last_played']['greeting'])
        # Should have both Hello1.wav and Hello2.wav
        assert len(set(sounds)) > 1

    def test_single_sound_category_works(self, peon_dir):
        """Annoyed has only 1 sound — should not infinite loop."""
        for _ in range(3):
            run_peon(peon_dir,
                '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state['last_played']['annoyed'] == 'Angry1.wav'


# ============================================================
# Annoyed easter egg
# ============================================================

class TestAnnoyed:
    def test_triggers_after_rapid_prompts(self, peon_dir):
        for _ in range(3):
            run_peon(peon_dir,
                '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'annoyed' in state.get('last_played', {})

    def test_does_not_trigger_below_threshold(self, peon_dir):
        for _ in range(2):
            run_peon(peon_dir,
                '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'annoyed' not in state.get('last_played', {})

    def test_disabled_in_config(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "active_pack": "peon", "volume": 0.5, "enabled": True,
            "categories": {"annoyed": False},
            "annoyed_threshold": 3, "annoyed_window_seconds": 10,
        }))
        for _ in range(5):
            run_peon(peon_dir,
                '{"hook_event_name":"UserPromptSubmit","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'annoyed' not in state.get('last_played', {})


# ============================================================
# Update check
# ============================================================

class TestUpdateCheck:
    def test_update_notice_shown(self, peon_dir):
        (peon_dir / '.update_available').write_text('1.1.0')
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert 'update available' in stderr
        assert '1.0.0' in stderr
        assert '1.1.0' in stderr

    def test_no_update_notice_when_no_file(self, peon_dir):
        update_file = peon_dir / '.update_available'
        if update_file.exists():
            update_file.unlink()
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert 'update available' not in stderr

    def test_update_notice_only_on_session_start(self, peon_dir):
        (peon_dir / '.update_available').write_text('1.1.0')
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"Notification","notification_type":"idle_prompt","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert 'update available' not in stderr


# ============================================================
# Project name / tab title
# ============================================================

class TestProjectName:
    def test_project_name_from_cwd(self, peon_dir):
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/Users/dev/my-cool-project","session_id":"s1","permission_mode":"default"}')
        assert rc == 0

    def test_empty_cwd_fallback(self, peon_dir):
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"","session_id":"s1","permission_mode":"default"}')
        assert rc == 0

    def test_windows_cwd(self, peon_dir):
        """Windows paths with backslashes should work."""
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"C:\\\\Users\\\\dev\\\\my-project","session_id":"s1","permission_mode":"default"}')
        assert rc == 0


# ============================================================
# Volume passthrough
# ============================================================

class TestVolume:
    def test_volume_from_config(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "active_pack": "peon", "volume": 0.3, "enabled": True, "categories": {},
        }))
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/p","session_id":"s1","permission_mode":"default"}')
        assert rc == 0
        # Volume is used in the subprocess call; we verify via state that a sound was picked
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'greeting' in state.get('last_played', {})


# ============================================================
# Pause / mute feature
# ============================================================

class TestPauseMute:
    def test_toggle_creates_paused_file(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--toggle')
        assert rc == 0
        assert 'sounds paused' in stdout
        assert (peon_dir / '.paused').exists()

    def test_toggle_removes_paused_file(self, peon_dir):
        (peon_dir / '.paused').write_text('')
        rc, stdout, stderr = run_peon_cli(peon_dir, '--toggle')
        assert rc == 0
        assert 'sounds resumed' in stdout
        assert not (peon_dir / '.paused').exists()

    def test_pause_creates_file(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--pause')
        assert rc == 0
        assert 'sounds paused' in stdout
        assert (peon_dir / '.paused').exists()

    def test_resume_removes_file(self, peon_dir):
        (peon_dir / '.paused').write_text('')
        rc, stdout, stderr = run_peon_cli(peon_dir, '--resume')
        assert rc == 0
        assert 'sounds resumed' in stdout
        assert not (peon_dir / '.paused').exists()

    def test_status_reports_paused(self, peon_dir):
        (peon_dir / '.paused').write_text('')
        rc, stdout, stderr = run_peon_cli(peon_dir, '--status')
        assert rc == 0
        assert 'paused' in stdout

    def test_status_reports_active(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--status')
        assert rc == 0
        assert 'active' in stdout

    def test_paused_suppresses_sound(self, peon_dir):
        (peon_dir / '.paused').write_text('')
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}

    def test_paused_session_start_shows_stderr(self, peon_dir):
        (peon_dir / '.paused').write_text('')
        rc, stdout, stderr = run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        assert 'sounds paused' in stderr

    def test_paused_suppresses_notification_sound(self, peon_dir):
        (peon_dir / '.paused').write_text('')
        run_peon(peon_dir,
            '{"hook_event_name":"Notification","notification_type":"permission_prompt","cwd":"/tmp/myproject","session_id":"s1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state.get('last_played', {}) == {}


# ============================================================
# --packs (list packs)
# ============================================================

class TestPacksList:
    def test_lists_all_packs(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--packs')
        assert rc == 0
        assert 'peon' in stdout
        assert 'sc_kerrigan' in stdout

    def test_marks_active_pack(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--packs')
        assert rc == 0
        assert 'Orc Peon *' in stdout
        # sc_kerrigan should NOT be marked
        for line in stdout.splitlines():
            if 'sc_kerrigan' in line:
                assert '*' not in line

    def test_marks_correct_pack_after_switch(self, peon_dir):
        run_peon_cli(peon_dir, '--pack', 'sc_kerrigan')
        rc, stdout, stderr = run_peon_cli(peon_dir, '--packs')
        assert rc == 0
        assert 'Sarah Kerrigan (StarCraft) *' in stdout


# ============================================================
# --pack <name> (set specific pack)
# ============================================================

class TestPackSwitch:
    def test_switch_to_valid_pack(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--pack', 'sc_kerrigan')
        assert rc == 0
        assert 'switched to sc_kerrigan' in stdout
        assert 'Sarah Kerrigan' in stdout
        cfg = json.loads((peon_dir / 'config.json').read_text())
        assert cfg['active_pack'] == 'sc_kerrigan'

    def test_preserves_other_config_fields(self, peon_dir):
        run_peon_cli(peon_dir, '--pack', 'sc_kerrigan')
        cfg = json.loads((peon_dir / 'config.json').read_text())
        assert cfg['volume'] == 0.5

    def test_errors_on_nonexistent_pack(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--pack', 'nonexistent')
        assert rc != 0
        assert 'not found' in stderr
        assert 'Available packs' in stderr

    def test_does_not_modify_config_on_invalid_pack(self, peon_dir):
        run_peon_cli(peon_dir, '--pack', 'nonexistent')
        cfg = json.loads((peon_dir / 'config.json').read_text())
        assert cfg['active_pack'] == 'peon'


# ============================================================
# --pack (cycle, no argument)
# ============================================================

class TestPackCycle:
    def test_cycles_to_next_pack(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--pack')
        assert rc == 0
        assert 'switched to sc_kerrigan' in stdout

    def test_wraps_around(self, peon_dir):
        run_peon_cli(peon_dir, '--pack', 'sc_kerrigan')
        rc, stdout, stderr = run_peon_cli(peon_dir, '--pack')
        assert rc == 0
        assert 'switched to peon' in stdout

    def test_updates_config(self, peon_dir):
        run_peon_cli(peon_dir, '--pack')
        cfg = json.loads((peon_dir / 'config.json').read_text())
        assert cfg['active_pack'] == 'sc_kerrigan'


# ============================================================
# --help
# ============================================================

class TestHelp:
    def test_shows_pack_commands(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--help')
        assert rc == 0
        assert '--packs' in stdout
        assert '--pack' in stdout

    def test_unknown_option_error(self, peon_dir):
        rc, stdout, stderr = run_peon_cli(peon_dir, '--foobar')
        assert rc != 0
        assert 'Unknown option' in stderr
        assert 'peon --help' in stderr


# ============================================================
# Pack rotation
# ============================================================

class TestPackRotation:
    def test_picks_from_rotation_list(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "active_pack": "peon", "volume": 0.5, "enabled": True,
            "categories": {},
            "pack_rotation": ["sc_kerrigan"],
        }))
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"rot1","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        # Should have used sc_kerrigan (the only option in rotation)
        assert state.get('session_packs', {}).get('rot1') == 'sc_kerrigan'
        assert 'greeting' in state.get('last_played', {})

    def test_keeps_same_pack_within_session(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "active_pack": "peon", "volume": 0.5, "enabled": True,
            "categories": {},
            "pack_rotation": ["sc_kerrigan"],
        }))
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"rot2","permission_mode":"default"}')
        run_peon(peon_dir,
            '{"hook_event_name":"Stop","cwd":"/tmp/myproject","session_id":"rot2","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert state['session_packs']['rot2'] == 'sc_kerrigan'

    def test_empty_rotation_falls_back(self, peon_dir):
        (peon_dir / 'config.json').write_text(json.dumps({
            "active_pack": "peon", "volume": 0.5, "enabled": True,
            "categories": {},
            "pack_rotation": [],
        }))
        run_peon(peon_dir,
            '{"hook_event_name":"SessionStart","cwd":"/tmp/myproject","session_id":"rot3","permission_mode":"default"}')
        state = json.loads((peon_dir / '.state.json').read_text())
        assert 'greeting' in state.get('last_played', {})
        # No session_packs entry since rotation is empty
        assert 'rot3' not in state.get('session_packs', {})
