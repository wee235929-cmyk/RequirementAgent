import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Message } from '../store/appStore'

interface ChatMessageProps {
  message: Message
  isStreaming?: boolean
}

export default function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar - Simple circle with initial */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
          isUser ? 'bg-white/10 text-white' : 'bg-white/5 text-gray-400'
        }`}
      >
        {isUser ? 'U' : 'R'}
      </div>

      {/* Message Content */}
      <div
        className={`max-w-[80%] px-4 py-3 rounded-2xl ${
          isUser
            ? 'bg-white/10 text-white rounded-tr-sm'
            : 'bg-white/5 text-gray-200 rounded-tl-sm'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="markdown-content">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '')
                  const language = match ? match[1] : ''
                  
                  if (language === 'mermaid') {
                    return null
                  }
                  
                  if (inline) {
                    return (
                      <code className="bg-white/10 px-1.5 py-0.5 rounded text-sm text-gray-200" {...props}>
                        {children}
                      </code>
                    )
                  }
                  
                  return (
                    <pre className="bg-black/50 border border-white/10 text-gray-200 p-4 rounded-lg overflow-x-auto my-2">
                      <code className={className} {...props}>
                        {children}
                      </code>
                    </pre>
                  )
                },
                a({ href, children, ...props }: any) {
                  return (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:text-blue-300 underline"
                      {...props}
                    >
                      {children}
                    </a>
                  )
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-white/50 animate-pulse ml-1" />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
