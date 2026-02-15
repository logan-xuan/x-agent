/** FlowCanvas - React Flow canvas for trace visualization */

import { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';

import {
  ApiNode,
  AgentNode,
  LlmNode,
  MemoryNode,
  MiddlewareNode,
  DefaultNode,
} from './index';
import type { FlowNode as TraceFlowNode, FlowEdge as TraceFlowEdge } from '@/types';

const nodeTypes = {
  api: ApiNode,
  agent: AgentNode,
  llm: LlmNode,
  memory: MemoryNode,
  middleware: MiddlewareNode,
  default: DefaultNode,
};

interface FlowCanvasProps {
  nodes: TraceFlowNode[];
  edges: TraceFlowEdge[];
  onNodeClick?: (nodeId: string) => void;
}

function FlowCanvas({ nodes: initialNodes, edges: initialEdges, onNodeClick }: FlowCanvasProps) {
  // Convert trace nodes/edges to React Flow format
  const nodes: Node[] = useMemo(
    () =>
      initialNodes.map((node) => ({
        id: node.id,
        type: node.type,
        position: node.position,
        data: node.data,
      })),
    [initialNodes]
  );

  const edges: Edge[] = useMemo(
    () =>
      initialEdges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        animated: edge.animated,
        type: edge.type || 'default',
      })),
    [initialEdges]
  );

  const [nodesState, setNodes, onNodesChange] = useNodesState(nodes);
  const [edgesState, setEdges, onEdgesChange] = useEdgesState(edges);

  // Update nodes/edges when props change
  useMemo(() => {
    setNodes(nodes);
    setEdges(edges);
  }, [nodes, edges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeClick?.(node.id);
    },
    [onNodeClick]
  );

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodesState}
        edges={edgesState}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: 'smoothstep',
          style: { strokeWidth: 2, stroke: '#94a3b8' },
        }}
      >
        <Background color="#e2e8f0" gap={16} />
        <Controls />
        <MiniMap
          nodeColor={(node) => {
            switch (node.type) {
              case 'api':
                return '#3b82f6';
              case 'agent':
                return '#a855f7';
              case 'llm':
                return '#f59e0b';
              case 'memory':
                return '#22c55e';
              case 'middleware':
                return '#06b6d4';
              default:
                return '#64748b';
            }
          }}
          maskColor="rgba(0, 0, 0, 0.1)"
        />
      </ReactFlow>
    </div>
  );
}

export default FlowCanvas;
