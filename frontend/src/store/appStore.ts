import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import * as api from '../api'

export interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp?: string
  mermaidChart?: string
  pdfPath?: string
  docxPath?: string
}

export interface IndexStats {
  indexed_files: number
  total_chunks: number
  has_graph: boolean
  graph_storage: string
  neo4j_connected: boolean
  neo4j_entity_count: number
  neo4j_relationship_count: number
  needs_graph_update: boolean
}

export interface MemoryStats {
  entity_count: number
  mem0_enabled: boolean
  mem0_stats?: Record<string, unknown>
}

export interface ResearchTask {
  taskId: string
  status: 'running' | 'completed' | 'error' | 'not_found'
  query: string
  startedAt?: string
}

interface AppState {
  // Session
  sessionId: string | null
  
  // Chat
  messages: Message[]
  isLoading: boolean
  streamingContent: string
  
  // Role
  selectedRole: string
  availableRoles: string[]
  
  // Files
  indexedFiles: string[]
  isIndexing: boolean
  indexingStatus: string | null
  
  // Stats
  indexStats: IndexStats | null
  memoryStats: MemoryStats | null
  
  // SRS
  generatedSrs: string | null
  isGeneratingSrs: boolean
  
  // Deep Research
  researchTask: ResearchTask | null
  
  // Actions
  initSession: () => Promise<void>
  fetchRoles: () => Promise<void>
  setRole: (role: string) => void
  sendMessage: (message: string) => Promise<void>
  sendMessageStream: (message: string) => Promise<void>
  clearChat: () => void
  uploadAndIndexFiles: (files: File[]) => Promise<void>
  buildGraph: (forceRebuild?: boolean) => Promise<void>
  clearIndex: () => Promise<void>
  exportIndex: () => Promise<void>
  generateSrs: (focus?: string) => Promise<void>
  downloadSrs: () => void
  startResearch: (query: string) => Promise<void>
  checkResearchStatus: () => Promise<void>
  clearResearch: () => Promise<void>
  fetchStats: () => Promise<void>
  clearMemory: (clearMem0?: boolean) => Promise<void>
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Initial state
      sessionId: null,
      messages: [],
      isLoading: false,
      streamingContent: '',
      selectedRole: 'Requirements Analyst',
      availableRoles: ['Requirements Analyst', 'Software Architect', 'Software Developer', 'Test Engineer'],
      indexedFiles: [],
      isIndexing: false,
      indexingStatus: null,
      indexStats: null,
      memoryStats: null,
      generatedSrs: null,
      isGeneratingSrs: false,
      researchTask: null,

      // Actions
      initSession: async () => {
        try {
          const sessionId = get().sessionId
          const response = await api.getSessionInfo(sessionId)
          set({ 
            sessionId: response.session_id,
            selectedRole: response.selected_role,
            indexedFiles: [],
          })
          // Fetch initial stats
          get().fetchStats()
        } catch (error) {
          console.error('Failed to init session:', error)
          // Create new session
          const response = await api.createNewSession()
          set({ sessionId: response.session_id })
        }
      },

      fetchRoles: async () => {
        try {
          const response = await api.getRoles()
          set({ 
            availableRoles: response.roles,
            selectedRole: get().selectedRole || response.default,
          })
        } catch (error) {
          console.error('Failed to fetch roles:', error)
        }
      },

      setRole: (role: string) => {
        set({ selectedRole: role })
        api.setRole(role, get().sessionId)
      },

      sendMessage: async (message: string) => {
        const { sessionId, selectedRole, messages } = get()
        
        // Add user message
        const userMessage: Message = {
          role: 'user',
          content: message,
          timestamp: new Date().toISOString(),
        }
        set({ messages: [...messages, userMessage], isLoading: true })

        try {
          const response = await api.sendMessage(message, selectedRole, sessionId)
          
          const assistantMessage: Message = {
            role: 'assistant',
            content: response.response,
            timestamp: new Date().toISOString(),
            mermaidChart: response.mermaid_chart,
            pdfPath: response.pdf_path,
            docxPath: response.docx_path,
          }
          
          set(state => ({
            messages: [...state.messages, assistantMessage],
            isLoading: false,
          }))
          
          // Refresh stats after processing
          get().fetchStats()
        } catch (error) {
          console.error('Failed to send message:', error)
          const errorMessage: Message = {
            role: 'assistant',
            content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
            timestamp: new Date().toISOString(),
          }
          set(state => ({
            messages: [...state.messages, errorMessage],
            isLoading: false,
          }))
        }
      },

      sendMessageStream: async (message: string) => {
        const { sessionId, selectedRole, messages } = get()
        
        const userMessage: Message = {
          role: 'user',
          content: message,
          timestamp: new Date().toISOString(),
        }
        set({ messages: [...messages, userMessage], isLoading: true, streamingContent: '' })

        try {
          await api.sendMessageStream(
            message,
            selectedRole,
            sessionId,
            (chunk) => {
              set(state => ({ streamingContent: state.streamingContent + chunk }))
            },
            (data) => {
              // Handle completion
              const { streamingContent } = get()
              const assistantMessage: Message = {
                role: 'assistant',
                content: streamingContent,
                timestamp: new Date().toISOString(),
                mermaidChart: data?.mermaid,
                pdfPath: data?.pdf,
                docxPath: data?.docx,
              }
              set(state => ({
                messages: [...state.messages, assistantMessage],
                isLoading: false,
                streamingContent: '',
              }))
              get().fetchStats()
            },
            (error) => {
              const errorMessage: Message = {
                role: 'assistant',
                content: `Error: ${error}`,
                timestamp: new Date().toISOString(),
              }
              set(state => ({
                messages: [...state.messages, errorMessage],
                isLoading: false,
                streamingContent: '',
              }))
            }
          )
        } catch (error) {
          console.error('Stream error:', error)
          set({ isLoading: false, streamingContent: '' })
        }
      },

      clearChat: () => {
        set({ messages: [], streamingContent: '' })
        api.clearChatHistory(get().sessionId)
      },

      uploadAndIndexFiles: async (files: File[]) => {
        const { sessionId } = get()
        set({ isIndexing: true, indexingStatus: 'Uploading and indexing...' })

        try {
          const response = await api.uploadDocuments(files, true, sessionId)
          
          const result = response.index_result
          const successCount = result?.success?.length || 0
          const failedCount = result?.failed?.length || 0
          
          set(state => ({
            indexedFiles: [...state.indexedFiles, ...(result?.success || [])],
            isIndexing: false,
            indexingStatus: `✅ Indexed ${successCount} file(s), ${result?.total_chunks || 0} chunks${failedCount > 0 ? `, ${failedCount} failed` : ''}`,
          }))
          
          get().fetchStats()
        } catch (error) {
          console.error('Upload failed:', error)
          set({
            isIndexing: false,
            indexingStatus: `❌ Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`,
          })
        }
      },

      buildGraph: async (forceRebuild = false) => {
        const { sessionId } = get()
        set({ indexingStatus: forceRebuild ? 'Rebuilding graph...' : 'Building graph...' })

        try {
          await api.buildGraph(forceRebuild, sessionId)
          set({ indexingStatus: '✅ Knowledge graph updated!' })
          get().fetchStats()
        } catch (error) {
          set({ indexingStatus: `❌ Graph build failed: ${error instanceof Error ? error.message : 'Unknown error'}` })
        }
      },

      clearIndex: async () => {
        const { sessionId } = get()
        try {
          await api.clearIndex(sessionId)
          set({ indexedFiles: [], indexingStatus: '✅ Index cleared!' })
          get().fetchStats()
        } catch (error) {
          set({ indexingStatus: `❌ Clear failed: ${error instanceof Error ? error.message : 'Unknown error'}` })
        }
      },

      exportIndex: async () => {
        const { sessionId } = get()
        try {
          const blob = await api.downloadExport(sessionId)
          const url = window.URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = 'rag_index_export.json'
          a.click()
          window.URL.revokeObjectURL(url)
        } catch (error) {
          console.error('Export failed:', error)
        }
      },

      generateSrs: async (focus?: string) => {
        const { sessionId } = get()
        set({ isGeneratingSrs: true })

        try {
          const response = await api.generateSrs(focus, sessionId)
          if (response.success) {
            set({ generatedSrs: response.markdown, isGeneratingSrs: false })
          } else {
            set({ isGeneratingSrs: false })
            alert(response.message)
          }
        } catch (error) {
          set({ isGeneratingSrs: false })
          console.error('SRS generation failed:', error)
        }
      },

      downloadSrs: () => {
        const { generatedSrs } = get()
        if (!generatedSrs) return

        const blob = new Blob([generatedSrs], { type: 'text/markdown' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'srs.md'
        a.click()
        window.URL.revokeObjectURL(url)
      },

      startResearch: async (query: string) => {
        const { sessionId, selectedRole, messages } = get()
        
        // Add user message
        const userMessage: Message = {
          role: 'user',
          content: query,
          timestamp: new Date().toISOString(),
        }
        set({ messages: [...messages, userMessage] })

        try {
          const response = await api.startResearch(query, selectedRole, sessionId)
          
          set({
            researchTask: {
              taskId: response.task_id,
              status: 'running',
              query: query,
              startedAt: new Date().toISOString(),
            },
          })

          // Add status message
          const statusMessage: Message = {
            role: 'assistant',
            content: `🔬 **Deep Research Started**\n\nYour research query: *"${query.slice(0, 100)}${query.length > 100 ? '...' : ''}"*\n\nThe research is running in the background. Results will appear when complete.`,
            timestamp: new Date().toISOString(),
          }
          set(state => ({ messages: [...state.messages, statusMessage] }))

          // Start polling for status
          get().checkResearchStatus()
        } catch (error) {
          console.error('Research start failed:', error)
        }
      },

      checkResearchStatus: async () => {
        const { researchTask, sessionId } = get()
        if (!researchTask || researchTask.status !== 'running') return

        try {
          const status = await api.getResearchStatus(researchTask.taskId, sessionId)
          
          if (status.status === 'completed') {
            // Fetch result
            const result = await api.getResearchResult(researchTask.taskId, sessionId)
            
            const resultMessage: Message = {
              role: 'assistant',
              content: `🔬 **Deep Research Completed!**\n\n${result.response}`,
              timestamp: new Date().toISOString(),
              pdfPath: result.pdf_path,
              docxPath: result.docx_path,
            }
            
            set(state => ({
              messages: [...state.messages, resultMessage],
              researchTask: { ...state.researchTask!, status: 'completed' },
            }))
          } else if (status.status === 'error') {
            const errorMessage: Message = {
              role: 'assistant',
              content: `❌ **Research Error:** ${status.error}`,
              timestamp: new Date().toISOString(),
            }
            set(state => ({
              messages: [...state.messages, errorMessage],
              researchTask: { ...state.researchTask!, status: 'error' },
            }))
          } else if (status.status === 'running') {
            // Continue polling
            setTimeout(() => get().checkResearchStatus(), 3000)
          }
        } catch (error) {
          console.error('Status check failed:', error)
        }
      },

      clearResearch: async () => {
        const { researchTask, sessionId } = get()
        if (researchTask) {
          await api.clearResearchTask(researchTask.taskId, sessionId)
        }
        set({ researchTask: null })
      },

      fetchStats: async () => {
        const { sessionId } = get()
        try {
          const [indexStats, memoryStats] = await Promise.all([
            api.getIndexStats(sessionId),
            api.getMemoryStats(sessionId),
          ])
          set({ indexStats, memoryStats })
        } catch (error) {
          console.error('Failed to fetch stats:', error)
        }
      },

      clearMemory: async (clearMem0 = false) => {
        const { sessionId } = get()
        try {
          await api.clearMemory(clearMem0, sessionId)
          get().fetchStats()
        } catch (error) {
          console.error('Clear memory failed:', error)
        }
      },
    }),
    {
      name: 'raaa-storage',
      partialize: (state) => ({ 
        sessionId: state.sessionId,
        selectedRole: state.selectedRole,
      }),
    }
  )
)
