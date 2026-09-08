"""AMQTT 0.11.3 authentication/authorization; no App shared password."""

from dataclasses import dataclass

from amqtt.plugins.authentication import FileAuthPlugin
from amqtt.plugins.base import BaseTopicPlugin

from mqtt_access import APP_PREFIX, permitted_topic, valid_grant


@dataclass
class GuardianConfig:
    database: str = '/opt/wenxin/app/guardian_users.db'
    users_file: str = '/etc/wenxin/mqtt-users.json'
    password_file: str = '/etc/amqtt/passwd'


def is_app(session):
    return bool(session and isinstance(session.username, str) and session.username.startswith(APP_PREFIX))


def authorized_app(config, session):
    # AMQTT wills bypass PUBLISH checks, and cached offline messages bypass RECEIVE.
    if session.will_flag or not session.clean_session or session.client_id != session.username:
        return False
    return valid_grant(config.database, config.users_file, session.username, session.password)


class GuardianAuthPlugin(FileAuthPlugin):
    Config = GuardianConfig

    async def authenticate(self, *, session):
        if is_app(session):
            return authorized_app(self.config, session)
        # Preserve the existing board identity only; retire the shared App identity.
        if not session or session.username != 'ascend_board':
            return False
        return await super().authenticate(session=session)


class GuardianTopicPlugin(BaseTopicPlugin):
    Config = GuardianConfig

    async def topic_filtering(self, *, session=None, topic=None, action=None):
        if is_app(session):
            return permitted_topic(topic, action) and authorized_app(self.config, session)
        return bool(session and session.username == 'ascend_board')
