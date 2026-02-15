/** LLM node component for trace visualization */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { FlowNodeData } from '@/types';

/** LLM node for LLM call events */
function LlmNode({ data }: NodeProps<FlowNodeData>) {
  const latencyMs = data.latency_ms as number | undefined;
  const model = data.model as string | undefined;
  const provider = data.provider as string | undefined;
  
  return (
    <div className="px-4 py-2 shadow-md rounded-md bg-amber-50 border-2 border-amber-400 min-w-[180px]">
      <Handle type="target" position={Position.Top} className="w-2 h-2 !bg-amber-400" />
      
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <span className="text-amber-500 text-lg">✨</span>
          <div className="text-xs font-semibold text-amber-600 uppercase">
            LLM
          </div>
        </div>
        <div className="text-sm font-semibold text-gray-800 truncate">
          {data.label}
        </div>
        {model && (
          <div className="text-xs text-amber-600 font-medium">
            {model}
          </div>
        )}
        {provider && (
          <div className="text-xs text-gray-500">
            Provider: {provider}
          </div>
        )}
        {data.timestamp && (
          <div className="text-xs text-gray-500">
            {data.timestamp.split('T')[1]?.split('.')[0] || data.timestamp.split(' ')[1]?.split('.')[0]}
          </div>
        )}
        {latencyMs !== undefined && (
          <div className={`text-xs px-2 py-0.5 rounded inline-block w-fit ${
            latencyMs > 3000 ? 'bg-red-100 text-red-600' :
            latencyMs > 1000 ? 'bg-yellow-100 text-yellow-600' :
            'bg-green-100 text-green-600'
          }`}>
            {latencyMs}ms
          </div>
        )}
      </div>
      
      <Handle type="source" position={Position.Bottom} className="w-2 h-2 !bg-amber-400" />
    </div>
  );
}

export default memo(LlmNode);
