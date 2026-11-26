"""Fault checks for the isolated trial's fail-closed resource monitor."""
import socket
import threading
import unittest

from tools.local_care_board_trial import guard_monitor, port_available


class TrialGuardTests(unittest.TestCase):
    def test_monitor_io_failure_notifies_owner(self):
        errors = []
        def broken():
            raise OSError('synthetic monitor failure')
        guard_monitor(broken, errors.append)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], OSError)

    def test_monitor_type_failure_notifies_owner(self):
        errors = []
        def broken():
            raise TypeError('missing fps')
        guard_monitor(broken, errors.append)
        self.assertIsInstance(errors[0], TypeError)

    def test_success_does_not_notify(self):
        events = []
        guard_monitor(lambda: events.append('sample'), lambda _: self.fail())
        self.assertEqual(events, ['sample'])

    def test_active_listener_is_not_available(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            self.assertFalse(port_available(listener.getsockname()[1]))

    def test_closed_listener_is_available_even_after_connection(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            port = listener.getsockname()[1]
            def accept():
                connection, _ = listener.accept()
                connection.close()
            worker = threading.Thread(target=accept)
            worker.start()
            with socket.create_connection(('127.0.0.1', port)) as client:
                self.assertEqual(client.recv(1), b'')
            worker.join()
        self.assertTrue(port_available(port))


if __name__ == '__main__':
    unittest.main()
