import { useState, useRef } from 'react'
import { useAppStore } from '../store/appStore'

interface SidebarProps {
  isCollapsed: boolean
  onToggle: () => void
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const {
    selectedRole,
    availableRoles,
    setRole,
    indexedFiles,
    isIndexing,
    indexingStatus,
    indexStats,
    memoryStats,
    uploadAndIndexFiles,
    buildGraph,
    clearIndex,
    exportIndex,
    generateSrs,
    downloadSrs,
    generatedSrs,
    isGeneratingSrs,
    clearChat,
    clearMemory,
    researchTask,
  } = useAppStore()

  const [focusInput, setFocusInput] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      await uploadAndIndexFiles(Array.from(files))
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleGenerateSrs = async () => {
    await generateSrs(focusInput || undefined)
  }

  // Collapsed state
  if (isCollapsed) {
    return (
      <aside className="w-12 h-full bg-[#0a0a0a] border-r border-white/10 flex flex-col items-center py-4 sidebar-transition relative z-20">
        <button
          onClick={onToggle}
          className="text-gray-400 hover:text-white text-lg mb-6 sidebar-toggle"
          title="Expand"
        >
          »
        </button>
        
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.txt,.md,.pptx,.xlsx"
          onChange={handleFileUpload}
          className="hidden"
        />
      </aside>
    )
  }

  return (
    <aside className="w-64 h-full bg-[#0a0a0a] border-r border-white/10 flex flex-col overflow-hidden sidebar-transition relative z-20">
      {/* Header */}
      <div className="p-4 border-b border-white/5 flex items-center justify-between">
        <span className="text-white/80 text-sm font-medium">RAAA</span>
        <button
          onClick={onToggle}
          className="text-gray-500 hover:text-white text-sm sidebar-toggle"
          title="Collapse"
        >
          «
        </button>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Role Selection */}
        <div>
          <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">
            Role
          </label>
          <select
            value={selectedRole}
            onChange={(e) => setRole(e.target.value)}
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-white/20 glow-input"
          >
            {availableRoles.map(role => (
              <option key={role} value={role} className="bg-gray-900">{role}</option>
            ))}
          </select>
        </div>

        {/* Research Status */}
        {researchTask && researchTask.status === 'running' && (
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
            <div className="text-blue-400 text-sm font-medium">
              Research Running...
            </div>
            <p className="text-xs text-blue-400/70 mt-1 truncate">
              {researchTask.query.slice(0, 40)}...
            </p>
          </div>
        )}

        {/* Document Section */}
        <div className="space-y-3">
          <label className="block text-xs text-gray-500 uppercase tracking-wider">
            Documents
          </label>
          
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.png,.jpg,.jpeg,.json"
            onChange={handleFileUpload}
            className="hidden"
          />
          
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isIndexing}
            className="w-full px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-white/80 hover:text-white transition-colors disabled:opacity-50"
          >
            {isIndexing ? 'Indexing...' : 'Upload & Index'}
          </button>

          {indexingStatus && (
            <div className={`text-xs p-2 rounded ${
              indexingStatus.includes('✅') ? 'bg-green-500/10 text-green-400' :
              indexingStatus.includes('❌') ? 'bg-red-500/10 text-red-400' :
              'bg-blue-500/10 text-blue-400'
            }`}>
              {indexingStatus}
            </div>
          )}

          {/* Index Stats */}
          {indexStats && indexStats.indexed_files > 0 && (
            <div className="text-xs text-gray-500 space-y-1 bg-white/5 rounded-lg p-3">
              <p>Files: {indexStats.indexed_files} | Chunks: {indexStats.total_chunks}</p>
              {indexStats.neo4j_connected ? (
                <p>Graph: Neo4j ({indexStats.neo4j_entity_count} entities)</p>
              ) : (
                <p>Graph: {indexStats.has_graph ? 'JSON' : 'Not built'}</p>
              )}
            </div>
          )}

          {/* Index Actions */}
          {indexStats && indexStats.indexed_files > 0 && (
            <div className="grid grid-cols-2 gap-2">
              {(!indexStats.has_graph || indexStats.needs_graph_update) && (
                <button
                  onClick={() => buildGraph(false)}
                  className="px-2 py-1.5 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded text-gray-400 hover:text-white transition-colors"
                >
                  {indexStats.has_graph ? 'Update Graph' : 'Build Graph'}
                </button>
              )}
              {indexStats.has_graph && (
                <button
                  onClick={() => buildGraph(true)}
                  className="px-2 py-1.5 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded text-gray-400 hover:text-white transition-colors"
                >
                  Rebuild
                </button>
              )}
              <button
                onClick={exportIndex}
                className="px-2 py-1.5 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded text-gray-400 hover:text-white transition-colors"
              >
                Export
              </button>
              <button
                onClick={clearIndex}
                className="px-2 py-1.5 text-xs bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded text-red-400 hover:text-red-300 transition-colors"
              >
                Clear
              </button>
            </div>
          )}

          {/* Indexed Files */}
          {indexedFiles.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-gray-500 hover:text-gray-300">
                {indexedFiles.length} file(s) indexed
              </summary>
              <ul className="mt-2 space-y-1 text-gray-600">
                {indexedFiles.map(file => (
                  <li key={file} className="truncate">• {file}</li>
                ))}
              </ul>
            </details>
          )}
        </div>

        {/* SRS Section */}
        <div className="space-y-3">
          <label className="block text-xs text-gray-500 uppercase tracking-wider">
            SRS Generation
          </label>
          
          <textarea
            value={focusInput}
            onChange={(e) => setFocusInput(e.target.value)}
            placeholder="Focus area (optional)"
            className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-gray-600 resize-none h-16 focus:outline-none focus:border-white/20 glow-input"
          />
          
          <button
            onClick={handleGenerateSrs}
            disabled={isGeneratingSrs}
            className="w-full px-3 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-sm text-white/80 hover:text-white transition-colors disabled:opacity-50"
          >
            {isGeneratingSrs ? 'Generating...' : 'Generate SRS'}
          </button>
          
          {generatedSrs && (
            <button
              onClick={downloadSrs}
              className="w-full px-3 py-2 bg-green-500/10 hover:bg-green-500/20 border border-green-500/20 rounded-lg text-sm text-green-400 hover:text-green-300 transition-colors"
            >
              Download SRS
            </button>
          )}
        </div>

        {/* Memory Section */}
        <div className="space-y-3">
          <label className="block text-xs text-gray-500 uppercase tracking-wider">
            Memory & Chat
          </label>
          
          {memoryStats && (
            <div className="text-xs text-gray-500 bg-white/5 rounded-lg p-3 space-y-1">
              <p>Entities: {memoryStats.entity_count}</p>
              <p>Mem0: {memoryStats.mem0_enabled ? 'Enabled' : 'Disabled'}</p>
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={clearChat}
              className="px-2 py-2 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded text-gray-400 hover:text-white transition-colors"
            >
              Clear Chat
            </button>
            <button
              onClick={() => clearMemory(false)}
              className="px-2 py-2 text-xs bg-white/5 hover:bg-white/10 border border-white/10 rounded text-gray-400 hover:text-white transition-colors"
            >
              Clear Memory
            </button>
          </div>
          
          {memoryStats?.mem0_enabled && (
            <button
              onClick={() => clearMemory(true)}
              className="w-full px-2 py-2 text-xs bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 rounded text-red-400 hover:text-red-300 transition-colors"
            >
              Clear Mem0
            </button>
          )}
        </div>

        {/* Tips */}
        <div className="space-y-2">
          <label className="block text-xs text-gray-500 uppercase tracking-wider">
            Tips
          </label>
          <div className="text-xs text-gray-600 space-y-1">
            <p>• Ask about uploaded documents</p>
            <p>• Request requirements generation</p>
            <p>• Use "research" for deep research</p>
            <p>• Ask for diagrams</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
