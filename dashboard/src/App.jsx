import { BrowserRouter, Routes, Route } from 'react-router-dom';
import ThreadList from './components/ThreadList';
import ThreadDetail from './components/ThreadDetail';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ThreadList />} />
        <Route path="/thread/:id" element={<ThreadDetail />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
