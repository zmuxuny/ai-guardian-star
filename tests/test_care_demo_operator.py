"""Exercise operator recovery across independent PowerShell processes, no SSH."""
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('pwsh.exe'), 'PowerShell 7 required')
class OperatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        tools = self.root / 'tools'
        tools.mkdir()
        shutil.copy2(SOURCE / 'tools/Invoke-CareDemo.ps1', tools)
        (tools / 'Invoke-BoardValidation.ps1').write_text(r'''
param($Action,$Session,$OutputDirectory,$IdentityFile,$SocksProxy,[switch]$FastDemo,[switch]$AudioDemo)
$root=Split-Path $PSScriptRoot -Parent
@{action=$Action;session=$Session;fast=[bool]$FastDemo;audio=[bool]$AudioDemo}|ConvertTo-Json -Compress|Add-Content "$root/calls.jsonl"
switch($Action){
 Prepare { New-Item -ItemType File -Force "$OutputDirectory/board-kit.zip"|Out-Null; '{"status":"PASS"}' }
 StartShadow { 'shadow'|Set-Content "$root/mode"; '{"status":"PASS"}' }
 RecoverOff { if(Test-Path "$root/fail-recover"){ exit 7 }; 'off'|Set-Content "$root/mode"; '{"status":"PASS"}' }
 Probe { $m=if(Test-Path "$root/mode"){(Get-Content "$root/mode").Trim()}else{'off'}; @{status='PASS';care_mode=$m;care_config_present=($m -ne 'off')}|ConvertTo-Json }
}
''', encoding='utf-8')

    def run_action(self, action, *extra):
        return subprocess.run(['pwsh.exe', '-NoProfile', '-File',
                               str(self.root / 'tools/Invoke-CareDemo.ps1'),
                               '-Action', action, *extra], capture_output=True, text=True, encoding='utf-8', timeout=40)

    def calls(self):
        return [json.loads(s) for s in (self.root / 'calls.jsonl').read_text().splitlines()]

    def state(self):
        return json.loads((self.root / '.tmp/care-demo-operator/state.json').read_text(encoding='utf-8-sig'))

    def test_start_duplicate_stop_and_audio_opt_in(self):
        result = self.run_action('Start')
        self.assertEqual(0, result.returncode, result.stderr)
        original = self.state()['session']
        start = next(c for c in self.calls() if c['action'] == 'StartShadow')
        self.assertTrue(start['fast'])
        self.assertFalse(start['audio'])
        self.assertNotEqual(0, self.run_action('Start').returncode)
        self.assertEqual(original, self.state()['session'])
        self.assertEqual(0, self.run_action('Stop').returncode)
        self.assertEqual('closed', self.state()['status'])
        actions = [c['action'] for c in self.calls()]
        self.assertIn('RecoverOff', actions)
        self.assertTrue(all(a == 'Probe' for a in actions[actions.index('RecoverOff') + 1:]))
        self.assertEqual(0, self.run_action('Start', '-AudioDemo').returncode)
        self.assertNotEqual(original, self.state()['session'])
        self.assertTrue([c for c in self.calls() if c['action'] == 'StartShadow'][-1]['audio'])

    def test_failed_recovery_still_probes_and_keeps_ownership(self):
        self.assertEqual(0, self.run_action('Start').returncode)
        (self.root / 'fail-recover').touch()
        self.assertNotEqual(0, self.run_action('Stop').returncode)
        actions = [c['action'] for c in self.calls()]
        self.assertIn('RecoverOff', actions)
        self.assertTrue(all(a == 'Probe' for a in actions[actions.index('RecoverOff') + 1:]))
        self.assertEqual('running', self.state()['status'])
        (self.root / 'mode').write_text('off')
        self.assertEqual(0, self.run_action('Stop').returncode)
        self.assertEqual('closed', self.state()['status'])

    def test_stop_without_session_does_not_claim_off(self):
        self.assertNotEqual(0, self.run_action('Stop').returncode)
        self.assertFalse((self.root / 'calls.jsonl').exists())


@unittest.skipUnless(shutil.which('pwsh.exe'), 'PowerShell 7 required')
class SocksTransportTest(unittest.TestCase):
    def test_ssh_and_scp_share_proxy_and_host_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'board-kit.zip').write_bytes(b'fixture')
            (root / 'identity').write_text('fixture, not a key')
            harness = root / 'harness.ps1'
            harness.write_text(r'''
param($Validator,$Root)
function global:ssh { @{tool='ssh';args=@($args)}|ConvertTo-Json -Compress|Add-Content "$Root/calls"; $global:LASTEXITCODE=0 }
function global:scp { @{tool='scp';args=@($args)}|ConvertTo-Json -Compress|Add-Content "$Root/calls"; $global:LASTEXITCODE=0 }
& $Validator -Action Probe -OutputDirectory $Root -IdentityFile "$Root/identity" -SocksProxy '127.0.0.1:7890'
''', encoding='utf-8')
            result = subprocess.run(['pwsh.exe', '-NoProfile', '-File', str(harness),
                                     str(SOURCE / 'tools/Invoke-BoardValidation.ps1'), str(root)],
                                    capture_output=True, encoding='utf-8', timeout=20)
            self.assertEqual(0, result.returncode, result.stderr)
            calls = [json.loads(s) for s in (root / 'calls').read_text(encoding='utf-8-sig').splitlines()]
            self.assertEqual({'ssh', 'scp'}, {c['tool'] for c in calls})
            for call in calls:
                self.assertIn('StrictHostKeyChecking=yes', call['args'])
                proxy = [a for a in call['args'] if isinstance(a, str) and a.startswith('ProxyCommand=')]
                self.assertEqual(1, len(proxy))
                self.assertIn('-S 127.0.0.1:7890 %h %p', proxy[0])


if __name__ == '__main__':
    unittest.main()
