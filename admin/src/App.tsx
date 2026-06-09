import { Navigate, Route, Routes } from "react-router-dom";

import { AdminRoute } from "@/components/admin-route";
import { PublicRoute } from "@/components/public-route";

import LoginPage from "@/pages/login";
import DashboardPage from "@/pages/admin/dashboard";
import SystemPage from "@/pages/admin/system";
import LabelingPage from "@/pages/admin/labeling";
import ModelsPage from "@/pages/admin/models";
import JobsPage from "@/pages/admin/jobs";
import CVsPage from "@/pages/admin/cvs";
import RecommendPage from "@/pages/admin/recommend";
import LLMProvidersPage from "@/pages/admin/llm-providers";
import CVUploadPage from "@/pages/admin/cv-upload";
import LLMLogsPage from "@/pages/admin/llm-logs";
import JDExtractPage from "@/pages/admin/jd-extract";
import JDBatchLayout from "@/pages/admin/jd-batch";
import JDBatchOverview from "@/pages/admin/jd-batch/overview";
import JDBatchNew from "@/pages/admin/jd-batch/new";
import JDBatchDetail from "@/pages/admin/jd-batch/detail";
import CVBatchLayout from "@/pages/admin/cv-batch";
import CVBatchOverview from "@/pages/admin/cv-batch/overview";
import CVBatchDetail from "@/pages/admin/cv-batch/detail";
import LabelBatchLayout from "@/pages/admin/label-batch";
import LabelBatchOverview from "@/pages/admin/label-batch/overview";
import LabelBatchDetail from "@/pages/admin/label-batch/detail";
import VerifySchedulePage from "@/pages/admin/schedule/verify";
import ExtractSchedulePage from "@/pages/admin/schedule/extract";
import MorningRefreshSchedulePage from "@/pages/admin/schedule/morning-refresh";
import EmployeesPage from "@/pages/admin/employees";
import EmployeeDetailPage from "@/pages/admin/employees/detail";
import PipelinePage from "@/pages/admin/pipeline";
import JobTrackingPage from "@/pages/admin/job-tracking";
import ApplyEmailPage from "@/pages/admin/apply-email";
import SettingsPage from "@/pages/admin/settings";

function App() {
  return (
    <Routes>
      <Route element={<AdminRoute />} path="/admin">
        <Route index element={<DashboardPage />} />
        <Route path="system" element={<SystemPage />} />
        <Route path="labeling" element={<LabelingPage />} />
        <Route path="models" element={<ModelsPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="cvs" element={<CVsPage />} />
        <Route path="recommend" element={<RecommendPage />} />
        <Route path="llm-providers" element={<LLMProvidersPage />} />
        <Route path="cvs/upload" element={<CVUploadPage />} />
        <Route path="llm-logs" element={<LLMLogsPage />} />
        <Route path="jd-extract" element={<JDExtractPage />} />
        <Route path="jd-batch" element={<JDBatchLayout />}>
          <Route index element={<JDBatchOverview />} />
          <Route path="new" element={<JDBatchNew />} />
          <Route path=":id" element={<JDBatchDetail />} />
        </Route>
        <Route path="cv-batch" element={<CVBatchLayout />}>
          <Route index element={<CVBatchOverview />} />
          <Route path=":id" element={<CVBatchDetail />} />
        </Route>
        <Route path="label-batch" element={<LabelBatchLayout />}>
          <Route index element={<LabelBatchOverview />} />
          <Route path=":id" element={<LabelBatchDetail />} />
        </Route>
        <Route path="schedule/verify" element={<VerifySchedulePage />} />
        <Route path="schedule/extract" element={<ExtractSchedulePage />} />
        <Route path="schedule/morning-refresh" element={<MorningRefreshSchedulePage />} />

        {/* Feature 012 — Employee MVP */}
        <Route path="employees" element={<EmployeesPage />} />
        <Route path="employees/:id" element={<EmployeeDetailPage />} />
        <Route path="pipeline" element={<PipelinePage />} />
        <Route path="job-tracking" element={<JobTrackingPage />} />
        <Route path="apply-email" element={<ApplyEmailPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route element={<PublicRoute />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>

      <Route path="*" element={<Navigate replace to="/admin" />} />
    </Routes>
  );
}

export default App;
