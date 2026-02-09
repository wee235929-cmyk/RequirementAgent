import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

interface MermaidDiagramProps {
  code: string
}

// Initialize mermaid with default config
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'inherit',
  themeVariables: {
    primaryColor: '#1e293b',
    primaryTextColor: '#fff',
    primaryBorderColor: '#334155',
    lineColor: '#64748b',
    secondaryColor: '#0f172a',
    tertiaryColor: '#1e293b',
  },
})

let diagramId = 0

export default function MermaidDiagram({ code }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [svg, setSvg] = useState<string>('')

  useEffect(() => {
    const renderDiagram = async () => {
      if (!code || !containerRef.current) return

      // Clean the code - remove markdown code block markers if present
      let cleanCode = code.trim()
      if (cleanCode.startsWith('```mermaid')) {
        cleanCode = cleanCode.replace(/^```mermaid\s*/, '').replace(/```\s*$/, '')
      } else if (cleanCode.startsWith('```')) {
        cleanCode = cleanCode.replace(/^```\s*/, '').replace(/```\s*$/, '')
      }

      try {
        const id = `mermaid-${diagramId++}`
        const { svg } = await mermaid.render(id, cleanCode)
        setSvg(svg)
        setError(null)
      } catch (err) {
        console.error('Mermaid rendering error:', err)
        setError(err instanceof Error ? err.message : 'Failed to render diagram')
        setSvg('')
      }
    }

    renderDiagram()
  }, [code])

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
        <p className="text-red-400 text-sm font-medium">Failed to render diagram</p>
        <p className="text-red-400/70 text-xs mt-1">{error}</p>
        <details className="mt-2">
          <summary className="text-xs text-gray-500 cursor-pointer">View code</summary>
          <pre className="mt-2 text-xs bg-black/50 text-gray-300 p-2 rounded overflow-x-auto">
            {code}
          </pre>
        </details>
      </div>
    )
  }

  if (!svg) {
    return (
      <div className="bg-white/5 rounded-lg p-4 animate-pulse">
        <div className="h-32 bg-white/10 rounded"></div>
      </div>
    )
  }

  return (
    <div className="bg-white/5 border border-white/10 rounded-lg p-4 overflow-x-auto">
      <div
        ref={containerRef}
        className="mermaid-container"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  )
}
