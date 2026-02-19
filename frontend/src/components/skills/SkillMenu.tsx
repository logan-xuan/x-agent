import { useState, useRef, useEffect } from 'react';
import { Skill } from '@/services/api';

interface SkillMenuProps {
  skills: Skill[];
  onSelect: (skillName: string) => void;
  onClose: () => void;
  anchorPosition?: { x: number; y: number };
}

export function SkillMenu({ skills, onSelect, onClose, anchorPosition }: SkillMenuProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const filteredSkills = skills.filter(s => s.user_invocable);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => (prev + 1) % filteredSkills.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => (prev - 1 + filteredSkills.length) % filteredSkills.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredSkills[selectedIndex]) {
          onSelect(filteredSkills[selectedIndex].name);
        }
      } else if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [filteredSkills.length, selectedIndex, onSelect, onClose]);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  if (filteredSkills.length === 0) {
    return null;
  }

  return (
    <div
      ref={menuRef}
      className="fixed z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-80 overflow-y-auto"
      style={{
        left: anchorPosition?.x || 0,
        top: anchorPosition?.y || 0,
        minWidth: '300px',
        maxWidth: '500px',
      }}
    >
      <div className="p-2 border-b border-gray-200 dark:border-gray-700">
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
          可用技能 ({filteredSkills.length})
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          使用 ↑↓ 导航，Enter 选择，Esc 关闭
        </div>
      </div>
      
      <div className="py-1">
        {filteredSkills.map((skill, index) => (
          <button
            key={skill.name}
            onClick={() => onSelect(skill.name)}
            className={`w-full px-4 py-2 text-left flex items-start gap-3 transition-colors ${
              index === selectedIndex
                ? 'bg-blue-50 dark:bg-blue-900/20'
                : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  /{skill.name}
                </span>
                {skill.argument_hint && typeof skill.argument_hint === 'string' && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">
                    {skill.argument_hint}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                {typeof skill.description === 'string' ? skill.description : JSON.stringify(skill.description)}
              </p>
              {skill.allowed_tools && (
                <div className="flex items-center gap-1 mt-1 flex-wrap">
                  <span className="text-xs text-gray-500 dark:text-gray-400">工具:</span>
                  {skill.allowed_tools.slice(0, 3).map(tool => (
                    <span
                      key={tool}
                      className="text-xs text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded"
                    >
                      {tool}
                    </span>
                  ))}
                  {skill.allowed_tools.length > 3 && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      +{skill.allowed_tools.length - 3}
                    </span>
                  )}
                </div>
              )}
            </div>
            {index === selectedIndex && (
              <div className="text-blue-600 dark:text-blue-400 text-sm">→</div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
