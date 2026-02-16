/** Developer Mode Window - Main container for dev tools */

import { useState, useEffect, useRef } from 'react';
import { PromptLogList } from './PromptLogList';
import { PromptTester } from './PromptTester';
import { TraceViewer } from '../trace';
import { MemorySearchDebugger } from './MemorySearchDebugger';
import { Button } from '../ui/Button';

type TabType = 'logs' | 'tester' | 'trace' | 'search';

interface DevModeWindowProps {
  isOpen: boolean;
  onClose: () => void;
}

export function DevModeWindow({ isOpen, onClose }: DevModeWindowProps) {
  const [activeTab, setActiveTab] = useState<TabType>('logs');
  const [error, setError] = useState<string | null>(null);
  const [traceId, setTraceId] = useState<string>('');
  
  // Handle viewing trace from log list
  const handleViewTrace = (id: string) => {
    setTraceId(id);
    setActiveTab('trace');
  };
  
  // Calculate initial position (right side of screen with some margin)
  const getInitialPosition = () => {
    const margin = 20;
    const windowWidth = 1200; // Increased from 900 to provide more space
    return {
      x: window.innerWidth - windowWidth - margin,
      y: margin + 60, // Add some top margin for header
    };
  };
  
  const [position, setPosition] = useState(getInitialPosition());
  const [isDragging, setIsDragging] = useState(false);
  const [size, setSize] = useState({ width: 1200, height: 800 }); // Increased from 900x700 to 1200x800
  const [isResizing, setIsResizing] = useState(false);

  const dragStartRef = useRef({ x: 0, y: 0 });
  const resizeStartRef = useRef({ width: 0, height: 0, x: 0, y: 0 });
  const windowRef = useRef<HTMLDivElement>(null);

  // Handle drag start
  const handleDragStart = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.dev-window-header')) {
      setIsDragging(true);
      dragStartRef.current = {
        x: e.clientX - position.x,
        y: e.clientY - position.y,
      };
    }
  };

  // Handle resize start
  const handleResizeStart = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsResizing(true);
    resizeStartRef.current = {
      width: size.width,
      height: size.height,
      x: e.clientX,
      y: e.clientY,
    };
  };

  // Handle mouse move for drag and resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        setPosition({
          x: Math.max(0, e.clientX - dragStartRef.current.x),
          y: Math.max(0, e.clientY - dragStartRef.current.y),
        });
      }
      if (isResizing) {
        const newWidth = Math.max(600, resizeStartRef.current.width + (e.clientX - resizeStartRef.current.x)); // Increased from 400 to 600
        const newHeight = Math.max(400, resizeStartRef.current.height + (e.clientY - resizeStartRef.current.y)); // Increased from 300 to 400
        setSize({ width: newWidth, height: newHeight });
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(false);
    };

    if (isDragging || isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, isResizing]);

  // Handle escape key to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Reset position when window opens
  useEffect(() => {
    if (isOpen) {
      setPosition(getInitialPosition());
    }
  }, [isOpen]);

  // Clear error when switching tabs
  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
    setError(null);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 z-40" onClick={onClose} />

      {/* Window */}
      <div
        ref={windowRef}
        className="fixed z-50 bg-white dark:bg-gray-900 rounded-lg shadow-2xl border border-gray-200 dark:border-gray-700 flex flex-col overflow-hidden"
        style={{
          left: position.x,
          top: position.y,
          width: size.width,
          height: size.height,
          cursor: isDragging ? 'grabbing' : 'default',
        }}
      >
        {/* Header - Draggable */}
        <div
          className="dev-window-header flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 cursor-grab active:cursor-grabbing select-none"
          onMouseDown={handleDragStart}
        >
          <div className="flex items-center gap-2">
            <svg
              className="w-5 h-5 text-gray-500 dark:text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
              />
            </svg>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
              开发者模式
            </h2>
          </div>

          <div className="flex items-center gap-2">
            {/* Tab Buttons */}
            <div className="flex items-center bg-gray-200 dark:bg-gray-700 rounded-md p-0.5 mr-2">
              <button
                onClick={() => handleTabChange('logs')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  activeTab === 'logs'
                    ? 'bg-white dark:bg-gray-600 text-gray-800 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
                }`}
              >
                交互记录
              </button>
              <button
                onClick={() => handleTabChange('tester')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  activeTab === 'tester'
                    ? 'bg-white dark:bg-gray-600 text-gray-800 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
                }`}
              >
                Prompt测试
              </button>
              <button
                onClick={() => handleTabChange('trace')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  activeTab === 'trace'
                    ? 'bg-white dark:bg-gray-600 text-gray-800 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
                }`}
              >
                Trace
              </button>
              <button
                onClick={() => handleTabChange('search')}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  activeTab === 'search'
                    ? 'bg-white dark:bg-gray-600 text-gray-800 dark:text-white shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200'
                }`}
              >
                搜索调试
              </button>
            </div>

            {/* Close Button */}
            <Button variant="ghost" size="sm" onClick={onClose} className="h-8 w-8 p-0">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </Button>
          </div>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800 px-4 py-2 flex items-center justify-between">
            <span className="text-sm text-red-600 dark:text-red-400">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {activeTab === 'logs' ? (
            <PromptLogList onError={setError} onViewTrace={handleViewTrace} />
          ) : activeTab === 'tester' ? (
            <PromptTester onError={setError} />
          ) : activeTab === 'trace' ? (
            <TraceViewer initialTraceId={traceId} />
          ) : (
            <MemorySearchDebugger onError={setError} />
          )}
        </div>

        {/* Resize Handle */}
        <div
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
          onMouseDown={handleResizeStart}
        >
          <svg
            className="w-4 h-4 text-gray-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 19L5 5m14 0v14M5 5h14"
              transform="rotate(180 12 12)"
            />
          </svg>
        </div>
      </div>
    </>
  );
}
