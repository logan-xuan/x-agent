import React, { useState, useRef, useEffect } from 'react';
import { chatService } from '../services/chatService';
import './ChatInterface.css';

interface Message {
  id: string;
  content: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: Date;
  type?: 'text' | 'image' | 'file' | 'tool_result';
}

interface ChatInterfaceProps {
  sessionId?: string;
  onSendMessage?: (message: string) => void;
  onFileUpload?: (file: File) => void;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({
  sessionId,
  onSendMessage,
  onFileUpload
}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Mock initial messages for demo
  useEffect(() => {
    setMessages([
      {
        id: '1',
        content: 'Hello! I\'m your AI assistant. How can I help you today?',
        sender: 'assistant',
        timestamp: new Date(Date.now() - 300000),
        type: 'text'
      }
    ]);
  }, []);

  // Scroll to bottom of messages
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = async () => {
    if (!inputValue.trim()) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue,
      sender: 'user',
      timestamp: new Date(),
      type: 'text'
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    // Call parent handler if provided
    if (onSendMessage) {
      onSendMessage(inputValue);
    }

    setIsLoading(true);
    try {
      // Call the real API service
      const response = await chatService.sendMessage(inputValue, sessionId);

      // Add AI response
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.response,
        sender: 'assistant',
        timestamp: new Date(),
        type: 'text'
      };
      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: 'Sorry, I encountered an error processing your request.',
        sender: 'assistant',
        timestamp: new Date(),
        type: 'text'
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onFileUpload) {
      onFileUpload(file);

      // Add file message
      const fileMessage: Message = {
        id: Date.now().toString(),
        content: `Uploading file: ${file.name} (${(file.size / 1024).toFixed(2)} KB)`,
        sender: 'user',
        timestamp: new Date(),
        type: 'file'
      };

      setMessages(prev => [...prev, fileMessage]);

      try {
        // Actually upload the file using the service
        const response = await chatService.uploadFile(file, sessionId || '');

        // Replace the uploading message with success message
        setMessages(prev => prev.map(msg =>
          msg.id === fileMessage.id
            ? {
                ...msg,
                content: `Uploaded file: ${response.filename} (${(file.size / 1024).toFixed(2)} KB)`
              }
            : msg
        ));
      } catch (error) {
        console.error('Error uploading file:', error);
        // Show error message
        setMessages(prev => prev.map(msg =>
          msg.id === fileMessage.id
            ? {
                ...msg,
                content: `Failed to upload file: ${file.name}`,
                sender: 'system'
              }
            : msg
        ));
      } finally {
        e.target.value = ''; // Reset file input
      }
    }
  };

  return (
    <div className="chat-interface">
      <div className="chat-header">
        <h2>AI Assistant</h2>
        {sessionId && <span className="session-id">Session: {sessionId.substring(0, 8)}...</span>}
      </div>

      <div className="chat-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.sender}-message`}
          >
            <div className="message-content">
              {message.type === 'file' ? (
                <div className="file-message">
                  📎 {message.content}
                </div>
              ) : (
                <div className="text-message">
                  {message.content}
                </div>
              )}
              <div className="message-timestamp">
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          </div>
        ))}
        {isLoading && (
          <div className="message assistant-message">
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-area">
        <div className="input-controls">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message here..."
            disabled={isLoading}
          />
          <label htmlFor="file-upload" className="file-upload-button">
            📎
          </label>
          <input
            id="file-upload"
            type="file"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            className="send-button"
          >
            ➤
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;