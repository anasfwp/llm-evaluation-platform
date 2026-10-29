import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ComparisonPage } from "./pages/ComparisonPage";
import { DatasetPage } from "./pages/DatasetPage";
import { NewComparisonPage } from "./pages/NewComparisonPage";
import { NewRunPage } from "./pages/NewRunPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { RunPage } from "./pages/RunPage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectPage />} />
        <Route path="projects/:projectId/runs/new" element={<NewRunPage />} />
        <Route path="projects/:projectId/compare" element={<NewComparisonPage />} />
        <Route path="datasets/:datasetId" element={<DatasetPage />} />
        <Route path="runs/:runId" element={<RunPage />} />
        <Route path="comparisons/:comparisonId" element={<ComparisonPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
