import './App.css';
import { AgentList } from './components/AgentList';
import { EventStream } from './components/EventStream';
import { Shield } from 'lucide-react';

function App() {
  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-gradient-to-r from-blue-600 to-purple-600 text-white shadow-lg">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <Shield className="w-10 h-10" />
            <div>
              <h1 className="text-3xl font-bold">NAGA-7 Dashboard</h1>
              <p className="text-blue-100 text-sm">Security Event Monitoring System</p>
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="col-span-1">
            <AgentList />
          </div>
          <div className="col-span-1">
            <EventStream />
          </div>
        </div>
      </main>

      <footer className="mt-12 py-6 bg-white border-t">
        <div className="container mx-auto px-4 text-center text-gray-500 text-sm">
          NAGA-7 Security Monitoring Platform v0.0.0
        </div>
      </footer>
    </div>
  );
}

export default App;
