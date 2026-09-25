import { useState, useEffect } from 'react';
import ConnectDBScreen from './components/ConnectDBScreen';
import ChatWindow from './components/ChatWindow';
import HelpSidebar from './components/HelpSidebar';
import { getSessionStatus } from './api/client';

export default function App() {
  const [screen, setScreen] = useState('connect'); // 'connect' | 'chat'
  const [session, setSession] = useState(null);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState('');
  const [isRestoringSession, setIsRestoringSession] = useState(true);

  // Check and restore persisted session from localStorage on mount
  useEffect(() => {
    const restoreSession = async () => {
      try {
        const storedStr = localStorage.getItem('nl2sql_session');
        if (!storedStr) {
          setIsRestoringSession(false);
          return;
        }

        const storedData = JSON.parse(storedStr);
        if (!storedData?.session_id) {
          localStorage.removeItem('nl2sql_session');
          setIsRestoringSession(false);
          return;
        }

        // Verify with backend that session is active or restorable
        const status = await getSessionStatus(storedData.session_id);
        if (status?.status === 'connected') {
          const mergedSession = {
            ...storedData,
            ...status,
          };
          setSession(mergedSession);
          setScreen('chat');
          setSessionExpiredNotice('');
        }
      } catch (err) {
        console.warn('Session restoration failed:', err.message);
        localStorage.removeItem('nl2sql_session');
        setSession(null);
        setScreen('connect');
        setSessionExpiredNotice('Your previous session expired, please reconnect.');
      } finally {
        setIsRestoringSession(false);
      }
    };

    restoreSession();
  }, []);

  const handleConnected = (sessionData) => {
    try {
      localStorage.setItem('nl2sql_session', JSON.stringify(sessionData));
    } catch (e) {
      console.warn('Could not save session to localStorage:', e);
    }
    setSession(sessionData);
    setScreen('chat');
    setSessionExpiredNotice('');
  };

  const handleDisconnect = () => {
    localStorage.removeItem('nl2sql_session');
    setSession(null);
    setScreen('connect');
    setSessionExpiredNotice('');
  };

  return (
    <div className="min-h-screen bg-[#F4F7F7] text-slate-800 flex flex-col relative overflow-x-hidden selection:bg-teal-100 selection:text-teal-900">
      
      {/* Subtle Ambient Decorative Gradient Glows for Glassmorphic Depth */}
      <div className="fixed top-[-10%] left-[-5%] w-[45vw] h-[45vw] rounded-full bg-teal-200/25 blur-[120px] pointer-events-none -z-10" />
      <div className="fixed bottom-[-10%] right-[-5%] w-[45vw] h-[45vw] rounded-full bg-indigo-200/20 blur-[130px] pointer-events-none -z-10" />

      {/* Top Navbar */}
      <header className="border-b border-slate-200/70 bg-white/75 backdrop-blur-xl sticky top-0 z-30 shadow-2xs">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          
          {/* Logo & App Brand */}
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-teal-600 to-teal-700 text-white flex items-center justify-center font-bold text-sm shadow-xs shadow-teal-700/20">
              ⚡
            </div>
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-sm sm:text-base tracking-tight text-slate-900">
                NL-to-SQL Assistant
              </span>
              <span className="hidden sm:inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold bg-teal-50 text-teal-800 border border-teal-200/60">
                AI Query Engine
              </span>
            </div>
          </div>

          {/* Right Header Navigation & Help Trigger */}
          <div className="flex items-center gap-2">
            {screen === 'chat' && session && (
              <span className="hidden md:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                Active Session
              </span>
            )}

            {/* Persistent Help / Guide Button */}
            <button
              onClick={() => setIsHelpOpen(true)}
              className="p-1.5 sm:px-3 sm:py-1.5 rounded-xl bg-white hover:bg-teal-50/80 border border-slate-200/90 hover:border-teal-300 text-slate-700 hover:text-teal-800 transition-all text-xs font-semibold flex items-center gap-1.5 shadow-2xs group"
              title="Open User Guide & Help"
            >
              <span className="w-5 h-5 rounded-full bg-slate-100 group-hover:bg-teal-600 text-slate-600 group-hover:text-white flex items-center justify-center font-bold text-xs transition-colors">
                ?
              </span>
              <span className="hidden sm:inline">Guide</span>
            </button>
          </div>

        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 flex items-center justify-center py-4 sm:py-6">
        {isRestoringSession ? (
          <div className="flex flex-col items-center gap-3 text-slate-500">
            <svg className="animate-spin w-6 h-6 text-teal-600" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span className="text-xs font-medium">Restoring your workspace...</span>
          </div>
        ) : screen === 'connect' ? (
          <ConnectDBScreen onConnected={handleConnected} initialNotice={sessionExpiredNotice} />
        ) : (
          <ChatWindow session={session} onDisconnect={handleDisconnect} />
        )}
      </main>

      {/* Global Help / Orientation Drawer (Left Slide-in) */}
      <HelpSidebar
        isOpen={isHelpOpen}
        onClose={() => setIsHelpOpen(false)}
      />

    </div>
  );
}
