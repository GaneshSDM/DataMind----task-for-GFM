import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './contexts/AuthContext'
import AppShell from './components/layout/AppShell'
import SignIn from './pages/SignIn'
import Chats from './pages/Chats'
import { GeographyPage, DomainPage, SubDomainPage, RagCategoryPage, RagSubCategoryPage } from './pages/MasterData'
import SecurityGroups from './pages/SecurityGroups'
import Guardrails from './pages/Guardrails'
import { UserManagement, RLSPage, CLSPage, SLMConfigPage, DBConnectionsPage } from './pages/AdminPages'
import RAGPipelines from './pages/RAGPipelines'
import './styles/global.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<SignIn />} />
          <Route path="/" element={<AppShell />}>
            <Route index element={<Navigate to="/chats" replace />} />
            <Route path="chats"          element={<Chats />} />
            <Route path="geographies"    element={<GeographyPage />} />
            <Route path="domains"        element={<DomainPage />} />
            <Route path="subdomains"     element={<SubDomainPage />} />
            <Route path="security-groups" element={<SecurityGroups />} />
            <Route path="guardrails"     element={<Guardrails />} />
            <Route path="rls"            element={<RLSPage />} />
            <Route path="cls"            element={<CLSPage />} />
            <Route path="users"          element={<UserManagement />} />
            <Route path="slm-config"     element={<SLMConfigPage />} />
            <Route path="db-connections" element={<DBConnectionsPage />} />
            <Route path="rag-pipelines"    element={<RAGPipelines />} />
            <Route path="rag-categories"   element={<RagCategoryPage />} />
            <Route path="rag-sub-categories" element={<RagSubCategoryPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 3500,
          style: {
            fontFamily: "'Montserrat', sans-serif",
            fontSize: 13,
            fontWeight: 500,
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
          },
        }}
      />
    </AuthProvider>
  </StrictMode>
)
