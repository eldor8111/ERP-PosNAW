import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from 'react-hot-toast';
import '../index.css';
import './mobile.css';
import { LangProvider } from '../context/LangContext.jsx';
import { MobileAuthProvider } from './lib/auth';
import MobileApp from './MobileApp';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <LangProvider>
      <MobileAuthProvider>
        <Toaster position="top-center" toastOptions={{ duration: 3000, style: { fontSize: 14 } }} />
        <MobileApp />
      </MobileAuthProvider>
    </LangProvider>
  </StrictMode>,
);
