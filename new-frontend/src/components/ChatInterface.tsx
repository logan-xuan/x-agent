import React, { useState, useRef, useEffect } from 'react';
import { Send, PlusCircle, Image as ImageIcon, FileText, Bot, User } from 'lucide-react';
import { chatService } from '@/services/chatService';

interface Message {
  id: string;
  content: string;
  sender: 'user' | 'assistant' | 'system';
  timestamp: Date;
  type?: 'text' | 'image' | 'file' | 'tool_result';
}

interface ChatInterfaceProps {
  sessionId: string;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ sessionId }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      content: 'Hello! I\'m your x-agent2 assistant. How can I help you today?',
      sender: 'assistant',
      timestamp: new Date(),
      type: 'text'
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = async () => {
    if ((!inputValue.trim() && !selectedFile) || isLoading) return;

    let newMessage: Message;
    let fileProcessed = false;

    // Add user message
    if (inputValue.trim()) {
      newMessage = {
        id: Date.now().toString(),
        content: inputValue,
        sender: 'user',
        timestamp: new Date(),
        type: 'text'
      };

      setMessages(prev => [...prev, newMessage]);
      setInputValue('');
    }

    // Handle file upload if present
    if (selectedFile) {
      const fileInfoMessage: Message = {
        id: `file-${Date.now()}`,
        content: `📁 Uploading: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(2)} KB)`,
        sender: 'user',
        timestamp: new Date(),
        type: 'file'
      };

      if (!inputValue.trim()) {
        // If only file is being sent
        setMessages(prev => [...prev, fileInfoMessage]);
      } else {
        // If both text and file are sent, update the text message to include file info
        setMessages(prev => {
          const lastMessage = prev[prev.length - 1];
          lastMessage.content += `\n📁 File: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(2)} KB)`;
          return [...prev.slice(0, -1), lastMessage];
        });
      }

      try {
        const uploadResponse = await chatService.uploadFile(selectedFile, sessionId);
        fileProcessed = true;
        console.log('File uploaded:', uploadResponse);
      } catch (error) {
        console.error('File upload error:', error);
        setMessages(prev => [...prev, {
          id: `error-${Date.now()}`,
          content: `Failed to upload file: ${selectedFile.name}`,
          sender: 'system',
          timestamp: new Date(),
          type: 'text'
        }]);
      }

      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }

    setIsLoading(true);

    try {
      // Get AI response
      const response = await chatService.sendMessage(
        inputValue || (selectedFile ? `Processing file: ${selectedFile.name}` : ''),
        sessionId
      );

      const aiMessage: Message = {
        id: `ai-${Date.now()}`,
        content: response.response,
        sender: 'assistant',
        timestamp: new Date(),
        type: 'text'
      };

      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
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

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);

      // Show preview message
      const previewMessage: Message = {
        id: `preview-${Date.now()}`,
        content: `📄 Selected: ${file.name} (${(file.size / 1024).toFixed(2)} KB) - Processing...`,
        sender: 'user',
        timestamp: new Date(),
        type: 'file'
      };

      setMessages(prev => [...prev, previewMessage]);

      // Remove preview after processing
      setTimeout(() => {
        setMessages(prev => prev.filter(msg => msg.id !== `preview-${Date.now()}`));
      }, 1000);
    }
  };

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages Container */}
      <div className="flex-grow overflow-y-auto mb-4 space-y-4 pr-2">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl p-4 ${
                message.sender === 'user'
                  ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-br-none'
                  : message.sender === 'system'
                  ? 'bg-yellow-900/30 text-yellow-200 border border-yellow-800/50'
                  : 'bg-slate-800/50 text-slate-100 rounded-bl-none'
              }`}
            >
              <div className="flex items-start space-x-2">
                {message.sender !== 'user' && (
                  <div className="mt-0.5">
                    {message.sender === 'assistant' ? (
                      <Bot size={18} className="text-cyan-400" />
                    ) : (
                      <div className="w-5 h-5 rounded-full bg-yellow-500 flex items-center justify-center">
                        <span className="text-xs font-bold text-black">!</span>
                      </div>
                    )}
                  </div>
                )}

                <div className="flex-1">
                  <div className="font-medium text-xs mb-1 opacity-80">
                    {message.sender === 'user' ? 'You' : message.sender === 'assistant' ? 'Assistant' : 'System'}
                    <span className="ml-2 text-[10px] opacity-60">{formatTime(message.timestamp)}</span>
                  </div>
                  <div className="whitespace-pre-wrap break-words">
                    {message.content}
                  </div>
                </div>

                {message.sender === 'user' && (
                  <div className="mt-0.5">
                    <User size={18} className="text-blue-300" />
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-2xl p-4 bg-slate-800/50 text-slate-100 rounded-bl-none">
              <div className="flex items-center space-x-2">
                <Bot size={18} className="text-cyan-400" />
                <div className="font-medium text-xs mb-1 opacity-80">Assistant</div>
              </div>
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"></div>
                <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce delay-75"></div>
                <div className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce delay-150"></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="border-t border-slate-700 pt-4">
        {selectedFile && (
          <div className="mb-3 flex items-center justify-between bg-slate-800/50 p-2 rounded-lg">
            <div className="flex items-center space-x-2 text-sm">
              <FileText size={16} className="text-blue-400" />
              <span className="truncate max-w-xs">{selectedFile.name}</span>
              <span className="text-xs text-slate-400">({(selectedFile.size / 1024).toFixed(2)} KB)</span>
            </div>
            <button
              onClick={() => {
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }}
              className="text-red-400 hover:text-red-300"
            >
              ✕
            </button>
          </div>
        )}

        <div className="relative flex">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message here... (Supports text, image, file)"
            disabled={isLoading}
            className="flex-grow bg-slate-800/50 border border-slate-600 rounded-l-xl py-3 px-4 text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
          />

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept="image/*,.pdf,.doc,.docx,.txt,.csv"
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
            className="bg-slate-700 hover:bg-slate-600 border-r border-slate-600 px-3 text-slate-300 disabled:opacity-50"
            title="Attach file"
          >
            <PlusCircle size={20} />
          </button>

          <button
            onClick={handleSend}
            disabled={!inputValue.trim() && !selectedFile || isLoading}
            className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50 text-white px-5 rounded-r-xl transition-all duration-200 flex items-center"
          >
            <Send size={18} />
          </button>
        </div>

        <div className="mt-2 text-xs text-slate-500 text-center">
          Send messages with text, images, or files. Press Enter to send.
        </div>
      </div>
    </div>
  );
};

export default ChatInterface;