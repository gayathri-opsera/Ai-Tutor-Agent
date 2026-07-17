import { Routes, Route, Navigate } from 'react-router-dom';
import { useUser } from './auth/UserContext';
import { Navbar } from './components/Navbar';
import { ChatInterface } from './components/ChatInterface';
import { HomePage } from './pages/Home/HomePage';
import { LoginPage } from './pages/Login/LoginPage';
import { CourseDetailPage } from './pages/Course/CourseDetailPage';
import { MyLearningPage } from './pages/MyLearning/MyLearningPage';
import { KnowledgeBaseList } from './pages/ContentManagement/KnowledgeBaseList';
import { DocumentUpload } from './pages/ContentManagement/DocumentUpload';
import { DocumentStatus } from './pages/ContentManagement/DocumentStatus';
import { LearnerProgressDashboard } from './pages/LearnerProgress/LearnerProgressDashboard';
import { AdminConfigPanel } from './pages/AdminConfig/AdminConfigPanel';
import { AdminMonitoringDashboard } from './pages/AdminMonitoring/AdminMonitoringDashboard';
import { AdminUsersPage } from './pages/AdminUsers/AdminUsersPage';
import { AssessmentPage } from './pages/Assessment/AssessmentPage';

export default function App() {
  const { user } = useUser();

  if (!user) return <LoginPage />;

  return (
    <div className="page-shell">
      <Navbar />
      <div className="page-body">
        <Routes>
          {/* ── Public / Learner ────────────────────────────── */}
          <Route path="/"                    element={<HomePage />} />
          <Route path="/chat"                element={<ChatInterface />} />
          <Route path="/learning"            element={<MyLearningPage />} />
          <Route path="/course/:id"          element={<CourseDetailPage />} />

          {/* ── Content browsing ────────────────────────────── */}
          <Route path="/content"             element={<KnowledgeBaseList />} />
          <Route path="/content/upload"      element={<DocumentUpload />} />
          <Route path="/content/status/:id"  element={<DocumentStatus />} />

          {/* ── Progress ────────────────────────────────────── */}
          <Route path="/progress"            element={<LearnerProgressDashboard />} />
          <Route path="/assessment/:id"      element={<AssessmentPage />} />

          {/* ── Admin (role-gated) ──────────────────────────── */}
          {user.role === 'Admin' && <>
            <Route path="/admin/config"      element={<AdminConfigPanel />} />
            <Route path="/admin/monitoring"  element={<AdminMonitoringDashboard />} />
            <Route path="/admin/users"       element={<AdminUsersPage />} />
          </>}

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  );
}
