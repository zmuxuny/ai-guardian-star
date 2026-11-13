"""API, authorization and real AMQTT 0.11.3 transport regressions."""

import asyncio
import importlib.util
import json
import logging
import sqlite3
import struct
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

# Reuse the existing Flask test dependency fallback.
from test_wenxin_proxy import proxy
from mqtt_access import ALERT_FILTER, allowed_users, issue_grant, permitted_topic, valid_grant


class GrantFixture:
    def prepare_grant(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / 'users.db')
        self.users = str(Path(self.temp.name) / 'users.json')
        Path(self.users).write_text('["alice"]', encoding='utf-8')
        self.patches = mock.patch.multiple(proxy, DB_PATH=self.database, MQTT_USERS_FILE=self.users)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        conn = proxy.get_db()
        conn.execute('INSERT INTO t_user (username,password_hash,create_time) VALUES (?,?,?)',
                     ('alice', 'test-only-password', 1))
        self.tokens = proxy._new_session(conn, 'alice')
        self.access_hash = proxy._token_hash(self.tokens['accessToken'])
        self.grant = issue_grant(conn, self.access_hash, int(time.time()) + 900)
        conn.commit()
        conn.close()
        self.client = proxy.app.test_client()
        self.headers = {'Authorization': 'Bearer ' + self.tokens['accessToken']}

    def execute(self, sql, parameters=()):
        with closing(sqlite3.connect(self.database)) as conn:
            conn.execute(sql, parameters)
            conn.commit()

    def valid(self, grant=None):
        grant = grant or self.grant
        return valid_grant(self.database, self.users, grant['username'], grant['password'])


class MqttGrantTest(GrantFixture, unittest.TestCase):
    def setUp(self):
        self.prepare_grant()

    def test_missing_invalid_and_expired_login_denied(self):
        endpoint = '/api/mqtt/credentials'
        self.assertEqual(self.client.post(endpoint).status_code, 401)
        self.assertEqual(self.client.post(endpoint, headers={'Authorization': 'Bearer wrong'}).status_code, 401)
        self.execute('UPDATE t_session SET access_expires_at=0')
        self.assertEqual(self.client.post(endpoint, headers=self.headers).status_code, 401)

    def test_explicit_allowlist_required_and_changes_revoke_existing_grant(self):
        self.assertTrue(self.valid())
        for contents in ('[]', '{}', 'broken-json'):
            Path(self.users).write_text(contents, encoding='utf-8')
            self.assertFalse(self.valid())
            self.assertEqual(self.client.post('/api/mqtt/credentials', headers=self.headers).status_code, 403)
        Path(self.users).unlink()
        self.assertEqual(allowed_users(self.users), set())
        self.assertFalse(self.valid())

    def test_api_issues_short_lived_separate_hashed_secret_and_revokes_previous_grant(self):
        response = self.client.post('/api/mqtt/credentials', headers=self.headers,
                                    json={'username': 'someone-else', 'topic': '#'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        grant = response.get_json()['credentials']
        self.assertEqual(grant['topic'], ALERT_FILTER)
        self.assertEqual(grant['username'], grant['clientId'])
        self.assertEqual(grant['expiresIn'], 300)
        self.assertNotEqual(grant['password'], self.tokens['accessToken'])
        self.assertTrue(self.valid(grant))
        self.assertFalse(self.valid())
        with closing(sqlite3.connect(self.database)) as conn:
            stored = conn.execute('SELECT password_hash FROM t_mqtt_grant').fetchone()[0]
        self.assertEqual(stored, proxy._token_hash(grant['password']))

    def test_grant_expiry_bad_secret_and_unknown_client_denied(self):
        self.assertTrue(self.valid())
        self.assertFalse(valid_grant(self.database, self.users, self.grant['username'], 'wrong'))
        self.assertFalse(valid_grant(self.database, self.users, 'guardian_app_unknown', self.grant['password']))
        self.assertFalse(valid_grant(self.database, self.users, self.grant['username'], self.grant['password'],
                                     now=int(time.time()) + 301))
        self.assertFalse(valid_grant(self.database + '-missing', self.users,
                                     self.grant['username'], self.grant['password']))

    def test_frozen_account_denies_credentials_and_existing_delivery(self):
        self.execute('UPDATE t_user SET is_frozen=1')
        self.assertFalse(self.valid())
        self.assertEqual(self.client.post('/api/mqtt/credentials', headers=self.headers).status_code, 401)

    def test_logout_revokes_existing_grant(self):
        self.assertTrue(self.valid())
        self.assertEqual(self.client.post('/api/logout', headers=self.headers).status_code, 200)
        self.assertFalse(self.valid())

    def test_refresh_preserves_grant_binding_then_logout_revokes(self):
        response = self.client.post('/api/refresh', json={'refreshToken': self.tokens['refreshToken']})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.valid())
        headers = {'Authorization': 'Bearer ' + response.get_json()['accessToken']}
        self.assertEqual(self.client.post('/api/logout', headers=headers).status_code, 200)
        self.assertFalse(self.valid())

    def test_near_expired_access_requests_refresh_before_issue(self):
        self.execute('UPDATE t_session SET access_expires_at=?', (int(time.time()) + 30,))
        self.assertEqual(self.client.post('/api/mqtt/credentials', headers=self.headers).status_code, 401)

    def test_app_topic_boundary(self):
        self.assertTrue(permitted_topic(ALERT_FILTER, 'subscribe'))
        self.assertTrue(permitted_topic('ai_guardian/alerts/fall', 'receive'))
        for topic in ('#', '+', '$SYS/#', 'ai_guardian/#', 'ai_guardian/alerts_other', ''):
            self.assertFalse(permitted_topic(topic, 'subscribe'))
            self.assertFalse(permitted_topic(topic, 'receive'))
        for action in ('publish', 'unknown', None):
            self.assertFalse(permitted_topic('ai_guardian/alerts/fall', action))


AMQTT_INSTALLED = importlib.util.find_spec('amqtt') is not None


def mqtt_string(value):
    value = value.encode('utf-8')
    return struct.pack('!H', len(value)) + value


async def send_packet(writer, header, payload):
    remaining = len(payload)
    encoded = bytearray()
    while True:
        part = remaining % 128
        remaining //= 128
        encoded.append(part | (128 if remaining else 0))
        if not remaining:
            break
    writer.write(bytes([header]) + bytes(encoded) + payload)
    await writer.drain()


async def read_packet(reader, timeout=1):
    async def read():
        header = (await reader.readexactly(1))[0]
        length, multiplier = 0, 1
        while True:
            part = (await reader.readexactly(1))[0]
            length += (part & 127) * multiplier
            if part < 128:
                break
            multiplier *= 128
        return header, await reader.readexactly(length)
    return await asyncio.wait_for(read(), timeout)


@unittest.skipUnless(AMQTT_INSTALLED, 'Requires production AMQTT 0.11.3')
class MqttBrokerTest(GrantFixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from amqtt.broker import Broker
        from passlib.apps import custom_app_context
        self.prepare_grant()
        self.writers = []
        password_file = str(Path(self.temp.name) / 'passwd')
        Path(password_file).write_text('ascend_board:' + custom_app_context.hash('board-test-password') + '\n'
                                      'harmony_app:' + custom_app_context.hash('legacy-test-password') + '\n',
                                      encoding='utf-8')
        self.config = {
            'listeners': {'default': {'type': 'tcp', 'bind': '127.0.0.1:0'}},
            'plugins': {
                'guardian_mqtt_plugin.GuardianAuthPlugin': {
                    'database': self.database, 'users_file': self.users, 'password_file': password_file},
                'guardian_mqtt_plugin.GuardianTopicPlugin': {'database': self.database, 'users_file': self.users},
            },
        }
        self.broker = Broker(self.config)
        await self.broker.start()
        self.port = self.broker._servers['default'].instance.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        for writer in self.writers:
            writer.close()
            await writer.wait_closed()
        await self.broker.shutdown()

    async def connect(self, username=None, password=None, *, client_id=None, clean=True, will=False, expect=True):
        username = username or self.grant['username']
        password = password or self.grant['password']
        reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
        self.writers.append(writer)
        flags = 0xc0 | (2 if clean else 0) | (4 if will else 0)
        payload = mqtt_string('MQTT') + bytes([4, flags]) + struct.pack('!H', 30)
        payload += mqtt_string(client_id or username)
        if will:
            payload += mqtt_string('ai_guardian/alerts/fall') + mqtt_string('forged-will')
        payload += mqtt_string(username) + mqtt_string(password)
        await send_packet(writer, 0x10, payload)
        if expect:
            self.assertEqual(await read_packet(reader), (0x20, b'\x00\x00'))
        else:
            self.assertEqual(await asyncio.wait_for(reader.read(4), 1), b'')
        return reader, writer

    async def subscribe(self, reader, writer, topic=ALERT_FILTER, granted=0):
        await send_packet(writer, 0x82, b'\x00\x01' + mqtt_string(topic) + b'\x00')
        self.assertEqual(await read_packet(reader), (0x90, b'\x00\x01' + bytes([granted])))

    async def publish_board(self, writer, payload=b'board-heartbeat'):
        await send_packet(writer, 0x30, mqtt_string('ai_guardian/alerts/fall') + payload)

    async def test_board_publish_app_receive_and_subscription_denials(self):
        reader, writer = await self.connect()
        await self.subscribe(reader, writer)
        for topic in ('#', '$SYS/#', 'ai_guardian/#', 'other/topic'):
            await self.subscribe(reader, writer, topic, 128)
        _, board = await self.connect('ascend_board', 'board-test-password')
        await self.publish_board(board)
        packet = await read_packet(reader)
        self.assertEqual(packet, (0x30, mqtt_string('ai_guardian/alerts/fall') + b'board-heartbeat'))

    async def test_bad_secret_legacy_app_will_persistence_and_wrong_client_denied(self):
        await self.connect(password='wrong', expect=False)
        await self.connect('harmony_app', 'legacy-test-password', expect=False)
        await self.connect('ascend_board', 'wrong-board-password', expect=False)
        await self.connect(will=True, expect=False)
        await self.connect(clean=False, expect=False)
        await self.connect(client_id='someone-else', expect=False)

    async def test_app_publish_never_delivered_to_board(self):
        board_reader, board_writer = await self.connect('ascend_board', 'board-test-password')
        await self.subscribe(board_reader, board_writer)
        _, app_writer = await self.connect()
        await self.publish_board(app_writer, b'forged-alert')
        with self.assertRaises(asyncio.TimeoutError):
            await read_packet(board_reader, 0.15)

    async def test_connected_client_stops_receiving_after_expiry(self):
        reader, writer = await self.connect()
        await self.subscribe(reader, writer)
        _, board = await self.connect('ascend_board', 'board-test-password')
        self.execute('UPDATE t_mqtt_grant SET expires_at=0')
        await self.publish_board(board)
        with self.assertRaises(asyncio.TimeoutError):
            await read_packet(reader, 0.15)
        await self.connect(expect=False)

    async def test_connected_client_stops_receiving_after_logout(self):
        reader, writer = await self.connect()
        await self.subscribe(reader, writer)
        _, board = await self.connect('ascend_board', 'board-test-password')
        self.client.post('/api/logout', headers=self.headers)
        await self.publish_board(board)
        with self.assertRaises(asyncio.TimeoutError):
            await read_packet(reader, 0.15)

    async def test_connected_client_stops_receiving_after_allowlist_removal(self):
        reader, writer = await self.connect()
        await self.subscribe(reader, writer)
        _, board = await self.connect('ascend_board', 'board-test-password')
        Path(self.users).write_text('[]', encoding='utf-8')
        await self.publish_board(board)
        with self.assertRaises(asyncio.TimeoutError):
            await read_packet(reader, 0.15)

    async def test_connected_client_stops_receiving_after_freeze(self):
        reader, writer = await self.connect()
        await self.subscribe(reader, writer)
        _, board = await self.connect('ascend_board', 'board-test-password')
        self.execute('UPDATE t_user SET is_frozen=1')
        await self.publish_board(board)
        with self.assertRaises(asyncio.TimeoutError):
            await read_packet(reader, 0.15)

    async def test_restart_keeps_board_and_unexpired_database_grants(self):
        from amqtt.broker import Broker
        await self.broker.shutdown()
        self.broker = Broker(self.config)
        await self.broker.start()
        self.port = self.broker._servers['default'].instance.sockets[0].getsockname()[1]
        reader, writer = await self.connect()
        await self.subscribe(reader, writer)
        _, board = await self.connect('ascend_board', 'board-test-password')
        await self.publish_board(board)
        self.assertEqual((await read_packet(reader))[0], 0x30)


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    unittest.main()
