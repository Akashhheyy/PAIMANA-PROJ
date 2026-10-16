import { Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { OverviewPage } from './pages/OverviewPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { ProjectDetailPage } from './pages/ProjectDetailPage';
import { ComingSoonPage } from './pages/ComingSoonPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectCode" element={<ProjectDetailPage />} />
        <Route
          path="/early-warnings"
          element={<ComingSoonPage title="Early Warnings" />}
        />
        <Route path="*" element={<OverviewPage />} />
      </Route>
    </Routes>
  );
}
