import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.operating_environment import network_probe, executable_paths

class OperatingEnvironmentTests(unittest.TestCase):
    def test_firewall_paths_include_junction_target(self):
        def resolved(path, strict=False):
            return Path(str(path).replace('alias-python', 'physical-python'))
        with patch('sys.executable', 'C:/alias-python/python.exe'), \
             patch('sys._base_executable', 'C:/alias-python/python.exe'), \
             patch.object(Path, 'resolve', autospec=True, side_effect=resolved):
            paths = executable_paths()
        self.assertIn('C:/alias-python/python.exe', paths)
        self.assertIn(str(Path('C:/physical-python/python.exe')), paths)

    def test_connected_network_rejected(self):
        with patch('socket.create_connection', return_value=MagicMock()):
            with self.assertRaises(RuntimeError): network_probe()

    def test_timeout_is_not_proof_of_offline_enforcement(self):
        with patch('socket.create_connection', side_effect=TimeoutError()):
            with self.assertRaises(RuntimeError): network_probe()

    def test_explicit_os_denial_accepted(self):
        error = OSError('OS denied outbound')
        error.winerror = 10013
        with patch('socket.create_connection', side_effect=error):
            self.assertEqual(len(network_probe()), 2)

if __name__ == '__main__': unittest.main()
