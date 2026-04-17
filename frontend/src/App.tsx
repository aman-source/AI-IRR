import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import OverviewPage from './pages/OverviewPage';
import PlaceholderPage from './pages/PlaceholderPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="targets" element={<PlaceholderPage title="Targets" />} />
          <Route path="prefixes" element={<PlaceholderPage title="Prefixes" />} />
          <Route path="diffs" element={<PlaceholderPage title="Diffs" />} />
          <Route path="tickets" element={<PlaceholderPage title="Tickets" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
