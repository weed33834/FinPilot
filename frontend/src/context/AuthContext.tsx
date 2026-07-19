import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore.ts'

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { fetchMe, isAuthenticated, loading } = useAuthStore()

  // 应用启动时检查会话
  useEffect(() => {
    fetchMe().catch(() => {
      // fetchMe 内部不设 loading=false，由 store 默认 loading 变为 false 需在 catch 后设置
    }).finally(() => {
      useAuthStore.setState({ loading: false })
    })
  }, [fetchMe])

  const navigate = useNavigate()

  // 监听登出跳转：当 isAuthenticated 从 true→false 时跳 /login
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/login', { replace: true })
    }
  }, [isAuthenticated, loading, navigate])

  return <>{children}</>
}

export { useAuthStore as useAuth }
