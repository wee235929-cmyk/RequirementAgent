import { useEffect } from 'react'
import Layout from './components/Layout'
import { useAppStore } from './store/appStore'

function App() {
  const { initSession, fetchRoles } = useAppStore()

  useEffect(() => {
    initSession()
    fetchRoles()
  }, [initSession, fetchRoles])

  return <Layout />
}

export default App
