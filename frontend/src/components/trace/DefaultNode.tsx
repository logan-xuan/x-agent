/** Default node component for trace visualization */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { FlowNodeData } from '@/types';

/** Default node for generic events */
function DefaultNode({ data }: NodeProps<FlowNodeData>) {
  return (
    <div className="px-4 py-2 shadow-md rounded-md bg-white border-2 border-gray-300 min-w-[180px]">
      <Handle type="target" position={Position.Top} className="w-2 h-2" />
      
      <div className="flex flex-col gap-1">
        <div className="text-xs font-medium text-gray-500">
          {data.module?.split('.').pop()}
        </div>
        <div className="text-sm font-semibold text-gray-700 truncate">
          {data.label}
        </div>
        {data.timestamp && (
          <div className="text-xs text-gray-400">
            {data.timestamp.split('T')[1]?.split('.')[0] || data.timestamp.split(' ')[1]?.split('.')[0]}
          </div>
        )}
      </div>
      
      <Handle type="source" position={Position.Bottom} className="w-2 h-2" />
    </div>
  );
}

export default memo(DefaultNode);
