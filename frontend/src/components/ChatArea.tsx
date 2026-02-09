import { useState, useRef, useEffect } from 'react'
import { useAppStore } from '../store/appStore'
import ChatMessage from './ChatMessage'
import MermaidDiagram from './MermaidDiagram'

export default function ChatArea() {
  const {
    messages,
    isLoading,
    streamingContent,
    sendMessage,
    researchTask,
  } = useAppStore()

  const [input, setInput] = useState('')
  const [showWelcome, setShowWelcome] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (messages.length > 0) {
      setShowWelcome(false)
    }
  }, [messages])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 150)}px`
    }
  }, [input])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    setShowWelcome(false)
    const message = input.trim()
    setInput('')
    await sendMessage(message)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const showWelcomeScreen = showWelcome && messages.length === 0

  return (
    <div className="flex flex-col h-full relative">
      {/* Content */}
      <div className="flex-1 overflow-y-auto relative">
        {showWelcomeScreen ? (
          /* Welcome Screen - Grok Style */
          <div className="flex flex-col items-center justify-center h-full px-4">
            <div className="text-center max-w-2xl animate-fade-in-up">
              {/* Logo */}
              <div className="mb-12">
                <img 
                  src="/RAAAICON.png" 
                  alt="RAAA" 
                  className="w-96 h-72 mx-auto animate-subtle-pulse object-contain"
                />
              </div>
              
              {/* Description */}
              <p className="text-gray-200 text-2xl leading-relaxed mb-8">
                I'm RAAA, your intelligent assistant for requirements analysis, document Q&A, deep research, and conversations.
              </p>
              <p className="text-gray-400 text-lg">
                Feel free to ask me anything you'd like to know.
              </p>
              <p className="text-gray-500 text-base mt-4">
                Email: lee235929@gmail.com
              </p>
            </div>
          </div>
        ) : (
          /* Chat Messages */
          <div className="px-6 py-4 space-y-4 max-w-4xl mx-auto w-full">
            {messages.map((message, index) => (
              <div key={index} className="animate-fade-in">
                <ChatMessage message={message} />
                {message.mermaidChart && (
                  <div className="mt-3 ml-12">
                    <MermaidDiagram code={message.mermaidChart} />
                  </div>
                )}
                {(message.pdfPath || message.docxPath) && (
                  <div className="mt-3 ml-12 flex gap-2">
                    {message.pdfPath && (
                      <a
                        href={`/api/research/download/pdf/${message.pdfPath.split('/').pop()?.replace('.pdf', '')}`}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white/80 text-sm rounded-lg transition-colors"
                      >
                        Download PDF
                      </a>
                    )}
                    {message.docxPath && (
                      <a
                        href={`/api/research/download/docx/${message.docxPath.split('/').pop()?.replace('.docx', '')}`}
                        className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-white/80 text-sm rounded-lg transition-colors"
                      >
                        Download Word
                      </a>
                    )}
                  </div>
                )}
              </div>
            ))}

            {streamingContent && (
              <div className="animate-fade-in">
                <ChatMessage
                  message={{ role: 'assistant', content: streamingContent }}
                  isStreaming
                />
              </div>
            )}

            {isLoading && !streamingContent && (
              <div className="flex items-center gap-2 text-gray-500 ml-12">
                <div className="flex gap-1">
                  <span className="loading-dot w-2 h-2 bg-gray-500 rounded-full"></span>
                  <span className="loading-dot w-2 h-2 bg-gray-500 rounded-full"></span>
                  <span className="loading-dot w-2 h-2 bg-gray-500 rounded-full"></span>
                </div>
                <span className="text-sm">Thinking...</span>
              </div>
            )}

            {researchTask?.status === 'running' && (
              <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4 ml-12">
                <div className="text-blue-400 font-medium">
                  Deep Research in Progress
                </div>
                <p className="text-sm text-blue-400/70 mt-1">
                  This may take a few minutes. You can continue chatting.
                </p>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input Area - Grok Style */}
      <div className="relative z-10 px-4 py-6">
        <div className="max-w-3xl mx-auto">
          <form onSubmit={handleSubmit} className="relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Wanna konw？"
              className="w-full px-5 py-4 pr-14 bg-white/5 border border-white/10 rounded-2xl resize-none text-white placeholder-gray-500 focus:outline-none focus:border-white/20 glow-input min-h-[56px] max-h-[200px]"
              rows={1}
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="absolute right-3 bottom-3 p-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
