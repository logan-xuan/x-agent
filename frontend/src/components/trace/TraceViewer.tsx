/** TraceViewer - Main trace visualization component */

import { useState, useCallback, useEffect } from 'react';
import FlowCanvas from './FlowCanvas';
import { getTraceFlow, analyzeTrace } from '@/services/api';
import type { 
  TraceFlowResponse, 
  TraceDetailLevel,
  TraceAnalysisResponse,
  FlowNode as TraceFlowNode,
} from '@/types';

interface TraceViewerProps {
  initialTraceId?: string;
  onClose?: () => void;
}

function TraceViewer({ initialTraceId = '', onClose }: TraceViewerProps) {
  const [traceId, setTraceId] = useState(initialTraceId);
  const [detailLevel, setDetailLevel] = useState<TraceDetailLevel>('medium');
  const [flowData, setFlowData] = useState<TraceFlowResponse | null>(null);
  const [analysis, setAnalysis] = useState<TraceAnalysisResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<TraceFlowNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'flow' | 'analysis'>('flow');

  // Fetch trace flow data
  const fetchFlowData = useCallback(async (id: string) => {
    if (!id) return;
    
    setLoading(true);
    setError(null);
    setAnalysis(null);
    
    try {
      const data = await getTraceFlow(id, detailLevel);
      setFlowData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trace data');
      setFlowData(null);
    } finally {
      setLoading(false);
    }
  }, [detailLevel]);

  // Fetch when traceId or detailLevel changes
  useEffect(() => {
    if (traceId) {
      fetchFlowData(traceId);
    }
  }, [traceId, detailLevel, fetchFlowData]);

  // Handle analyze button
  const handleAnalyze = useCallback(async () => {
    if (!traceId) return;
    
    setAnalyzing(true);
    try {
      const result = await analyzeTrace(traceId, {
        focus_areas: ['performance', 'error'],
        include_suggestions: true,
      });
      setAnalysis(result);
      setActiveTab('analysis');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze trace');
    } finally {
      setAnalyzing(false);
    }
  }, [traceId]);

  // Handle node click
  const handleNodeClick = useCallback((nodeId: string) => {
    const node = flowData?.nodes.find(n => n.id === nodeId);
    if (node) {
      setSelectedNode(node);
    }
  }, [flowData]);

  return (
    <div className="h-full w-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h2 className="text-lg font-semibold text-gray-800">Trace Viewer</h2>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={traceId}
                onChange={(e) => setTraceId(e.target.value)}
                placeholder="Enter Trace ID"
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-80"
              />
              <select
                value={detailLevel}
                onChange={(e) => setDetailLevel(e.target.value as TraceDetailLevel)}
                className="px-3 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="high">High Level</option>
                <option value="medium">Medium</option>
                <option value="detailed">Detailed</option>
              </select>
              <button
                onClick={() => fetchFlowData(traceId)}
                disabled={loading || !traceId}
                className="px-4 py-1.5 bg-blue-500 text-white rounded-md text-sm hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Loading...' : 'Load'}
              </button>
              <button
                onClick={handleAnalyze}
                disabled={analyzing || !flowData}
                className="px-4 py-1.5 bg-purple-500 text-white rounded-md text-sm hover:bg-purple-600 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {analyzing ? 'Analyzing...' : 'Analyze'}
              </button>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-4 py-2 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Tabs for flow/analysis */}
        <div className="flex-1 flex flex-col">
          <div className="bg-white border-b border-gray-200 px-4">
            <div className="flex gap-4">
              <button
                onClick={() => setActiveTab('flow')}
                className={`py-2 px-1 text-sm font-medium border-b-2 ${
                  activeTab === 'flow'
                    ? 'text-blue-600 border-blue-600'
                    : 'text-gray-500 border-transparent hover:text-gray-700'
                }`}
              >
                Flow
              </button>
              <button
                onClick={() => setActiveTab('analysis')}
                className={`py-2 px-1 text-sm font-medium border-b-2 ${
                  activeTab === 'analysis'
                    ? 'text-blue-600 border-blue-600'
                    : 'text-gray-500 border-transparent hover:text-gray-700'
                }`}
              >
                Analysis {analysis && `(${analysis.insights.length})`}
              </button>
            </div>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'flow' && (
              flowData ? (
                <FlowCanvas
                  nodes={flowData.nodes}
                  edges={flowData.edges}
                  onNodeClick={handleNodeClick}
                />
              ) : (
                <div className="h-full flex items-center justify-center text-gray-500">
                  {loading ? 'Loading trace data...' : 'Enter a Trace ID to visualize'}
                </div>
              )
            )}
            
            {activeTab === 'analysis' && (
              <div className="h-full overflow-auto p-4">
                {analysis ? (
                  <div className="space-y-4">
                    {/* Analysis text */}
                    <div className="bg-white rounded-lg border border-gray-200 p-4">
                      <h3 className="text-sm font-semibold text-gray-700 mb-2">Analysis</h3>
                      <pre className="text-sm text-gray-600 whitespace-pre-wrap font-mono">
                        {analysis.analysis}
                      </pre>
                    </div>

                    {/* Insights */}
                    {analysis.insights.length > 0 && (
                      <div className="bg-white rounded-lg border border-gray-200 p-4">
                        <h3 className="text-sm font-semibold text-gray-700 mb-2">Insights</h3>
                        <div className="space-y-2">
                          {analysis.insights.map((insight, idx) => (
                            <div
                              key={idx}
                              className={`p-3 rounded-md border ${
                                insight.severity === 'high' ? 'bg-red-50 border-red-200' :
                                insight.severity === 'medium' ? 'bg-yellow-50 border-yellow-200' :
                                'bg-green-50 border-green-200'
                              }`}
                            >
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-semibold uppercase text-gray-500">
                                  {insight.type}
                                </span>
                                {insight.severity && (
                                  <span className={`text-xs px-2 py-0.5 rounded ${
                                    insight.severity === 'high' ? 'bg-red-200 text-red-700' :
                                    insight.severity === 'medium' ? 'bg-yellow-200 text-yellow-700' :
                                    'bg-green-200 text-green-700'
                                  }`}>
                                    {insight.severity}
                                  </span>
                                )}
                              </div>
                              <div className="font-medium text-gray-800 mt-1">{insight.title}</div>
                              <div className="text-sm text-gray-600 mt-1">{insight.description}</div>
                              {insight.location && (
                                <div className="text-xs text-gray-500 mt-1">📍 {insight.location}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Suggestions */}
                    {analysis.suggestions.length > 0 && (
                      <div className="bg-white rounded-lg border border-gray-200 p-4">
                        <h3 className="text-sm font-semibold text-gray-700 mb-2">Suggestions</h3>
                        <ul className="space-y-1">
                          {analysis.suggestions.map((suggestion, idx) => (
                            <li key={idx} className="text-sm text-gray-600 flex items-start gap-2">
                              <span className="text-green-500">•</span>
                              {suggestion}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center text-gray-500">
                    {analyzing ? 'Analyzing trace...' : 'Click "Analyze" to analyze the trace with LLM'}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Side panel for metadata */}
        {flowData && activeTab === 'flow' && (
          <div className="w-80 bg-white border-l border-gray-200 overflow-auto">
            <div className="p-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Trace Info</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Trace ID:</span>
                  <span className="text-gray-800 font-mono text-xs truncate max-w-[180px]">
                    {flowData.metadata.trace_id}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Nodes:</span>
                  <span className="text-gray-800">{flowData.metadata.total_nodes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Edges:</span>
                  <span className="text-gray-800">{flowData.metadata.total_edges}</span>
                </div>
                {flowData.metadata.total_duration_ms > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Duration:</span>
                    <span className="text-gray-800">{flowData.metadata.total_duration_ms}ms</span>
                  </div>
                )}
              </div>

              {/* Execution path */}
              <div className="mt-4">
                <h3 className="text-sm font-semibold text-gray-700 mb-2">Execution Path</h3>
                <div className="text-xs text-gray-600 space-y-1">
                  {flowData.metadata.execution_path.map((step, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <span className="text-gray-400">{idx + 1}.</span>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Selected node details */}
              {selectedNode && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">Selected Node</h3>
                  <div className="space-y-2 text-sm">
                    <div>
                      <span className="text-gray-500">Label:</span>
                      <div className="text-gray-800 font-medium">{selectedNode.data.label}</div>
                    </div>
                    <div>
                      <span className="text-gray-500">Module:</span>
                      <div className="text-gray-800">{selectedNode.data.module}</div>
                    </div>
                    {selectedNode.data.timestamp && (
                      <div>
                        <span className="text-gray-500">Timestamp:</span>
                        <div className="text-gray-800">{selectedNode.data.timestamp}</div>
                      </div>
                    )}
                    {selectedNode.data.level && (
                      <div>
                        <span className="text-gray-500">Level:</span>
                        <div className={`inline-block px-2 py-0.5 rounded text-xs ${
                          selectedNode.data.level === 'error' ? 'bg-red-100 text-red-600' :
                          selectedNode.data.level === 'warning' ? 'bg-yellow-100 text-yellow-600' :
                          'bg-green-100 text-green-600'
                        }`}>
                          {selectedNode.data.level}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TraceViewer;
