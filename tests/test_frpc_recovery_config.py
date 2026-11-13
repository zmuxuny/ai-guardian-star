"""Check the minimal FRP fragment without production credentials or binaries."""
from pathlib import Path
import tomllib
import unittest


FRAGMENT = (Path(__file__).resolve().parents[1] / 'deploy/board/frpc-recovery.toml').read_text(encoding='utf-8')


class FrpcRecoveryConfigTests(unittest.TestCase):
    def test_fragment_changes_only_mux_liveness(self):
        self.assertEqual(tomllib.loads(FRAGMENT), {'transport': {'tcpMuxKeepaliveInterval': 5}})

    def test_prepend_preserves_auth_ports_and_proxy_definitions(self):
        original = '''serverAddr = "example.invalid"
serverPort = 7000
auth.token = "synthetic-test-only"
[[proxies]]
name = "video"
type = "tcp"
localPort = 5000
remotePort = 6001
[[proxies]]
name = "ssh"
type = "tcp"
localPort = 22
remotePort = 6022
'''
        merged = tomllib.loads(FRAGMENT + '\n' + original)
        merged.pop('transport')
        self.assertEqual(merged, tomllib.loads(original))

    def test_conflicting_existing_setting_cannot_silently_override(self):
        with self.assertRaises(tomllib.TOMLDecodeError):
            tomllib.loads(FRAGMENT + '\ntransport.tcpMuxKeepaliveInterval = 30\n')


if __name__ == '__main__':
    unittest.main()
