import { Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { OverviewPage } from './pages/OverviewPage';
import { ComingSoonPage } from './pages/ComingSoonPage';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<OverviewPage />} />
        <Route
          path="/projects"
          element={<ComingSoonPage title="Projects" />}
        />
        <Route
          path="/early-warnings"
          element={<ComingSoonPage title="Early Warnings" />}
        />
        <Route path="*" element={<OverviewPage />} />
      </Route>
    </Routes>
  );
}
