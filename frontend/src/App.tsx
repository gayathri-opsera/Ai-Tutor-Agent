import { Routes, Route, Navigate } from 'react-router-dom';
import { ChatInterface } from './components/ChatInterface';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { KnowledgeBaseList } from './pages/ContentManagement/KnowledgeBaseList';
import { DocumentUpload } from './pages/ContentManagement/DocumentUpload';
import { DocumentStatus } from './pages/ContentManagement/DocumentStatus';
import { LearnerProgressDashboard } from './pages/LearnerProgress/LearnerProgressDashboard';
import { AdminConfigPanel } from './pages/AdminConfig/AdminConfigPanel';
import { AdminMonitoringDashboard } from './pages/AdminMonitoring/AdminMonitoringDashboard';

export default function App() {
  return (
    <div className="app-layout">
      <Routes>
        <Route path="/" element={<ProtectedRoute><ChatInterface /></ProtectedRoute>} />
        <Route path="/content" element={<ProtectedRoute roles={['Creator', 'Admin']}><KnowledgeBaseList /></ProtectedRoute>} />
        <Route path="/content/upload" element={<ProtectedRoute roles={['Creator', 'Admin']}><DocumentUpload /></ProtectedRoute>} />
        <Route path="/content/status/:id" element={<ProtectedRoute roles={['Creator', 'Admin']}><DocumentStatus /></ProtectedRoute>} />
        <Route path="/progress" element={<ProtectedRoute><LearnerProgressDashboard /></ProtectedRoute>} />
        <Route path="/admin/config" element={<ProtectedRoute roles={['Admin']}><AdminConfigPanel /></ProtectedRoute>} />
        <Route path="/admin/monitoring" element={<ProtectedRoute roles={['Admin']}><AdminMonitoringDashboard /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
