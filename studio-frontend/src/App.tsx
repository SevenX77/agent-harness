import { useState, useCallback, useEffect, useRef } from 'react';
import { ReactFlow, MiniMap, Controls, Background, useNodesState, useEdgesState, addEdge, MarkerType } from 'reactflow';
import type { Node, Edge } from 'reactflow';
import 'reactflow/dist/style.css';
import Editor from '@monaco-editor/react';
import { Play, CheckCircle, AlertCircle, FileText, Settings, Terminal, Copy, FolderOpen, Save, HardDrive, ChevronRight, Hash, MessageSquare } from 'lucide-react';
import yaml from 'js-yaml';
import { SubgraphNode, AgentNode } from './CustomNodes';

// API Base URL
const API_BASE_URL = 'http://localhost:8787/api';

const nodeTypes = {
  subgraph: SubgraphNode,
  agent: AgentNode
};

export default function App() {
  const [skills, setSkills] = useState<any[]>([]);
  const [activeSkillId, setActiveSkillId] = useState<string | null>(null);
  
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [skillCode, setSkillCode] = useState('');
  
  const [compileStatus, setCompileStatus] = useState<'idle' | 'compiling' | 'success' | 'error'>('idle');
  const [compileError, setCompileError] = useState('');
  
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const [activeTab, setActiveTab] = useState<'code' | 'trace' | 'settings'>('code');
  
  // Artifacts Manager State
  const [inputPath, setInputPath] = useState('workspaces/default/inputs/test.json');
  const [outputPath, setOutputPath] = useState('workspaces/default/outputs/result.md');
  const [isArtifactsMenuOpen, setIsArtifactsMenuOpen] = useState(false);
  
  // Settings State
  const [apiKeys, setApiKeys] = useState({
    openai: '',
    anthropic: '',
    gemini: ''
  });
  
  // Trace State
  const [traceLogs, setTraceLogs] = useState<any[]>([]);
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(new Set());
  const [selectedPromptIndex, setSelectedPromptIndex] = useState<number | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);

  const onConnect = useCallback((params: any) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  // Fetch skills list on load
  useEffect(() => {
    fetch(`${API_BASE_URL}/skills`)
      .then(res => res.json())
      .then(data => {
        setSkills(data.skills);
        if (data.skills.length > 0) {
          loadSkill(data.skills[0].id);
        }
      })
      .catch(err => console.error("Failed to fetch skills", err));
  }, []);

  // Parse skill code to graph nodes and edges
  const parseSkillToGraph = useCallback((code: string, expandedNodes: Set<string>) => {
    const newNodes: Node[] = [];
    const newEdges: Edge[] = [];
    
    // 1. Parse frontmatter for IO
    const frontmatterMatch = code.match(/^---\n([\s\S]*?)\n---/);
    let inputs = [];
    let outputs = [];
    if (frontmatterMatch) {
      try {
        const metadata: any = yaml.load(frontmatterMatch[1]);
        inputs = metadata?.io?.inputs || [];
        outputs = metadata?.io?.outputs || [];
      } catch (e) {
        console.error("Failed to parse frontmatter", e);
      }
    }

    // Add Input Node
    newNodes.push({
      id: 'input',
      type: 'input',
      data: { label: `Input: ${inputs.map((i: any) => i.name).join(', ') || 'None'}` },
      position: { x: 250, y: 50 },
      style: { background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '10px', minWidth: '200px', textAlign: 'center', fontWeight: 'bold', color: '#475569' }
    });

    // 2. Parse phase_configs
    const phaseRegex = /<phase_config>([\s\S]*?)<\/phase_config>/g;
    let match;
    let yPos = 150;
    const phases = [];

    while ((match = phaseRegex.exec(code)) !== null) {
      try {
        const phaseConfig: any = yaml.load(match[1]);
        if (phaseConfig && phaseConfig.name) {
          phases.push(phaseConfig);
          
          const isSubgraph = !!phaseConfig.subgraph;
          const isExpanded = expandedNodes.has(phaseConfig.name);
          
          newNodes.push({
            id: phaseConfig.name,
            type: isSubgraph ? 'subgraph' : 'agent',
            data: { 
              label: phaseConfig.name,
              isExpanded: isExpanded,
              subgraphPath: phaseConfig.subgraph,
              tier: phaseConfig.tier,
              onToggleExpand: () => toggleSubgraph(phaseConfig.name)
            },
            position: { x: 250, y: yPos }
          });

          // Add edges based on depends_on
          if (phaseConfig.depends_on) {
            const deps = Array.isArray(phaseConfig.depends_on) ? phaseConfig.depends_on : [phaseConfig.depends_on];
            deps.forEach((dep: string) => {
              newEdges.push({
                id: `e-${dep}-${phaseConfig.name}`,
                source: dep,
                target: phaseConfig.name,
                animated: true,
                markerEnd: { type: MarkerType.ArrowClosed },
                style: { stroke: '#94a3b8', strokeWidth: 2 }
              });
            });
          } else if (phases.length === 1) {
             // Connect first phase to input
             newEdges.push({
              id: `e-input-${phaseConfig.name}`,
              source: 'input',
              target: phaseConfig.name,
              animated: true,
              markerEnd: { type: MarkerType.ArrowClosed },
              style: { stroke: '#94a3b8', strokeWidth: 2 }
            });
          }

          // If expanded, add mock child nodes and adjust yPos
          if (isSubgraph && isExpanded) {
            yPos += 140;
            
            // Mock child nodes for expanded subgraph
            const child1Id = `${phaseConfig.name}_child1`;
            const child2Id = `${phaseConfig.name}_child2`;
            
            newNodes.push({
              id: child1Id,
              type: 'agent',
              data: { label: 'sub_phase_1', tier: 'balanced' },
              position: { x: 250, y: yPos },
              style: { opacity: 0.8, transform: 'scale(0.9)' }
            });
            
            newEdges.push({
              id: `e-${phaseConfig.name}-${child1Id}`,
              source: phaseConfig.name,
              target: child1Id,
              animated: true,
              style: { stroke: '#c084fc', strokeDasharray: '5,5' }
            });
            
            yPos += 120;
            
            newNodes.push({
              id: child2Id,
              type: 'agent',
              data: { label: 'sub_phase_2', tier: 'premium' },
              position: { x: 250, y: yPos },
              style: { opacity: 0.8, transform: 'scale(0.9)' }
            });
            
            newEdges.push({
              id: `e-${child1Id}-${child2Id}`,
              source: child1Id,
              target: child2Id,
              animated: true,
              style: { stroke: '#c084fc', strokeDasharray: '5,5' }
            });
            
            // The next main node should connect from child2Id
            phaseConfig._lastChildId = child2Id;
          }

          yPos += 140;
        }
      } catch (e) {
        console.error("Failed to parse phase_config", e);
      }
    }

    // Add Output Node
    newNodes.push({
      id: 'output',
      type: 'output',
      data: { label: `Output: ${outputs.map((o: any) => o.name).join(', ') || 'None'}` },
      position: { x: 250, y: yPos },
      style: { background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', padding: '10px', minWidth: '200px', textAlign: 'center', fontWeight: 'bold', color: '#166534' }
    });

    // Connect last phases to output
    const sources = new Set(newEdges.map(e => e.source));
    phases.forEach(p => {
      if (!sources.has(p.name) && !sources.has(p._lastChildId)) {
        const sourceId = p._lastChildId || p.name;
        newEdges.push({
          id: `e-${sourceId}-output`,
          source: sourceId,
          target: 'output',
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: '#94a3b8', strokeWidth: 2 }
        });
      }
    });

    return { newNodes, newEdges };
  }, []);

  const toggleSubgraph = useCallback((nodeId: string) => {
    setExpandedSubgraphs(prev => {
      const next = new Set<string>(); // Only allow one expanded at a time
      if (!prev.has(nodeId)) {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  // Update graph when code or expanded state changes
  useEffect(() => {
    if (skillCode) {
      const { newNodes, newEdges } = parseSkillToGraph(skillCode, expandedSubgraphs);
      setNodes(newNodes);
      setEdges(newEdges);
    }
  }, [skillCode, expandedSubgraphs, parseSkillToGraph, setNodes, setEdges]);

  // Load specific skill
  const loadSkill = async (skillId: string) => {
    try {
      const res = await fetch(`${API_BASE_URL}/skills/${skillId}`);
      const data = await res.json();
      setActiveSkillId(skillId);
      setSkillCode(data.content);
      setExpandedSubgraphs(new Set()); // Reset expansion state
      setCompileStatus('idle');
      setRunStatus('idle');
      setTraceLogs([]);
      setSelectedPromptIndex(null);
      setActiveTab('code');
    } catch (err) {
      console.error("Failed to load skill", err);
    }
  };

  const handleCompile = async () => {
    if (!activeSkillId) return;
    
    setCompileStatus('compiling');
    try {
      const res = await fetch(`${API_BASE_URL}/skills/${activeSkillId}/compile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: skillCode })
      });
      const data = await res.json();
      
      if (data.status === 'success') {
        setCompileStatus('success');
      } else {
        setCompileStatus('error');
        setCompileError(data.message);
      }
    } catch (err) {
      setCompileStatus('error');
      setCompileError(String(err));
    }
  };

  const handleRun = () => {
    if (compileStatus !== 'success' || !activeSkillId) {
      alert("请先编译通过后再运行！");
      return;
    }
    
    setRunStatus('running');
    setActiveTab('trace');
    setTraceLogs([]);
    setSelectedPromptIndex(null);
    
    const runId = `run_${Date.now()}`;
    
    if (wsRef.current) {
      wsRef.current.close();
    }
    
    const ws = new WebSocket(`ws://localhost:8787/ws/run/${runId}`);
    wsRef.current = ws;
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setTraceLogs(prev => [...prev, data]);
      
      if (data.type === 'complete') {
        setRunStatus('success');
        ws.close();
      }
    };
    
    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      setRunStatus('error');
    };
  };

  const copyErrorToClipboard = () => {
    navigator.clipboard.writeText(compileError);
    alert("错误信息已复制，可粘贴给您的编程助手 (如 Cursor/Claude) 进行修复。");
  };

  // Render Prompt Inspector Modal
  const renderPromptInspector = () => {
    if (selectedPromptIndex === null) return null;
    
    const log = traceLogs[selectedPromptIndex];
    if (!log || log.type !== 'llm_call') return null;

    // Mock prompt data
    const template = `你是一个产品专家。请从参数表中提取3-5个核心亮点。
输入数据：
{product_specs}`;
    
    const variables = `{
  "product_specs": {
    "name": "iPhone 15",
    "chip": "A16 Bionic",
    "camera": "48MP Main",
    "material": "Color-infused glass and aluminum"
  }
}`;

    const finalPrompt = `你是一个产品专家。请从参数表中提取3-5个核心亮点。
输入数据：
{
  "name": "iPhone 15",
  "chip": "A16 Bionic",
  "camera": "48MP Main",
  "material": "Color-infused glass and aluminum"
}`;

    return (
      <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-8">
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl h-[80vh] flex flex-col overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
            <h3 className="font-bold text-lg flex items-center gap-2 text-gray-800">
              <MessageSquare className="w-5 h-5 text-indigo-600" />
              Prompt Inspector: {log.phase}
            </h3>
            <button 
              onClick={() => setSelectedPromptIndex(null)}
              className="text-gray-500 hover:text-gray-800 p-1"
            >
              ✕
            </button>
          </div>
          
          <div className="flex-1 flex flex-col p-6 overflow-hidden">
            <div className="grid grid-cols-3 gap-4 h-full">
              <div className="flex flex-col border border-gray-200 rounded-lg overflow-hidden">
                <div className="bg-gray-100 px-3 py-2 text-xs font-bold text-gray-600 border-b border-gray-200">1. Template (模板)</div>
                <div className="flex-1 p-3 bg-gray-50 overflow-y-auto font-mono text-sm whitespace-pre-wrap">
                  {template}
                </div>
              </div>
              
              <div className="flex flex-col border border-gray-200 rounded-lg overflow-hidden">
                <div className="bg-gray-100 px-3 py-2 text-xs font-bold text-gray-600 border-b border-gray-200">2. Variables (变量)</div>
                <div className="flex-1 p-3 bg-gray-50 overflow-y-auto font-mono text-sm whitespace-pre-wrap text-blue-700">
                  {variables}
                </div>
              </div>
              
              <div className="flex flex-col border border-indigo-200 rounded-lg overflow-hidden shadow-sm">
                <div className="bg-indigo-50 px-3 py-2 text-xs font-bold text-indigo-700 border-b border-indigo-200 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" />
                  3. Final Text (最终注入)
                </div>
                <div className="flex-1 p-3 bg-white overflow-y-auto font-mono text-sm whitespace-pre-wrap text-gray-800">
                  {finalPrompt}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-screen w-full bg-gray-50 text-slate-800 font-sans">
      {/* Left Sidebar */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col z-10">
        <div className="p-4 border-b border-gray-200 font-bold text-lg flex items-center gap-2">
          <Settings className="w-5 h-5 text-blue-600" />
          Skill Studio
        </div>
        <div className="p-4 flex-1 overflow-y-auto">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Skills</h3>
          <ul className="space-y-2">
            {skills.map(skill => (
              <li 
                key={skill.id}
                onClick={() => loadSkill(skill.id)}
                className={`p-2 rounded-md cursor-pointer flex items-center gap-2 font-medium transition-colors ${
                  activeSkillId === skill.id 
                    ? 'bg-blue-50 text-blue-700 border border-blue-100' 
                    : 'hover:bg-gray-100 text-gray-600 border border-transparent'
                }`}
              >
                <FileText className="w-4 h-4" />
                {skill.name}
              </li>
            ))}
          </ul>
        </div>
        
        {/* Settings Button */}
        <div className="p-4 border-t border-gray-200">
          <button 
            onClick={() => setActiveTab('settings')}
            className={`w-full p-2 rounded-md flex items-center justify-center gap-2 font-medium transition-colors ${
              activeTab === 'settings' ? 'bg-gray-200 text-gray-800' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            <Settings className="w-4 h-4" />
            Settings
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Top Toolbar */}
        <div className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0 z-20">
          <div className="flex items-center gap-6 text-sm relative">
            {/* Artifacts Manager Trigger */}
            <button 
              onClick={() => setIsArtifactsMenuOpen(!isArtifactsMenuOpen)}
              className="flex items-center gap-2 px-3 py-1.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-md hover:bg-indigo-100 font-medium transition-colors"
            >
              <HardDrive className="w-4 h-4" />
              Artifacts Manager
            </button>
            
            {/* Artifacts Dropdown Menu */}
            {isArtifactsMenuOpen && (
              <div className="absolute top-10 left-0 w-96 bg-white border border-gray-200 shadow-xl rounded-lg p-4 z-50">
                <h4 className="font-bold text-gray-800 mb-3 border-b pb-2">Artifacts Configuration</h4>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase mb-1">Input Source</label>
                    <div className="flex items-center gap-2">
                      <FolderOpen className="w-4 h-4 text-gray-400 shrink-0" />
                      <input 
                        type="text" 
                        value={inputPath}
                        onChange={e => setInputPath(e.target.value)}
                        className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        placeholder="workspaces/default/inputs/..."
                      />
                    </div>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase mb-1">Output Destination</label>
                    <div className="flex items-center gap-2">
                      <Save className="w-4 h-4 text-gray-400 shrink-0" />
                      <input 
                        type="text" 
                        value={outputPath}
                        onChange={e => setOutputPath(e.target.value)}
                        className="flex-1 border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        placeholder="workspaces/default/outputs/..."
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Quick Display */}
            <div className="text-xs text-gray-500 flex flex-col">
              <span><span className="font-semibold">In:</span> {inputPath.split('/').pop()}</span>
              <span><span className="font-semibold">Out:</span> {outputPath.split('/').pop()}</span>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <button 
              onClick={handleCompile}
              className="px-4 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 font-medium flex items-center gap-2 transition-colors"
            >
              {compileStatus === 'compiling' ? '编译中...' : 'Compile'}
              {compileStatus === 'success' && <CheckCircle className="w-4 h-4 text-green-500" />}
              {compileStatus === 'error' && <AlertCircle className="w-4 h-4 text-red-500" />}
            </button>
            <button 
              onClick={handleRun}
              disabled={compileStatus !== 'success' || runStatus === 'running'}
              className={`px-4 py-1.5 rounded-md font-medium flex items-center gap-2 transition-colors ${
                compileStatus === 'success' && runStatus !== 'running'
                  ? 'bg-blue-600 hover:bg-blue-700 text-white' 
                  : 'bg-blue-300 text-white cursor-not-allowed'
              }`}
            >
              <Play className="w-4 h-4" />
              {runStatus === 'running' ? 'Running...' : 'Run'}
            </button>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 flex overflow-hidden">
          {/* Graph View */}
          <div className="flex-1 border-r border-gray-200 relative bg-slate-50">
            <div className="absolute top-4 left-4 z-10 bg-white px-3 py-1.5 rounded-md shadow-sm border border-gray-200 text-sm font-semibold text-gray-700">
              Graph 拓扑视图
            </div>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              fitView
              minZoom={0.5}
            >
              <Controls />
              <MiniMap />
              <Background gap={12} size={1} />
            </ReactFlow>
          </div>

          {/* Right Panel (Code / Trace / Settings) */}
          <div className="w-[500px] flex flex-col bg-white z-10">
            <div className="flex border-b border-gray-200 shrink-0">
              <button 
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 ${activeTab === 'code' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                onClick={() => setActiveTab('code')}
              >
                <FileText className="w-4 h-4" />
                SKILL.md
              </button>
              <button 
                className={`flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 ${activeTab === 'trace' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-500 hover:text-gray-700'}`}
                onClick={() => setActiveTab('trace')}
              >
                <Terminal className="w-4 h-4" />
                Trace / Output
              </button>
            </div>

            <div className="flex-1 overflow-hidden">
              {activeTab === 'settings' ? (
                <div className="p-6 h-full overflow-y-auto bg-gray-50">
                  <h2 className="text-xl font-bold text-gray-800 mb-6">Settings</h2>
                  
                  <div className="bg-white p-5 rounded-lg shadow-sm border border-gray-200 mb-6">
                    <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wider mb-4 border-b pb-2">LLM API Keys</h3>
                    
                    <div className="space-y-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">OpenAI API Key</label>
                        <input 
                          type="password" 
                          value={apiKeys.openai}
                          onChange={e => setApiKeys({...apiKeys, openai: e.target.value})}
                          className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="sk-..."
                        />
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Anthropic API Key</label>
                        <input 
                          type="password" 
                          value={apiKeys.anthropic}
                          onChange={e => setApiKeys({...apiKeys, anthropic: e.target.value})}
                          className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="sk-ant-..."
                        />
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Google Gemini API Key</label>
                        <input 
                          type="password" 
                          value={apiKeys.gemini}
                          onChange={e => setApiKeys({...apiKeys, gemini: e.target.value})}
                          className="w-full border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          placeholder="AIza..."
                        />
                      </div>
                    </div>
                    
                    <button className="mt-4 w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 rounded-md transition-colors">
                      Save Keys
                    </button>
                  </div>
                </div>
              ) : activeTab === 'code' ? (
                <div className="h-full flex flex-col">
                  {compileStatus === 'error' && (
                    <div className="bg-red-50 border-b border-red-200 p-3 text-sm text-red-700 flex flex-col gap-2 shrink-0">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                        <span>{compileError}</span>
                      </div>
                      <button 
                        onClick={copyErrorToClipboard}
                        className="self-end flex items-center gap-1 text-xs bg-white border border-red-200 px-2 py-1 rounded hover:bg-red-50 text-red-600"
                      >
                        <Copy className="w-3 h-3" />
                        复制给 AI 助手修复
                      </button>
                    </div>
                  )}
                  <div className="flex-1">
                    <Editor
                      height="100%"
                      defaultLanguage="markdown"
                      value={skillCode}
                      onChange={(val) => setSkillCode(val || '')}
                      options={{
                        minimap: { enabled: false },
                        fontSize: 13,
                        wordWrap: 'on',
                        scrollBeyondLastLine: false,
                      }}
                    />
                  </div>
                </div>
              ) : (
                <div className="h-full bg-slate-50 p-4 overflow-y-auto">
                  {traceLogs.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-slate-400 font-medium text-sm">
                      等待运行...
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <h3 className="font-bold text-gray-700 border-b border-gray-200 pb-2 mb-4">Trace Timeline</h3>
                      
                      <div className="relative border-l-2 border-gray-200 ml-3 space-y-6">
                        {traceLogs.map((log, i) => (
                          <div key={i} className="relative pl-6">
                            {/* Timeline Dot */}
                            <div className={`absolute -left-[9px] top-1 w-4 h-4 rounded-full border-2 border-white ${
                              log.type === 'system' ? 'bg-green-500' :
                              log.type === 'phase_start' ? 'bg-blue-500' :
                              log.type === 'llm_call' ? 'bg-purple-500' :
                              log.type === 'phase_end' ? 'bg-gray-400' : 'bg-green-600'
                            }`} />
                            
                            {/* Content Card */}
                            <div className={`p-3 rounded-lg border shadow-sm ${
                              log.type === 'system' ? 'bg-green-50 border-green-200' :
                              log.type === 'phase_start' ? 'bg-blue-50 border-blue-200' :
                              log.type === 'llm_call' ? 'bg-white border-purple-200 hover:border-purple-400 cursor-pointer transition-colors' :
                              log.type === 'phase_end' ? 'bg-gray-50 border-gray-200' : 'bg-green-100 border-green-300'
                            }`}
                            onClick={() => log.type === 'llm_call' && setSelectedPromptIndex(i)}
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className={`text-sm font-bold ${
                                  log.type === 'system' ? 'text-green-800' :
                                  log.type === 'phase_start' ? 'text-blue-800' :
                                  log.type === 'llm_call' ? 'text-purple-800 flex items-center gap-1' :
                                  log.type === 'phase_end' ? 'text-gray-700' : 'text-green-900'
                                }`}>
                                  {log.type === 'llm_call' && <MessageSquare className="w-3.5 h-3.5" />}
                                  {log.type === 'llm_call' ? 'LLM Call' : log.phase || 'System'}
                                </span>
                                
                                {log.tokens && (
                                  <span className="text-xs font-medium text-purple-600 bg-purple-100 px-2 py-0.5 rounded-full flex items-center gap-1">
                                    <Hash className="w-3 h-3" />
                                    {log.tokens}
                                  </span>
                                )}
                              </div>
                              
                              <p className="text-sm text-gray-600">
                                {log.message}
                              </p>
                              
                              {log.type === 'llm_call' && (
                                <div className="mt-2 text-xs text-purple-500 font-medium flex items-center gap-1">
                                  Click to inspect prompt <ChevronRight className="w-3 h-3" />
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Render Modals */}
      {renderPromptInspector()}
    </div>
  );
}
