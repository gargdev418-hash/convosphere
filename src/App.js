// filepath: [App.js](http://_vscodecontentref_/1)
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { AuthProvider } from './contexts/AuthContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Inbox from './pages/Inbox';
import EmailSettings from './pages/EmailSettings';
import WhatsAppConfig from './pages/WhatsAppConfig';
import Integrations from './pages/Integrations';

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <WebSocketProvider>
          <Toaster position="top-right" />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/email-settings" element={<EmailSettings />} />
            <Route path="/whatsapp-config" element={<WhatsAppConfig />} />
            <Route path="/integrations" element={<Integrations />} />
            <Route path="/" element={<Navigate to="/dashboard" />} />
          </Routes>
        </WebSocketProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;