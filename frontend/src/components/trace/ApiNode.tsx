/** API node component for trace visualization */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { FlowNodeData } from '@/types';

/** API node for API endpoint events */
function ApiNode({ data }: NodeProps<FlowNodeData>) {
  return (
    <div className="px-4 py-2 shadow-md rounded-md bg-blue-50 border-2 border-blue-400 min-w-[180px]">
      <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-blue-400" />
      
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-blue-500 text-lg">🌐</span>
          <div className="text-xs font-semibold text-blue-600 uppercase">
            API
          </div>
        </div>
        <div className="text-sm font-semibold text-gray-800 truncate">
          {data.label}
        </div>
        {data.timestamp && (
          <div className="text-xs text-gray-500">
            {data.timestamp.split('T')[1]?.split('.')[0] || data.timestamp.split(' ')[1]?.split('.')[0]}
          </div>
        )}
        {data.level && (
          <div className={`text-xs px-2 py-0.5 rounded inline-block w-fit ${
            data.level === 'error' ? 'bg-red-100 text-red-600' :
            data.level === 'warning' ? 'bg-yellow-100 text-yellow-600' :
            'bg-green-100 text-green-600'
          }`}>
            {data.level}
          </div>
        )}
      </div>
      
      <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-blue-400" />
    </div>
  );
}

export default memo(ApiNode);
