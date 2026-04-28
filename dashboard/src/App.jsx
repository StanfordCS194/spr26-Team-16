import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AppShell from './components/AppShell';
import ThreadDetail from './components/ThreadDetail';
import EmptyDetail from './components/EmptyDetail';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<EmptyDetail />} />
          <Route path="/thread/:id" element={<ThreadDetail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
