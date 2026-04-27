import { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { Layers, ChevronDown, ChevronRight, Cpu } from 'lucide-react';

export const SubgraphNode = memo(({ data, isConnectable }: any) => {
  return (
    <div className={`px-4 py-3 shadow-md rounded-md bg-purple-50 border-2 ${data.isExpanded ? 'border-purple-500' : 'border-purple-200'} min-w-[220px]`}>
      <Handle type="target" position={Position.Top} isConnectable={isConnectable} className="w-3 h-3 bg-purple-400" />
      
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-purple-100 rounded-md text-purple-600">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-bold text-gray-800">{data.label}</div>
            <div className="text-xs text-purple-600 font-medium">Subgraph</div>
          </div>
        </div>
        
        <button 
          onClick={data.onToggleExpand}
          className="p-1 hover:bg-purple-100 rounded-full text-purple-500 transition-colors"
          title={data.isExpanded ? "Collapse Subgraph" : "Expand Subgraph"}
        >
          {data.isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>
      
      {data.isExpanded && data.subgraphPath && (
        <div className="mt-3 pt-2 border-t border-purple-200 text-xs text-gray-500">
          <div className="font-mono bg-white px-2 py-1 rounded border border-purple-100 overflow-hidden text-ellipsis">
            {data.subgraphPath}
          </div>
          <div className="mt-2 text-center text-purple-400 italic">
            (Child nodes rendered below)
          </div>
        </div>
      )}

      <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} className="w-3 h-3 bg-purple-400" />
    </div>
  );
});

export const AgentNode = memo(({ data, isConnectable }: any) => {
  return (
    <div className="px-4 py-3 shadow-md rounded-md bg-blue-50 border border-blue-200 min-w-[220px]">
      <Handle type="target" position={Position.Top} isConnectable={isConnectable} className="w-3 h-3 bg-blue-400" />
      
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-100 rounded-md text-blue-600">
            <Cpu className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-bold text-gray-800">{data.label}</div>
            <div className="text-xs text-blue-600 font-medium">Agent-Loop</div>
          </div>
        </div>
      </div>

      {/* LLM Selector */}
      <div className="mt-2 pt-2 border-t border-blue-100">
        <select 
          className="w-full text-xs bg-white border border-blue-200 rounded px-2 py-1 text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-400"
          defaultValue={data.tier || 'balanced'}
        >
          <optgroup label="Tier: Premium">
            <option value="claude-3-opus">Claude 3 Opus</option>
            <option value="gpt-4">GPT-4</option>
          </optgroup>
          <optgroup label="Tier: Balanced">
            <option value="claude-3-sonnet">Claude 3 Sonnet</option>
            <option value="gpt-4o">GPT-4o</option>
            <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
          </optgroup>
          <optgroup label="Tier: Fast">
            <option value="claude-3-haiku">Claude 3 Haiku</option>
            <option value="gpt-3.5-turbo">GPT-3.5 Turbo</option>
          </optgroup>
        </select>
      </div>

      <Handle type="source" position={Position.Bottom} isConnectable={isConnectable} className="w-3 h-3 bg-blue-400" />
    </div>
  );
});
