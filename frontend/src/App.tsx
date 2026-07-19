import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext.tsx'
import Layout from './components/Layout.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'
import Loading from './components/ui/Loading.tsx'
import { Toaster } from './components/ui/Toaster.tsx'
import { ConfirmRoot } from './components/ui/ConfirmDialog.tsx'
import './index.css'

const LoginPage = lazy(() => import('./pages/LoginPage.tsx'))
const OAuthCallbackPage = lazy(() => import('./pages/OAuthCallbackPage.tsx'))
const DashboardPage = lazy(() => import('./pages/DashboardPage.tsx'))
const ReportsPage = lazy(() => import('./pages/ReportsPage.tsx'))
const DocumentsPage = lazy(() => import('./pages/DocumentsPage.tsx'))
const AuditPage = lazy(() => import('./pages/AuditPage.tsx'))
const AgentChatPage = lazy(() => import('./pages/AgentChatPage.tsx'))
const ConversationsPage = lazy(() => import('./pages/ConversationsPage.tsx'))
const QueriesPage = lazy(() => import('./pages/QueriesPage.tsx'))
const KpiDashboardPage = lazy(() => import('./pages/KpiDashboardPage.tsx'))
const ApprovalsPage = lazy(() => import('./pages/ApprovalsPage.tsx'))
const ReflectionsPage = lazy(() => import('./pages/ReflectionsPage.tsx'))
const UsersPage = lazy(() => import('./pages/UsersPage.tsx'))
const ApiKeysPage = lazy(() => import('./pages/ApiKeysPage.tsx'))
const LlmProvidersPage = lazy(() => import('./pages/LlmProvidersPage.tsx'))
const AccessPoliciesPage = lazy(() => import('./pages/AccessPoliciesPage.tsx'))
const ReportSubscriptionsPage = lazy(() => import('./pages/ReportSubscriptionsPage.tsx'))
const ReportTemplatesPage = lazy(() => import('./pages/ReportTemplatesPage.tsx'))
const SettingsPage = lazy(() => import('./pages/SettingsPage.tsx'))
const SecurityPage = lazy(() => import('./pages/SecurityPage.tsx'))
const AdminLayout = lazy(() => import('./pages/admin/AdminLayout.tsx'))
const Dashboard = lazy(() => import('./pages/admin/Dashboard.tsx'))
const ModelManagement = lazy(() => import('./pages/admin/ModelManagement.tsx'))
const PromptManagement = lazy(() => import('./pages/admin/PromptManagement.tsx'))
const ToolManagement = lazy(() => import('./pages/admin/ToolManagement.tsx'))
const SkillManagement = lazy(() => import('./pages/admin/SkillManagement.tsx'))
const SearchEngineManagement = lazy(() => import('./pages/admin/SearchEngineManagement.tsx'))
const AgentConfigManagement = lazy(() => import('./pages/admin/AgentConfigManagement.tsx'))
const McpServerManagement = lazy(() => import('./pages/admin/McpServerManagement.tsx'))
const SandboxManagement = lazy(() => import('./pages/admin/SandboxManagement.tsx'))
const SystemSettingsPage = lazy(() => import('./pages/admin/SystemSettings.tsx'))
const EvalManagement = lazy(() => import('./pages/admin/EvalManagement.tsx'))
const FactorMiningPage = lazy(() => import('./pages/admin/FactorMiningPage.tsx'))
const BacktestingPage = lazy(() => import('./pages/admin/BacktestingPage.tsx'))
const WorkflowEditorPage = lazy(() => import('./pages/admin/WorkflowEditorPage.tsx'))
const ContextManagementPage = lazy(() => import('./pages/admin/ContextManagementPage.tsx'))
const ToolMonitoringPage = lazy(() => import('./pages/admin/ToolMonitoringPage.tsx'))
const PromptDeepManagement = lazy(() => import('./pages/admin/PromptDeepManagement.tsx'))
const RuntimeLogsPage = lazy(() => import('./pages/admin/RuntimeLogsPage.tsx'))
const HitlPage = lazy(() => import('./pages/HitlPage.tsx'))
const NotFoundPage = lazy(() => import('./pages/NotFoundPage.tsx'))

function PrivateRoute({
  children,
  roles,
}: {
  children: React.ReactNode
  roles?: string[]
}) {
  const { isAuthenticated, loading, role } = useAuth()
  if (loading) {
    return <Loading />
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  // 角色守卫：roles 提供时，角色不在白名单则重定向到 dashboard。
  // 纵深防御：侧边栏已隐藏无权限菜单，此处拦截手动输入 URL 的越权访问。
  if (roles && (!role || !roles.includes(role))) {
    return <Navigate to="/dashboard" replace />
  }
  return <Layout>{children}</Layout>
}

function NotFoundRoute() {
  const { isAuthenticated, loading } = useAuth()
  if (loading) {
    return <Loading />
  }
  if (isAuthenticated) {
    return (
      <Layout>
        <NotFoundPage />
      </Layout>
    )
  }
  return <NotFoundPage />
}

function App() {
  return (
    <AuthProvider>
      <ErrorBoundary>
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/login/callback" element={<OAuthCallbackPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <DashboardPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/reports"
            element={
              <PrivateRoute>
                <ReportsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/reports/:id"
            element={
              <PrivateRoute>
                <ReportsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/documents"
            element={
              <PrivateRoute>
                <DocumentsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/documents/:id"
            element={
              <PrivateRoute>
                <DocumentsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/audit"
            element={
              <PrivateRoute>
                <AuditPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/agent"
            element={
              <PrivateRoute>
                <AgentChatPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/conversations"
            element={
              <PrivateRoute>
                <ConversationsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/queries"
            element={
              <PrivateRoute>
                <QueriesPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/kpi"
            element={
              <PrivateRoute>
                <KpiDashboardPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/approvals"
            element={
              <PrivateRoute roles={['admin', 'auditor']}>
                <ApprovalsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/reflections"
            element={
              <PrivateRoute roles={['admin', 'auditor']}>
                <ReflectionsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/hitl"
            element={
              <PrivateRoute roles={['admin', 'auditor']}>
                <HitlPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/users"
            element={
              <PrivateRoute roles={['admin']}>
                <UsersPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/api-keys"
            element={
              <PrivateRoute roles={['admin']}>
                <ApiKeysPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/llm-providers"
            element={
              <PrivateRoute roles={['admin']}>
                <LlmProvidersPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/access-policies"
            element={
              <PrivateRoute roles={['admin']}>
                <AccessPoliciesPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/report-subscriptions"
            element={
              <PrivateRoute roles={['admin', 'finance_manager']}>
                <ReportSubscriptionsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/report-templates"
            element={
              <PrivateRoute roles={['admin', 'finance_manager']}>
                <ReportTemplatesPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <PrivateRoute roles={['admin']}>
                <SettingsPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/security"
            element={
              <PrivateRoute>
                <SecurityPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <PrivateRoute roles={['admin']}>
                <AdminLayout />
              </PrivateRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="models" element={<ModelManagement />} />
            <Route path="prompts" element={<PromptManagement />} />
            <Route path="prompt-deep" element={<PromptDeepManagement />} />
            <Route path="runtime-logs" element={<RuntimeLogsPage />} />
            <Route path="tools" element={<ToolManagement />} />
            <Route path="tool-monitoring" element={<ToolMonitoringPage />} />
            <Route path="context-management" element={<ContextManagementPage />} />
            <Route path="skills" element={<SkillManagement />} />
            <Route path="search-engines" element={<SearchEngineManagement />} />
            <Route path="mcp-servers" element={<McpServerManagement />} />
            <Route path="sandbox-configs" element={<SandboxManagement />} />
            <Route path="agents" element={<AgentConfigManagement />} />
            <Route path="settings" element={<SystemSettingsPage />} />
            <Route path="eval-management" element={<EvalManagement />} />
            <Route path="factor-mining" element={<FactorMiningPage />} />
            <Route path="backtesting" element={<BacktestingPage />} />
            <Route path="workflow-editor" element={<WorkflowEditorPage />} />
          </Route>
          <Route path="*" element={<NotFoundRoute />} />
        </Routes>
      </Suspense>
      <Toaster />
      <ConfirmRoot />
      </ErrorBoundary>
    </AuthProvider>
  )
}

export default App
