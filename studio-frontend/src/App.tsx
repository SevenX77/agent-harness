import React, { useState, useCallback } from 'react';
import { ReactFlow, MiniMap, Controls, Background, useNodesState, useEdgesState, addEdge, MarkerType } from 'reactflow';
import 'reactflow/dist/style.css';
import Editor from '@monaco-editor/react';
import { Play, CheckCircle, AlertCircle, FileText, Settings, Terminal, Copy } from 'lucide-react';

const initialNodes = [
  {
    id: 'input',
    type: 'input',
    data: { label: 'Input: Product Specs (JSON)' },
    position: { x: 250, y: 50 },
    style: { background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '8px', padding: '10px' }
  },
  {
    id: 'extract_highlights',
    data: { label: 'Phase 1: extract_highlights\n(Agent-Loop)' },
    position: { x: 250, y: 150 },
    style: { background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '10px' }
  },
  {
    id: 'write_scenarios',
    data: { label: 'Phase 2: write_scenarios\n(Agent-Loop)' },
    position: { x: 250, y: 250 },
    style: { background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '10px' }
  },
  {
    id: 'synthesize_report',
    data: { label: 'Phase 3: synthesize_report\n(Agent-Loop)' },
    position: { x: 250, y: 350 },
    style: { background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '10px' }
  },
  {
    id: 'output',
    type: 'output',
    data: { label: 'Output: Product Manual (MD)' },
    position: { x: 250, y: 450 },
    style: { background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', padding: '10px' }
  },
];

const initialEdges = [
  { id: 'e1', source: 'input', target: 'extract_highlights', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: 'e2', source: 'extract_highlights', target: 'write_scenarios', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: 'e3', source: 'write_scenarios', target: 'synthesize_report', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
  { id: 'e4', source: 'synthesize_report', target: 'output', animated: true, markerEnd: { type: MarkerType.ArrowClosed } },
];

const mockSkillMd = `---
name: product-manual
description: 生成面向消费者的产品说明书
type: graph
io:
  inputs:
    - name: product_specs
      type: json
      source: runtime
  outputs:
    - name: final_manual
      type: markdown
---

<phase_config>
name: extract_highlights
tier: balanced
tools:
  - script.extract.get_highlights
</phase_config>

<system_prompt>
你是一个产品专家。请从参数表中提取3-5个核心亮点。
</system_prompt>

<phase_config>
name: write_scenarios
tier: balanced
depends_on:
  - extract_highlights
tools:
  - script.scenarios.generate
</phase_config>

<system_prompt>
根据产品亮点，构思3个具体的使用场景。
注意：至少举3个具体使用场景！
</system_prompt>

<phase_config>
name: synthesize_report
tier: premium
depends_on:
  - write_scenarios
tools:
  - script.report.synthesize
</phase_config>

<system_prompt>
综合亮点和场景，写出一份吸引人的产品说明书。
</system_prompt>
`;

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [skillCode, setSkillCode] = useState(mockSkillMd);
  const [compileStatus, setCompileStatus] = useState<'idle' | 'compiling' | 'success' | 'error'>('idle');
  const [runStatus, setRunStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle');
  const [activeTab, setActiveTab] = useState<'code' | 'trace'>('code');
  const [inputPath, setInputPath] = useState('workspaces/default/inputs/iphone15_specs.json');
  const [outputPath, setOutputPath] = useState('workspaces/default/outputs/iphone15_manual.md');
  const [traceLogs, setTraceLogs] = useState<string[]>([]);

  const onConnect = useCallback((params: any) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  const handleCompile = () => {
    setCompileStatus('compiling');
    setTimeout(() => {
      // Mock compilation logic
      if (skillCode.includes('至少举3个具体使用场景')) {
        setCompileStatus('success');
      } else {
        setCompileStatus('error');
      }
    }, 800);
  };

  const handleRun = () => {
    if (compileStatus !== 'success') {
      alert("请先编译通过后再运行！");
      return;
    }
    setRunStatus('running');
    setActiveTab('trace');
    setTraceLogs(['[System] 验证输入 schema: 成功 (product_specs.json)']);
    
    setTimeout(() => {
      setTraceLogs(prev => [...prev, '[Phase 1] extract_highlights 开始执行...']);
      setTimeout(() => {
        setTraceLogs(prev => [...prev, '[Phase 1] 提取亮点完成 (耗时: 3.2s)']);
        setTraceLogs(prev => [...prev, '[Phase 2] write_scenarios 开始执行...']);
        setTimeout(() => {
          setTraceLogs(prev => [...prev, '[Phase 2] 生成场景完成 (耗时: 4.1s)']);
          setTraceLogs(prev => [...prev, '[Phase 3] synthesize_report 开始执行...']);
          setTimeout(() => {
            setTraceLogs(prev => [...prev, '[Phase 3] 报告合成完成 (耗时: 2.8s)']);
            setTraceLogs(prev => [...prev, '[System] 验证输出 schema: 成功 (markdown)']);
            setTraceLogs(prev => [...prev, '[System] 产出已保存至: ' + outputPath]);
            setRunStatus('success');
          }, 1500);
        }, 1500);
      }, 1500);
    }, 500);
  };

  const copyErrorToClipboard = () => {
    const errorMsg = "编译错误: Phase 'write_scenarios' 缺少具体的场景数量约束。请在 system_prompt 中明确指定。";
    navigator.clipboard.writeText(errorMsg);
    alert("错误信息已复制，可粘贴给您的编程助手 (如 Cursor/Claude) 进行修复。");
  };

  return (
    <div className="flex h-screen w-full bg-gray-50 text-slate-800 font-sans">
      {/* Left Sidebar */}
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-4 border-b border-gray-200 font-bold text-lg flex items-center gap-2">
          <Settings className="w-5 h-5 text-blue-600" />
          Skill Studio
        </div>
        <div className="p-4">
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Skills</h3>
          <ul className="space-y-2">
            <li className="p-2 bg-blue-50 text-blue-700 rounded-md border border-blue-100 cursor-pointer flex items-center gap-2 font-medium">
              <FileText className="w-4 h-4" />
              product-manual
            </li>
            <li className="p-2 hover:bg-gray-100 text-gray-600 rounded-md cursor-pointer flex items-center gap-2">
              <FileText className="w-4 h-4" />
              hello-world
            </li>
          </ul>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Top Toolbar */}
        <div className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500 font-medium">输入 (Artifacts):</span>
              <input 
                type="text" 
                value={inputPath}
                onChange={e => setInputPath(e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500 font-medium">输出 (Artifacts):</span>
              <input 
                type="text" 
                value={outputPath}
                onChange={e => setOutputPath(e.target.value)}
                className="border border-gray-300 rounded px-2 py-1 w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
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
              className={
                compileStatus === 'success' && runStatus !== 'running'
                  ? 'px-4 py-1.5 rounded-md font-medium flex items-center gap-2 transition-colors bg-blue-600 hover:bg-blue-700 text-white' 
                  : 'px-4 py-1.5 rounded-md font-medium flex items-center gap-2 transition-colors bg-blue-300 text-white cursor-not-allowed'
              }
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
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              fitView
            >
              <Controls />
              <MiniMap />
              <Background gap={12} size={1} />
            </ReactFlow>
          </div>

          {/* Right Panel (Code / Trace) */}
          <div className="w-[450px] flex flex-col bg-white">
            <div className="flex border-b border-gray-200 shrink-0">
              <button 
                className={activeTab === 'code' ? 'flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 border-blue-600 text-blue-600' : 'flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 text-gray-500 hover:text-gray-700'}
                onClick={() => setActiveTab('code')}
              >
                <FileText className="w-4 h-4" />
                SKILL.md
              </button>
              <button 
                className={activeTab === 'trace' ? 'flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 border-b-2 border-blue-600 text-blue-600' : 'flex-1 py-3 text-sm font-medium flex items-center justify-center gap-2 text-gray-500 hover:text-gray-700'}
                onClick={() => setActiveTab('trace')}
              >
                <Terminal className="w-4 h-4" />
                Trace / Output
              </button>
            </div>

            <div className="flex-1 overflow-hidden">
              {activeTab === 'code' ? (
                <div className="h-full flex flex-col">
                  {compileStatus === 'error' && (
                    <div className="bg-red-50 border-b border-red-200 p-3 text-sm text-red-700 flex flex-col gap-2 shrink-0">
                      <div className="flex items-start gap-2">
                        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                        <span>编译错误: Phase 'write_scenarios' 缺少具体的场景数量约束。请在 system_prompt 中明确指定。</span>
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
                <div className="h-full bg-slate-900 text-green-400 p-4 font-mono text-sm overflow-y-auto">
                  {traceLogs.length === 0 ? (
                    <span className="text-slate-500">等待运行...</span>
                  ) : (
                    <div className="space-y-2">
                      {traceLogs.map((log, i) => (
                        <div key={i} className={log.includes('成功') ? 'text-green-400' : 'text-blue-300'}>
                          {log}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
