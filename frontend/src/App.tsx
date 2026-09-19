import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { checkHealth } from './api/client';
import './App.css';

const queryClient = new QueryClient();

function HealthCheck() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['health'],
    queryFn: checkHealth,
    refetchInterval: 30000,
  });

  if (isLoading) return <div className="status loading">Connecting to API...</div>;
  if (error) return <div className="status error">❌ API unreachable</div>;

  return (
    <div className="status ok">
      ✅ API connected — v{data.version} ({data.environment})
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="app">
        <header>
          <h1>🔌 Plateforme Nationale de Délestage</h1>
          <p>National Intelligent Load Shedding Management Platform</p>
        </header>
        <main>
          <HealthCheck />
          <div className="info">
            <h2>Modules</h2>
            <ul>
              <li>✅ M0 — Project Setup</li>
              <li>⬜ M1 — Database Schema & Seed Data</li>
              <li>⬜ M2 — Authentication, Roles & Audit</li>
              <li>⬜ M3 — Deficit Computation</li>
              <li>⬜ M4 — Shed Orders</li>
              <li>⬜ M5 — Allocation & Feeder Selection</li>
              <li>⬜ M6 — Real-time Monitoring</li>
              <li>⬜ M7 — BCC Execution</li>
              <li>⬜ M8 — Rotation Engine</li>
              <li>⬜ M9 — Administration & Audit View</li>
              <li>⬜ M10 — Citizen Platform</li>
              <li>⬜ M11 — Demo Simulator</li>
              <li>⬜ M12 — Evaluation & Tests</li>
            </ul>
          </div>
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
