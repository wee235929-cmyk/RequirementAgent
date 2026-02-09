import { useState } from 'react'
import Sidebar from './Sidebar'
import ChatArea from './ChatArea'
import StarryBackground from './StarryBackground'

export default function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  return (
    <div className="flex h-screen bg-black relative overflow-hidden">
      {/* Starry Background - at the bottom layer */}
      <StarryBackground />
      
      {/* Sidebar - above background */}
      <Sidebar 
        isCollapsed={sidebarCollapsed} 
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
      />
      
      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col overflow-hidden relative z-10">
        <ChatArea />
      </main>
    </div>
  )
}
