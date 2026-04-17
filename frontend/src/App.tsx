import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import OverviewPage from './pages/OverviewPage';
import TargetsPage from './pages/TargetsPage';
import PrefixesPage from './pages/PrefixesPage';
import DiffsPage from './pages/DiffsPage';
import TicketsPage from './pages/TicketsPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="targets" element={<TargetsPage />} />
          <Route path="prefixes" element={<PrefixesPage />} />
          <Route path="diffs" element={<DiffsPage />} />
          <Route path="tickets" element={<TicketsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
