import React, { useState } from 'react';
import { 
  ChevronRight, 
  FileCode2, 
  FolderOpen, 
  Sparkles, 
  Play, 
  CheckCircle2, 
  Activity, 
  MoreHorizontal,
  ArrowRight,
  TerminalSquare
} from 'lucide-react';

/**
 * Skill Studio - High-Density Vercel/Linear Style Workspace
 * 
 * Aesthetic Rules Applied:
 * - Colors: Zinc/Slate monochrome. No green. Indigo-500 for active/primary actions.
 * - Density: text-xs (12px) base, tight padding (p-1, p-2).
 * - Fonts: Sans for UI, Mono (text-[10px]) for data/code.
 * - Copilot: Inline terminal/slack style, no chat bubbles.
 */

export default function StudioWorkspace() {
  const [chatInput, setChatInput] = useState('');

  return (
    <div className="flex flex-col h-screen w-full bg-[#09090b] text-zinc-300 font-sans overflow-hidden selection:bg-indigo-500/30">
      
      {/* ================= HEADER ================= */}
      <header className="h-10 min-h-[40px] flex items-center justify-between px-3 border-b border-zinc-800 bg-[#09090b] z-20">
        {/* Breadcrumbs */}
        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
          <span className="hover:text-zinc-300 cursor-pointer">Workspace</span>
          <ChevronRight className="w-3 h-3 text-zinc-700" />
          <span className="hover:text-zinc-300 cursor-pointer">story-deconstruction</span>
          <ChevronRight className="w-3 h-3 text-zinc-700" />
          <span className="text-zinc-200 font-mono text-[11px]">SKILL.md</span>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded border border-zinc-800 bg-zinc-900/50">
            <CheckCircle2 className="w-3 h-3 text-zinc-500" />
            <span className="text-[10px] font-mono text-zinc-400">Compiled</span>
          </div>
          
          <button className="h-6 px-2.5 text-xs font-medium border border-zinc-700 rounded-md hover:bg-zinc-800 transition-colors text-zinc-300">
            Predict
          </button>
          <button className="h-6 px-2.5 flex items-center gap-1.5 text-xs font-medium border border-indigo-600 bg-indigo-600 text-white rounded-md hover:bg-indigo-500 transition-colors shadow-[0_0_10px_rgba(79,70,229,0.2)]">
            <Play className="w-3 h-3 fill-current" />
            Run
          </button>
        </div>
      </header>

      {/* ================= MAIN LAYOUT ================= */}
      <div className="flex flex-1 overflow-hidden">
        
        {/* LEFT: Asset Tree */}
        <aside className="w-48 flex-shrink-0 border-r border-zinc-800 bg-[#09090b] flex flex-col">
          <div className="px-3 py-2 text-[10px] font-mono text-zinc-500 font-medium tracking-widest border-b border-zinc-800/50">
            ASSETS
          </div>
          <div className="flex-1 overflow-y-auto py-1">
            <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-zinc-400 hover:bg-zinc-900 cursor-pointer">
              <FolderOpen className="w-3.5 h-3.5" />
              <span>scripts/</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-indigo-300 bg-indigo-500/10 border-l-2 border-indigo-500 cursor-pointer font-mono">
              <FileCode2 className="w-3.5 h-3.5" />
              <span>SKILL.md</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-900 cursor-pointer pl-6">
              <FileCode2 className="w-3.5 h-3.5" />
              <span>rules.md</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 text-xs text-zinc-500 hover:bg-zinc-900 cursor-pointer pl-6 font-mono text-[10px]">
              <FileCode2 className="w-3.5 h-3.5" />
              <span>baseline.json</span>
            </div>
          </div>
        </aside>

        {/* CENTER: Canvas */}
        <main className="flex-1 relative bg-[#09090b] overflow-hidden">
          {/* Subtle Dot Grid */}
          <div className="absolute inset-0 opacity-[0.15]" 
               style={{ backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)', backgroundSize: '16px 16px' }} />

          {/* Node 1: Input */}
          <div className="absolute top-20 left-10 w-48 bg-[#09090b] border border-zinc-800 rounded-lg shadow-xl z-10">
            <div className="px-3 py-1.5 border-b border-zinc-800 flex items-center justify-between bg-zinc-900/50 rounded-t-lg">
              <span className="text-[11px] font-medium text-zinc-400">io.inputs</span>
              <MoreHorizontal className="w-3 h-3 text-zinc-600" />
            </div>
            <div className="p-2 space-y-1.5">
              <div className="flex justify-between items-center text-[10px] font-mono">
                <span className="text-zinc-500">scene_id</span>
                <span className="text-indigo-400/70">str</span>
              </div>
              <div className="flex justify-between items-center text-[10px] font-mono">
                <span className="text-zinc-500">raw_text</span>
                <span className="text-indigo-400/70">str</span>
              </div>
            </div>
          </div>

          {/* SVG Line with Edge Dot */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
            <path d="M 232 110 C 280 110, 300 110, 350 110" fill="none" stroke="#27272a" strokeWidth="1.5" />
          </svg>
          {/* Edge Dot Inspector */}
          <div className="absolute top-[104px] left-[285px] w-3.5 h-3.5 bg-[#09090b] border border-zinc-600 rounded-full flex items-center justify-center cursor-pointer hover:border-indigo-400 z-10 transition-colors group">
            <div className="w-1.5 h-1.5 bg-zinc-500 rounded-full group-hover:bg-indigo-400" />
          </div>

          {/* Node 2: Active Phase */}
          <div className="absolute top-[75px] left-[350px] w-64 bg-[#09090b] border border-indigo-500/50 rounded-lg shadow-[0_0_15px_rgba(79,70,229,0.1)] z-20 overflow-hidden ring-1 ring-indigo-500">
            {/* Header */}
            <div className="px-3 py-2 bg-indigo-500/10 border-b border-indigo-500/20 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse shadow-[0_0_5px_#818cf8]" />
                <span className="text-xs font-semibold text-indigo-100">extract_events</span>
              </div>
              <span className="text-[9px] px-1.5 py-0.5 bg-zinc-900 border border-zinc-700 text-zinc-400 rounded uppercase tracking-wider">Phase</span>
            </div>
            
            {/* Metadata Pills */}
            <div className="px-3 py-1.5 border-b border-zinc-800/80 bg-zinc-900/30 flex gap-1.5">
              <span className="px-1.5 py-0.5 text-[9px] font-mono bg-[#09090b] border border-zinc-800 text-zinc-300 rounded">type: loop</span>
              <span class="px-1.5 py-0.5 text-[9px] font-mono bg-[#09090b] border border-zinc-800 text-zinc-300 rounded">tier: balanced</span>
            </div>

            {/* Content Preview */}
            <div className="p-3 text-xs leading-tight">
              <div className="text-[9px] uppercase tracking-wider font-mono text-zinc-500 mb-1">System Prompt</div>
              <div className="font-mono text-[10px] text-zinc-300 opacity-80 truncate">You are an expert story analyst...</div>
            </div>
          </div>
        </main>

        {/* RIGHT: Copilot (Dense, Inline, Terminal-like) */}
        <aside className="w-[320px] flex-shrink-0 border-l border-zinc-800 bg-[#09090b] flex flex-col shadow-[-10px_0_30px_rgba(0,0,0,0.2)] z-30">
          {/* Header */}
          <div className="h-10 flex items-center justify-between px-3 border-b border-zinc-800">
            <div className="flex items-center gap-1.5 text-zinc-300 text-xs font-medium">
              <TerminalSquare className="w-3.5 h-3.5 text-indigo-400" />
              Copilot
            </div>
          </div>

          {/* Chat / Log Stream */}
          <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-4 text-xs leading-relaxed">
            
            {/* User Message (Inline) */}
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-2 text-zinc-500">
                <span className="font-medium text-zinc-300">You</span>
                <span className="text-[9px] font-mono">10:42 AM</span>
              </div>
              <div className="text-zinc-300 ml-0">
                Add a validator to check if the JSON array has at least 3 items.
              </div>
            </div>

            {/* AI Message (Inline) */}
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 text-indigo-400">
                <Sparkles className="w-3 h-3" />
                <span className="font-medium">Studio AI</span>
                <span className="text-[9px] text-zinc-600 font-mono">10:42 AM</span>
              </div>
              <div className="text-zinc-300">
                I've generated a <code className="px-1 py-0.5 text-[10px] font-mono bg-zinc-900 border border-zinc-800 rounded text-zinc-200">length_validator</code> function in scripts and updated the phase config.
              </div>
              
              {/* Code Snippet */}
              <div className="mt-1 bg-[#09090b] border border-zinc-800 rounded overflow-hidden">
                <div className="px-2 py-1 border-b border-zinc-800 bg-zinc-900/50 text-[9px] font-mono text-zinc-500 flex justify-between">
                  <span>validator.py</span>
                  <span className="cursor-pointer hover:text-zinc-300">Copy</span>
                </div>
                <div className="p-2 text-[10px] font-mono leading-relaxed overflow-x-auto text-zinc-400">
                  <span className="text-indigo-400">def</span> <span className="text-blue-300">validate_events</span>(ctx):<br/>
                  &nbsp;&nbsp;events = ctx.get(<span className="text-emerald-400/80">'events'</span>, [])<br/>
                  &nbsp;&nbsp;<span className="text-indigo-400">if</span> len(events) &lt; <span className="text-orange-300/80">3</span>:<br/>
                  &nbsp;&nbsp;&nbsp;&nbsp;<span className="text-indigo-400">return</span> <span className="text-orange-300/80">False</span>, [<span className="text-emerald-400/80">"Too few events"</span>]<br/>
                  &nbsp;&nbsp;<span className="text-indigo-400">return</span> <span className="text-orange-300/80">True</span>, []
                </div>
              </div>

              {/* Action Buttons (Inline) */}
              <div className="flex gap-2 mt-1">
                <button className="text-[10px] font-medium border border-zinc-700 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 px-2 py-1 rounded transition-colors flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Apply
                </button>
                <button className="text-[10px] text-zinc-500 hover:text-zinc-300 px-2 py-1">Reject</button>
              </div>
            </div>

          </div>

          {/* Input Box */}
          <div className="p-2 border-t border-zinc-800 bg-[#09090b]">
            <div className="relative flex items-center bg-zinc-900 border border-zinc-800 focus-within:border-indigo-500 rounded px-2 py-1.5 transition-colors">
              <input 
                type="text" 
                placeholder="Ask Copilot or use /commands..." 
                className="w-full bg-transparent text-xs text-zinc-200 placeholder-zinc-600 focus:outline-none"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
              />
              <button className="w-5 h-5 flex items-center justify-center text-zinc-500 hover:text-indigo-400 rounded">
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </aside>

      </div>
    </div>
  );
}