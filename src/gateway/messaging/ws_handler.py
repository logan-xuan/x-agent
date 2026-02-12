"""
WebSocket connection handler for real-time chat in x-agent2 AI assistant system.

This module handles WebSocket connections for real-time communication between
clients and the AI assistant.
"""

import asyncio
import json
from typing import Dict, Set
from datetime import datetime
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from src.gateway.messaging.message_handler import message_handler
from src.gateway.session.db_session import db_session_manager


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_sessions: Dict[str, str] = {}  # connection_id -> session_id

    async def connect(self, websocket: WebSocket, session_id: str = None):
        """Add a new WebSocket connection."""
        await websocket.accept()

        # Generate a unique connection ID
        connection_id = str(uuid.uuid4())
        self.active_connections[connection_id] = websocket

        # Assign or create session for this connection
        if session_id:
            self.connection_sessions[connection_id] = session_id
        else:
            # Create a new session if none provided
            new_session = await db_session_manager.create_session()
            self.connection_sessions[connection_id] = new_session.id

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        connection_id = None
        for conn_id, conn_ws in self.active_connections.items():
            if conn_ws == websocket:
                connection_id = conn_id
                break

        if connection_id:
            del self.active_connections[connection_id]
            if connection_id in self.connection_sessions:
                del self.connection_sessions[connection_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket."""
        await websocket.send_text(json.dumps(message))

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSockets."""
        disconnected = []
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except:
                # If sending fails, mark for disconnection
                disconnected.append(websocket)

        # Clean up disconnected connections
        for websocket in disconnected:
            self.disconnect(websocket)


manager = ConnectionManager()


class WebSocketHandler:
    """Handles WebSocket communication logic."""

    def __init__(self):
        self.connection_manager = manager

    async def handle_websocket_connection(self, websocket: WebSocket, session_id: str = None):
        """Handle a WebSocket connection lifecycle."""
        await self.connection_manager.connect(websocket, session_id)

        try:
            # Get the session ID for this connection
            connection_id = None
            for conn_id, conn_ws in self.connection_manager.active_connections.items():
                if conn_ws == websocket:
                    connection_id = conn_id
                    break

            if not connection_id:
                return

            session_id = self.connection_manager.connection_sessions[connection_id]

            # Send welcome message
            welcome_msg = {
                "type": "system",
                "message": "Connected to AI assistant",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            await self.connection_manager.send_personal_message(welcome_msg, websocket)

            # Listen for messages
            while True:
                try:
                    data = await websocket.receive_text()

                    # Parse the received message
                    try:
                        message_data = json.loads(data)
                    except json.JSONDecodeError:
                        # If not JSON, treat as plain text
                        message_data = {"type": "text", "content": data}

                    # Handle different message types
                    msg_type = message_data.get("type", "text")
                    user_content = message_data.get("content", "")
                    user_id = message_data.get("user_id", None)

                    if msg_type == "text":
                        # Process text message through the message handler
                        response = await message_handler.process_message(
                            user_input=user_content,
                            session_id=session_id,
                            user_id=user_id
                        )

                        # Send response back to client
                        response["type"] = "assistant_response"
                        response["timestamp"] = datetime.utcnow().isoformat()
                        await self.connection_manager.send_personal_message(response, websocket)

                    elif msg_type == "ping":
                        # Respond to ping with pong
                        pong_msg = {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        await self.connection_manager.send_personal_message(pong_msg, websocket)

                    elif msg_type == "session_info":
                        # Send session information
                        session_info = {
                            "type": "session_info",
                            "session_id": session_id,
                            "connected": True,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        await self.connection_manager.send_personal_message(session_info, websocket)

                    else:
                        # Unsupported message type
                        error_msg = {
                            "type": "error",
                            "message": f"Unsupported message type: {msg_type}",
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        await self.connection_manager.send_personal_message(error_msg, websocket)

                except WebSocketDisconnect:
                    # Client disconnected
                    break
                except Exception as e:
                    # Handle any other errors
                    error_msg = {
                        "type": "error",
                        "message": f"Error processing message: {str(e)}",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    await self.connection_manager.send_personal_message(error_msg, websocket)

        except WebSocketDisconnect:
            # Connection was closed
            pass
        finally:
            # Clean up connection
            self.connection_manager.disconnect(websocket)

    async def send_heartbeat(self, session_id: str, message: str):
        """Send a heartbeat message to clients in a specific session."""
        # Find all connections in the same session
        for conn_id, sess_id in self.connection_manager.connection_sessions.items():
            if sess_id == session_id and conn_id in self.connection_manager.active_connections:
                ws = self.connection_manager.active_connections[conn_id]
                heartbeat_msg = {
                    "type": "heartbeat",
                    "session_id": session_id,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                }
                try:
                    await ws.send_text(json.dumps(heartbeat_msg))
                except:
                    # If sending fails, disconnect the socket
                    self.connection_manager.disconnect(ws)

    async def broadcast_to_session(self, session_id: str, message: dict):
        """Broadcast a message to all clients in a specific session."""
        message["timestamp"] = datetime.utcnow().isoformat()
        message["session_id"] = session_id

        # Find all connections in the same session
        for conn_id, sess_id in self.connection_manager.connection_sessions.items():
            if sess_id == session_id and conn_id in self.connection_manager.active_connections:
                ws = self.connection_manager.active_connections[conn_id]
                try:
                    await ws.send_text(json.dumps(message))
                except:
                    # If sending fails, disconnect the socket
                    self.connection_manager.disconnect(ws)


# Global WebSocket handler instance
ws_handler = WebSocketHandler()