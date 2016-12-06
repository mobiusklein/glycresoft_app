import datetime
import logging
from uuid import uuid4

from threading import Thread

from collections import defaultdict, namedtuple

try:
    from Queue import Queue, Empty as QueueEmptyException
except:
    from queue import Queue, Empty as QueueEmptyException


SessionIdentity = namedtuple("SessionIdentity", ["user_id", "session_id"])
UserIdentity = namedtuple("UserIdentity", ["id"])


class IdentityProvider(object):
    """Centralizes the minting of new UserIdentity and SessionIdentity
    objects, and tracks the relationship between user ids and session ids,
    though this behavior is also available through the SessionManager.
    
    Attributes
    ----------
    store : defaultdict(set)
        Mapping from UserIdentity to SessionIdentities
    """
    def __init__(self, syncfile=None):
        self.store = defaultdict(set)
        self.syncfile = syncfile
        if syncfile is not None:
            pass


    def new_session(self, user):
        new_id = str(uuid4())
        ses = SessionIdentity(user.id, new_id)
        self.store[user.id].add(ses.session_id)
        return ses

    def new_user(self, new_id=None):
        if new_id is None:
            new_id = str(uuid4())
        return UserIdentity(new_id)

    def sync(self):
        pass


# Common IdentityProvider for all applications.
# In the future, this will be made a member of the ApplicationManager
identity_provider = IdentityProvider()


class SessionManager(object):
    """Handles the tracking of UserIdentity to MessageQueueSessions,
    and as a wrapper around the underlying MessageQueueManager.
    
    Attributes
    ----------
    message_queue_manager : MessageQueueManagerBase
        The message queue that all messages are sent through
    session_map : defaultdict(dict)
        Mapping from UserIdentity to SessionIdentity -> MessageQueueSession
    """
    def __init__(self, message_queue_manager):
        self.message_queue_manager = message_queue_manager
        self.session_map = defaultdict(dict)

    def __iter__(self):
        return iter(self.session_map)

    def remove_user(self, identifier):
        sessions = self.user_sessions(identifier.user_id)
        for session in list(sessions):
            self.remove_session(session)
        self.session_map.pop(identifier)

    def remove_session(self, identifier):
        self.message_queue_manager.remove_queue(identifier)
        sessions = self.session_map[identifier.user_id]
        try:
            sessions.pop(identifier.session_id)
        except KeyError:
            pass

    def get_session(self, session_identifier):
        sessions_for_user = self.session_map[session_identifier.user_id]
        try:
            return sessions_for_user[session_identifier.session_id]
        except KeyError:
            new_session = self.create_new_session(session_identifier)
            sessions_for_user[session_identifier.session_id] = new_session
            return new_session

    def user_sessions(self, user_id):
        sessions_for_user = self.session_map[user_id]
        return sessions_for_user.values()

    def create_new_session(self, session_identifier):
        return MessageQueueSession(
            self,
            session_identifier)

    def _get_queue(self, session_identifier):
        return self.message_queue_manager.get_queue(session_identifier)

    def add_message(self, message, user_id=None):
        if user_id is None:
            if message.user is not None:
                user_id = message.user
            else:
                raise ValueError("Must provide a recipient user!")
        if isinstance(user_id, SessionIdentity):
            user_id = user_id.user_id
        elif isinstance(user_id, UserIdentity):
            user_id = user_id.id
        self.message_queue_manager.add_message(message, user_id)

    def put(self, message):
        if message.user is not None:
            user_id = message.user
        else:
            raise ValueError("Must provide a recipient user!")
        self.add_message(message, user_id)

    def __repr__(self):
        return "SessionManager(%r)" % self.message_queue_manager


class MessageQueueManagerBase(object):

    def __init__(self, **kwargs):
        self.session_manager = SessionManager(self)

    def add_message(self, message, user_id):
        raise NotImplementedError()

    def remove_messages_for(self, session_identifier):
        raise NotImplementedError()

    def get_queue(self, session_identifier):
        raise NotImplementedError()

    def remove_queue(self, session_identifier):
        raise NotImplementedError()

    def sync(self):
        pass

    def __repr__(self):
        return "{self.__class__.__name__}()".format(self=self)


class MemoryMessageQueueManager(MessageQueueManagerBase):
    """A simple MessageQueueManager that holds all message queues in memory.
    
    Attributes
    ----------
    storage : defaultdict(Queue)
        Mapping from SessionIdentity to thread-safe Queue
    """
    def __init__(self, **kwargs):
        super(MemoryMessageQueueManager, self).__init__(**kwargs)
        self.storage = defaultdict(Queue)

    def add_message(self, message, user_id):
        for session in self.session_manager.user_sessions(user_id):
            queue = self.storage[session.identifier]
            queue.put(message)

    def get_queue(self, session_identifier):
        return self.storage[session_identifier]

    def remove_queue(self, session_identifier):
        try:
            self.storage.pop(session_identifier)
        except KeyError:
            pass


class MessageQueueSession(object):
    """A read-only endpoint for a MessageQueue which can deliver messages to
    a single location. Associated with a SessionIdentity, and should only be
    created through a SessionManager's :meth:`create_new_session` method.
    
    Attributes
    ----------
    connected_at : datetime.datetime
        The time the connection was made.
    identifier : SessionIdentity
        The unique identifier for this session
    message_queue : Queue-like
        Any object which supports the method `get(block, timeout)` to fetch
        one item.
    session_manager : SessionManager
        The manager which governs the connection between this session and the
        underlying MessageQueueManager
    """
    def __init__(self, session_manager, identifier):
        self.session_manager = session_manager
        self.identifier = identifier
        self.connected_at = datetime.datetime.now()
        self.message_queue = session_manager._get_queue(self.identifier)

    def __repr__(self):
        return "MessageQueueSession(%s, %s)" % (self.identifier, self.session_manager)

    def get(self, block=True, timeout=None):
        return self.message_queue.get(block, timeout)

    def close(self):
        self.session_manager.remove_session(self.identifier)


def make_message_queue(message_queue_type=MemoryMessageQueueManager, params=None, **kwargs):
    if params is None:
        params = dict()
    params.update(kwargs)
    queue_manager = message_queue_type(**params)
    return queue_manager.session_manager
