import { Routes, Route, Navigate } from 'react-router-dom';
import { useUser } from './auth/UserContext';
import { Navbar } from './components/Navbar';
import { ChatInterface } from './components/ChatInterface';
import { HomePage } from './pages/Home/HomePage';
import { LoginPage } from './pages/Login/LoginPage';
import { RegisterPage } from './pages/Register/RegisterPage';
import { PendingApprovalPage } from './pages/PendingApproval/PendingApprovalPage';
import { CourseDetailPage } from './pages/Course/CourseDetailPage';
import { MyLearningPage } from './pages/MyLearning/MyLearningPage';
import { KnowledgeBaseList } from './pages/ContentManagement/KnowledgeBaseList';
import { DocumentUpload } from './pages/ContentManagement/DocumentUpload';
import { DocumentStatus } from './pages/ContentManagement/DocumentStatus';
import { CreatorCourseManagement } from './pages/ContentManagement/CreatorCourseManagement';
import { LearnerProgressDashboard } from './pages/LearnerProgress/LearnerProgressDashboard';
import { AdminConfigPanel } from './pages/AdminConfig/AdminConfigPanel';
import { AdminMonitoringDashboard } from './pages/AdminMonitoring/AdminMonitoringDashboard';
import { AdminUsersPage } from './pages/AdminUsers/AdminUsersPage';
import { AdminDashboardPage } from './pages/AdminDashboard/AdminDashboardPage';
import { AdminApprovalsPage } from './pages/AdminApprovals/AdminApprovalsPage';
import { CreatorDashboardPage } from './pages/CreatorDashboard/CreatorDashboardPage';
import { AssessmentPage } from './pages/Assessment/AssessmentPage';

export default function App() {
  const { user, initializing, login } = useUser();

  if (initializing) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <p style={{ color: 'var(--muted)' }}>Loading…</p>
      </div>
    );
  }

  if (!user) return (
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="*"         element={<LoginPage onLogin={login} />} />
    </Routes>
  );

  if (user.approvalStatus === 'pending') return <PendingApprovalPage />;

  const isAdmin = user.isAdmin;

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

          {/* ── Creator ────────────────────────────────────────── */}
          {(user.isCreator || isAdmin) && (
            <Route path="/creator/dashboard" element={<CreatorDashboardPage />} />
          )}
          {(user.isCreator || isAdmin) && (
            <Route path="/creator/courses" element={<CreatorCourseManagement />} />
          )}

          {/* ── Admin (role-gated) ──────────────────────────── */}
          {isAdmin && <>
            <Route path="/admin/config"      element={<AdminConfigPanel />} />
            <Route path="/admin/monitoring"  element={<AdminMonitoringDashboard />} />
            <Route path="/admin/users"       element={<AdminUsersPage />} />
            <Route path="/admin/dashboard"   element={<AdminDashboardPage />} />
            <Route path="/admin/approvals"   element={<AdminApprovalsPage />} />
          </>}

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
  );
}
