import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import RequireAuth from './components/RequireAuth';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';

import DeficitPage from './pages/DeficitPage';
import OrdersPage from './pages/OrdersPage';
import OrderDetailPage from './pages/OrderDetailPage';
import MonitoringPage from './pages/MonitoringPage';
import BccPage from './pages/BccPage';
import AdminPage from './pages/AdminPage';
import CitizenPage from './pages/CitizenPage';
import EvaluationPage from './pages/EvaluationPage';
import './App.css';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/citizen" element={<CitizenPage />} />
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route index element={<DeficitPage />} />
              <Route path="orders" element={<OrdersPage />} />
              <Route path="orders/:orderId" element={<OrderDetailPage />} />
              <Route path="monitoring" element={<MonitoringPage />} />
              <Route path="bcc" element={<BccPage />} />
              <Route path="admin" element={<AdminPage />} />
              <Route path="evaluation" element={<EvaluationPage />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
