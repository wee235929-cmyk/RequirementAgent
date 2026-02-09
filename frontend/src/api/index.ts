import axios from 'axios'

const API_BASE = '/api'

// Create axios instance with default config
const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add session ID to all requests
api.interceptors.request.use((config) => {
  const sessionId = localStorage.getItem('raaa-session-id')
  if (sessionId) {
    config.headers['X-Session-ID'] = sessionId
  }
  return config
})

// Helper to get session header
const getSessionHeader = (sessionId: string | null) => {
  return sessionId ? { 'X-Session-ID': sessionId } : {}
}

// ============= Chat API =============

export async function sendMessage(
  message: string,
  role: string | null,
  sessionId: string | null
) {
  const response = await api.post('/chat/send', {
    message,
    role,
  }, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function sendMessageStream(
  message: string,
  role: string | null,
  sessionId: string | null,
  onChunk: (chunk: string) => void,
  onComplete: (data: { mermaid?: string; pdf?: string; docx?: string }) => void,
  onError: (error: string) => void
) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(sessionId ? { 'X-Session-ID': sessionId } : {}),
    },
    body: JSON.stringify({ message, role }),
  })

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No reader available')

  const decoder = new TextDecoder()
  const extraData: { mermaid?: string; pdf?: string; docx?: string } = {}

  let currentEvent = ''
  
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value)
    const lines = text.split('\n')

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6)
        
        if (currentEvent === 'done') {
          onComplete(extraData)
        } else if (currentEvent === 'error') {
          onError(data)
        } else if (currentEvent === 'mermaid') {
          extraData.mermaid = data
        } else if (currentEvent === 'pdf') {
          extraData.pdf = data
        } else if (currentEvent === 'docx') {
          extraData.docx = data
        } else if (currentEvent === 'intent') {
          // Intent event, can be used for UI feedback
        } else if (data !== 'complete') {
          // Regular data chunk
          onChunk(data)
        }
        
        currentEvent = '' // Reset after processing data
      }
    }
  }
}

export async function getChatHistory(sessionId: string | null) {
  const response = await api.get('/chat/history', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function clearChatHistory(sessionId: string | null) {
  const response = await api.delete('/chat/history', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function setRole(role: string, sessionId: string | null) {
  const response = await api.post(`/chat/role?role=${encodeURIComponent(role)}`, null, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

// ============= Documents API =============

export async function uploadDocuments(
  files: File[],
  autoIndex: boolean = true,
  sessionId: string | null
) {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))
  formData.append('auto_index', String(autoIndex))

  const response = await api.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
      ...getSessionHeader(sessionId),
    },
  })
  return response.data
}

export async function buildGraph(forceRebuild: boolean, sessionId: string | null) {
  const response = await api.post(`/documents/graph/build?force_rebuild=${forceRebuild}`, null, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function clearIndex(sessionId: string | null) {
  const response = await api.delete('/documents/clear', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function downloadExport(sessionId: string | null) {
  const response = await api.get('/documents/export/download', {
    headers: getSessionHeader(sessionId),
    responseType: 'blob',
  })
  return response.data
}

export async function getIndexedFiles(sessionId: string | null) {
  const response = await api.get('/documents/files', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

// ============= SRS API =============

export async function generateSrs(focus: string | undefined, sessionId: string | null) {
  const response = await api.post('/srs/generate', { focus }, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function downloadSrs(sessionId: string | null) {
  const response = await api.get('/srs/download', {
    headers: getSessionHeader(sessionId),
    responseType: 'blob',
  })
  return response.data
}

export async function getCurrentSrs(sessionId: string | null) {
  const response = await api.get('/srs/current', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

// ============= Research API =============

export async function startResearch(
  query: string,
  role: string | null,
  sessionId: string | null
) {
  const response = await api.post('/research/start', { query, role }, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function getResearchStatus(taskId: string, sessionId: string | null) {
  const response = await api.get(`/research/status/${taskId}`, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function getResearchResult(taskId: string, sessionId: string | null) {
  const response = await api.get(`/research/result/${taskId}`, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function downloadResearchPdf(taskId: string) {
  const response = await api.get(`/research/download/pdf/${taskId}`, {
    responseType: 'blob',
  })
  return response.data
}

export async function downloadResearchDocx(taskId: string) {
  const response = await api.get(`/research/download/docx/${taskId}`, {
    responseType: 'blob',
  })
  return response.data
}

export async function clearResearchTask(taskId: string, sessionId: string | null) {
  const response = await api.delete(`/research/clear/${taskId}`, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function getCurrentResearch(sessionId: string | null) {
  const response = await api.get('/research/current', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

// ============= Stats API =============

export async function getMemoryStats(sessionId: string | null) {
  const response = await api.get('/stats/memory', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function getIndexStats(sessionId: string | null) {
  const response = await api.get('/stats/index', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function getSessionInfo(sessionId: string | null) {
  const response = await api.get('/stats/session', {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function getRoles() {
  const response = await api.get('/stats/roles')
  return response.data
}

export async function clearMemory(clearMem0: boolean, sessionId: string | null) {
  const response = await api.delete(`/stats/memory/clear?clear_mem0=${clearMem0}`, {
    headers: getSessionHeader(sessionId),
  })
  return response.data
}

export async function createNewSession() {
  const response = await api.post('/stats/session/new')
  return response.data
}
