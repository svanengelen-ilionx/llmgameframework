from __future__ import annotations

from collections.abc import Iterable, Sequence

from llmgames.core.contracts import Message


def public_message(sender_id: str, text: str, turn: int) -> Message:
    return Message(sender_id=sender_id, text=text, turn=turn)


def private_message(sender_id: str, recipient_id: str, text: str, turn: int) -> Message:
    return Message(sender_id=sender_id, text=text, turn=turn, recipient_ids=frozenset({recipient_id}))


def group_message(sender_id: str, recipient_ids: Iterable[str], text: str, turn: int) -> Message:
    return Message(sender_id=sender_id, text=text, turn=turn, recipient_ids=frozenset(recipient_ids))


def is_message_visible(message: Message, player_id: str) -> bool:
    return message.recipient_ids is None or player_id in message.recipient_ids


def visible_messages(messages: Sequence[Message], player_id: str) -> list[Message]:
    return [message for message in messages if is_message_visible(message, player_id)]
