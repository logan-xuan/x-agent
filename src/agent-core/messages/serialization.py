"""
Message serialization/deserialization utilities for the x-agent2 AI assistant system.

This module handles the conversion of message objects to and from various formats
for storage, transmission, and processing.
"""

import json
from typing import Any, Dict, List, Union, Optional
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import pickle
import base64
from uuid import UUID

from src.db.models.message import Message


class SerializationFormat(Enum):
    """Supported serialization formats."""
    JSON = "json"
    PICKLE = "pickle"
    CUSTOM = "custom"


class MessageSerializer(ABC):
    """Abstract base class for message serializers."""

    @abstractmethod
    def serialize(self, message: Message) -> Union[str, bytes]:
        """Serialize a message to the target format."""
        pass

    @abstractmethod
    def deserialize(self, data: Union[str, bytes]) -> Message:
        """Deserialize data to a message object."""
        pass


class JSONMessageSerializer(MessageSerializer):
    """JSON-based message serializer."""

    def serialize(self, message: Message) -> str:
        """Serialize a message to JSON string."""
        message_dict = {
            "id": str(message.id) if hasattr(message, 'id') else None,
            "session_id": str(message.session_id) if hasattr(message, 'session_id') else None,
            "user_id": str(message.user_id) if hasattr(message, 'user_id') else None,
            "content": message.content if hasattr(message, 'content') else {},
            "message_type": message.message_type if hasattr(message, 'message_type') else "text",
            "timestamp": message.timestamp.isoformat() if hasattr(message, 'timestamp') and message.timestamp else None,
            "metadata": message.metadata if hasattr(message, 'metadata') else {},
            "is_response": getattr(message, 'is_response', False)
        }

        # Convert datetime objects to ISO format strings
        for key, value in message_dict.items():
            if isinstance(value, datetime):
                message_dict[key] = value.isoformat()

        return json.dumps(message_dict, ensure_ascii=False, indent=2)

    def deserialize(self, data: str) -> Message:
        """Deserialize a JSON string to a message object."""
        if isinstance(data, bytes):
            data = data.decode('utf-8')

        message_dict = json.loads(data)

        # Convert timestamp string back to datetime object
        timestamp_str = message_dict.get("timestamp")
        timestamp = None
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Create message object
        # Note: We're creating a simplified version since the actual Message model
        # may have additional requirements
        message = Message.__new__(Message)  # Create instance without calling __init__

        message.id = message_dict.get("id")
        message.session_id = message_dict.get("session_id")
        message.user_id = message_dict.get("user_id")
        message.content = message_dict.get("content", {})
        message.message_type = message_dict.get("message_type", "text")
        message.timestamp = timestamp
        message.metadata = message_dict.get("metadata", {})
        message.is_response = message_dict.get("is_response", False)

        return message


class PickleMessageSerializer(MessageSerializer):
    """Pickle-based message serializer for binary serialization."""

    def serialize(self, message: Message) -> bytes:
        """Serialize a message to pickle bytes."""
        message_dict = {
            "id": message.id if hasattr(message, 'id') else None,
            "session_id": message.session_id if hasattr(message, 'session_id') else None,
            "user_id": message.user_id if hasattr(message, 'user_id') else None,
            "content": message.content if hasattr(message, 'content') else {},
            "message_type": message.message_type if hasattr(message, 'message_type') else "text",
            "timestamp": message.timestamp if hasattr(message, 'timestamp') else None,
            "metadata": message.metadata if hasattr(message, 'metadata') else {},
            "is_response": getattr(message, 'is_response', False)
        }

        return pickle.dumps(message_dict)

    def deserialize(self, data: bytes) -> Message:
        """Deserialize pickle bytes to a message object."""
        if isinstance(data, str):
            data = data.encode('utf-8')

        message_dict = pickle.loads(data)

        # Create message object
        message = Message.__new__(Message)  # Create instance without calling __init__

        message.id = message_dict.get("id")
        message.session_id = message_dict.get("session_id")
        message.user_id = message_dict.get("user_id")
        message.content = message_dict.get("content", {})
        message.message_type = message_dict.get("message_type", "text")
        message.timestamp = message_dict.get("timestamp")
        message.metadata = message_dict.get("metadata", {})
        message.is_response = message_dict.get("is_response", False)

        return message


class Base64MessageSerializer(MessageSerializer):
    """Base64-encoded JSON serializer for safe transmission."""

    def serialize(self, message: Message) -> str:
        """Serialize a message to base64-encoded JSON."""
        json_str = JSONMessageSerializer().serialize(message)
        return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

    def deserialize(self, data: str) -> Message:
        """Deserialize base64-encoded JSON to a message object."""
        json_bytes = base64.b64decode(data.encode('utf-8'))
        json_str = json_bytes.decode('utf-8')
        return JSONMessageSerializer().deserialize(json_str)


class MessageSerializationService:
    """Service class to manage message serialization operations."""

    def __init__(self):
        self._serializers = {
            SerializationFormat.JSON: JSONMessageSerializer(),
            SerializationFormat.PICKLE: PickleMessageSerializer(),
            SerializationFormat.CUSTOM: Base64MessageSerializer()
        }

    def serialize(
        self,
        message: Message,
        format_type: SerializationFormat = SerializationFormat.JSON
    ) -> Union[str, bytes]:
        """Serialize a message using the specified format."""
        if format_type not in self._serializers:
            raise ValueError(f"Unsupported serialization format: {format_type}")

        serializer = self._serializers[format_type]
        return serializer.serialize(message)

    def deserialize(
        self,
        data: Union[str, bytes],
        format_type: SerializationFormat = SerializationFormat.JSON
    ) -> Message:
        """Deserialize data to a message using the specified format."""
        if format_type not in self._serializers:
            raise ValueError(f"Unsupported serialization format: {format_type}")

        serializer = self._serializers[format_type]
        return serializer.deserialize(data)

    def batch_serialize(
        self,
        messages: List[Message],
        format_type: SerializationFormat = SerializationFormat.JSON
    ) -> List[Union[str, bytes]]:
        """Serialize a batch of messages."""
        return [self.serialize(msg, format_type) for msg in messages]

    def batch_deserialize(
        self,
        data_list: List[Union[str, bytes]],
        format_type: SerializationFormat = SerializationFormat.JSON
    ) -> List[Message]:
        """Deserialize a batch of message data."""
        return [self.deserialize(data, format_type) for data in data_list]

    def get_serializer(self, format_type: SerializationFormat) -> MessageSerializer:
        """Get a specific serializer instance."""
        if format_type not in self._serializers:
            raise ValueError(f"Unsupported serialization format: {format_type}")
        return self._serializers[format_type]


class MessageValidator:
    """Validates message objects before serialization."""

    @staticmethod
    def validate_message(message: Message) -> Dict[str, Any]:
        """
        Validate a message object and return validation results.

        Args:
            message: Message object to validate

        Returns:
            Dictionary with validation results
        """
        errors = []
        warnings = []

        # Check required fields
        if not hasattr(message, 'id') or not message.id:
            errors.append("Message ID is required")

        if not hasattr(message, 'session_id') or not message.session_id:
            errors.append("Session ID is required")

        if not hasattr(message, 'content'):
            errors.append("Message content is required")

        # Check content validity
        if hasattr(message, 'content'):
            if message.content is None:
                warnings.append("Message content is None")

        # Check timestamp validity
        if hasattr(message, 'timestamp') and message.timestamp:
            if not isinstance(message.timestamp, datetime):
                errors.append("Message timestamp must be a datetime object")

        # Check message type
        if hasattr(message, 'message_type'):
            valid_types = ["text", "file", "tool_call", "tool_response", "system"]
            if message.message_type not in valid_types:
                warnings.append(f"Unrecognized message type: {message.message_type}")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

    @staticmethod
    def sanitize_message(message: Message) -> Message:
        """
        Sanitize a message object by fixing common issues.

        Args:
            message: Message object to sanitize

        Returns:
            Sanitized message object
        """
        # Ensure we have an ID
        if not hasattr(message, 'id') or not message.id:
            import uuid
            message.id = str(uuid.uuid4())

        # Ensure we have a timestamp
        if not hasattr(message, 'timestamp') or not message.timestamp:
            message.timestamp = datetime.now(timezone.utc)

        # Sanitize content if it's a string
        if hasattr(message, 'content') and isinstance(message.content, str):
            # Remove null bytes and other problematic characters
            message.content = message.content.replace('\x00', '')

        return message


# Global service instance
serialization_service = MessageSerializationService()


# Convenience functions
def serialize_message(
    message: Message,
    format_type: SerializationFormat = SerializationFormat.JSON
) -> Union[str, bytes]:
    """Convenience function to serialize a message."""
    return serialization_service.serialize(message, format_type)


def deserialize_message(
    data: Union[str, bytes],
    format_type: SerializationFormat = SerializationFormat.JSON
) -> Message:
    """Convenience function to deserialize message data."""
    return serialization_service.deserialize(data, format_type)


def validate_message(message: Message) -> Dict[str, Any]:
    """Convenience function to validate a message."""
    return MessageValidator.validate_message(message)


def sanitize_message(message: Message) -> Message:
    """Convenience function to sanitize a message."""
    return MessageValidator.sanitize_message(message)