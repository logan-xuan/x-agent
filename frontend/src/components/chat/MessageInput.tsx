/** User input component with send button */

import { useState, useRef, useEffect } from 'react';
import { Skill } from '@/services/api';
import { SkillMenu } from './SkillMenu';

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  skills?: Skill[];
}

export function MessageInput({
  onSend,
  disabled = false,
  placeholder = '输入消息...',
  skills = []
}: MessageInputProps) {
  const [message, setMessage] = useState('');
  const [isComposing, setIsComposing] = useState(false); // Track IME composition state
  const [showSkillMenu, setShowSkillMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ x: number; y: number } | undefined>();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Focus textarea on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // Handle skill selection
  const handleSkillSelect = (skillName: string) => {
    const currentText = message;
    const lastSlashIndex = currentText.lastIndexOf('/');
    
    let newMessage: string;
    if (lastSlashIndex !== -1) {
      // Replace the text after last /
      newMessage = currentText.substring(0, lastSlashIndex + 1) + skillName + ' ';
    } else {
      newMessage = `/${skillName} `;
    }
    
    setMessage(newMessage);
    setShowSkillMenu(false);
    textareaRef.current?.focus();
  };

  // Check for / trigger
  const checkForSkillTrigger = () => {
    const cursorPosition = textareaRef.current?.selectionStart || 0;
    const textBeforeCursor = message.substring(0, cursorPosition);
    const lastSlashIndex = textBeforeCursor.lastIndexOf('/');
    
    // Show menu if / is the last character or followed by space/letters
    if (lastSlashIndex !== -1) {
      const afterSlash = textBeforeCursor.substring(lastSlashIndex + 1);
      if (afterSlash === '' || /^[a-zA-Z0-9_-]*$/.test(afterSlash)) {
        // Calculate position
        const textarea = textareaRef.current;
        if (textarea) {
          const rect = textarea.getBoundingClientRect();
          setMenuPosition({
            x: rect.left,
            y: rect.top - 300, // Show above input
          });
          setShowSkillMenu(true);
        }
      }
    } else {
      setShowSkillMenu(false);
    }
  };

  const handleSend = () => {
    const trimmedMessage = message.trim();
    if (trimmedMessage && !disabled) {
      onSend(trimmedMessage);
      setMessage('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Close menu on Escape
    if (e.key === 'Escape' && showSkillMenu) {
      setShowSkillMenu(false);
      return;
    }
    
    // Send on Enter (without Shift) but only when not composing (IME input)
    if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = message.trim().length > 0 && !disabled;
  
  // Handle composition events for IME input (Chinese, Japanese, Korean, etc.)
  const handleCompositionStart = () => {
    setIsComposing(true);
  };

  const handleCompositionEnd = () => {
    setIsComposing(false);
  };
  
  return (
    <div className="p-2 sm:p-4">
      <div className="flex items-end gap-2 sm:gap-3">
        {/* Textarea */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value);
              checkForSkillTrigger();
            }}
            onKeyDown={handleKeyDown}
            onCompositionStart={handleCompositionStart}
            onCompositionEnd={handleCompositionEnd}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="mobile-input w-full resize-none rounded-2xl border border-gray-300 dark:border-gray-600
                       bg-gray-50 dark:bg-gray-800 px-3 sm:px-4 py-2.5 sm:py-3 pr-10 sm:pr-12
                       text-gray-900 dark:text-gray-100 placeholder-gray-500
                       focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                       disabled:opacity-50 disabled:cursor-not-allowed
                       transition-colors"
          />
          
          {/* Skill menu */}
          {showSkillMenu && skills.length > 0 && (
            <SkillMenu
              skills={skills}
              onSelect={handleSkillSelect}
              onClose={() => setShowSkillMenu(false)}
              anchorPosition={menuPosition}
            />
          )}
          
          {/* Character count - hidden on mobile */}
          {message.length > 0 && (
            <span className="hidden sm:block absolute right-3 bottom-2 text-xs text-gray-400">
              {message.length}
            </span>
          )}
        </div>
        
        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!canSend}
          className="touch-target flex-shrink-0 w-11 h-11 sm:w-12 sm:h-12 rounded-full
                     bg-blue-600 hover:bg-blue-700 active:bg-blue-800
                     disabled:bg-gray-300 disabled:dark:bg-gray-700 disabled:cursor-not-allowed
                     text-white transition-colors
                     flex items-center justify-center"
          title="发送消息 (Enter)"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
            />
          </svg>
        </button>
      </div>
      
      {/* Help text - hidden on mobile */}
      <p className="hidden sm:block text-xs text-gray-400 mt-2 text-center">
        按 Enter 发送，Shift + Enter 换行
      </p>
    </div>
  );
}
