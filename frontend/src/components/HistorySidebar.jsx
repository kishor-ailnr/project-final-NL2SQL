import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

function formatRelativeTime(dateStr) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr.replace(' ', 'T'));
    if (isNaN(date.getTime())) return dateStr;
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);

    if (diffSec < 60) return 'Just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHour = Math.floor(diffMin / 60);
    if (diffHour < 24) return `${diffHour}h ago`;
    const diffDays = Math.floor(diffHour / 24);
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return dateStr;
  }
}

export default function HistorySidebar({
  isOpen,
  onClose,
  conversations = [],
  activeConversationId,
  loading = false,
  error = null,
  onRefresh,
  onNewChat,
  onSelectConversation,
}) {
  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Mobile and tablet backdrop overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            className="fixed inset-0 bg-slate-900/25 backdrop-blur-xs z-40 transition-opacity"
          />

          {/* Sidebar Drawer */}
          <motion.aside
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
            className="fixed top-0 bottom-0 left-0 z-40 w-72 sm:w-80 bg-white/95 backdrop-blur-xl border-r border-slate-200/80 shadow-2xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="p-4 border-b border-slate-200/70 flex items-center justify-between bg-slate-50/70">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <h3 className="font-bold text-sm text-slate-800 tracking-tight">
                  Chat History
                </h3>
              </div>

              <div className="flex items-center gap-1">
                {onRefresh && (
                  <button
                    type="button"
                    onClick={onRefresh}
                    title="Refresh conversations"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                  >
                    <svg className={`w-4 h-4 ${loading ? 'animate-spin text-teal-600' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                  </button>
                )}

                <button
                  type="button"
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
                  title="Close History"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* "+ New Chat" Action Button */}
            <div className="p-3 border-b border-slate-100 bg-white">
              <button
                type="button"
                onClick={() => {
                  if (onNewChat) onNewChat();
                  if (onClose) onClose();
                }}
                className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl bg-gradient-to-r from-teal-600 to-teal-700 hover:from-teal-700 hover:to-teal-800 text-white text-xs sm:text-sm font-semibold shadow-sm shadow-teal-700/20 hover:shadow-teal-700/30 transition-all active:scale-[0.98]"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
                </svg>
                <span>+ New Chat</span>
              </button>
            </div>

            {/* Conversations List */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {error && (
                <div className="p-2.5 mb-2 rounded-xl bg-amber-50 border border-amber-200 text-[11px] text-amber-800 flex items-center justify-between gap-2">
                  <span>{error}</span>
                  {onRefresh && (
                    <button
                      onClick={onRefresh}
                      className="underline font-semibold shrink-0 hover:text-amber-950"
                    >
                      Retry
                    </button>
                  )}
                </div>
              )}

              {loading ? (
                <div className="p-6 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                  <svg className="animate-spin w-4 h-4 text-teal-600" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Loading chats...</span>
                </div>
              ) : conversations.length === 0 ? (
                <div className="p-6 text-center text-xs text-slate-400">
                  No conversations yet. Start a new chat above!
                </div>
              ) : (
                conversations.map((item) => {
                  const isActive = item.conversation_id === activeConversationId;
                  return (
                    <button
                      key={item.conversation_id}
                      onClick={() => {
                        if (onSelectConversation) onSelectConversation(item.conversation_id);
                        if (onClose) onClose();
                      }}
                      className={`w-full text-left p-3 rounded-xl transition-all group shadow-2xs border ${
                        isActive
                          ? 'bg-teal-50/90 border-teal-400/90 text-teal-950 shadow-xs ring-1 ring-teal-400/30'
                          : 'bg-white/70 hover:bg-teal-50/40 border-slate-200/70 hover:border-teal-200/80 text-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-1.5">
                        <p className={`text-xs sm:text-sm font-medium line-clamp-1 ${
                          isActive ? 'text-teal-900 font-semibold' : 'text-slate-800 group-hover:text-teal-900'
                        }`}>
                          {item.title || 'New Chat'}
                        </p>
                        {isActive && (
                          <span className="w-2 h-2 rounded-full bg-teal-600 shrink-0" title="Active conversation" />
                        )}
                      </div>
                      <span className="text-[10px] text-slate-400 mt-1 block">
                        {formatRelativeTime(item.created_at)}
                      </span>
                    </button>
                  );
                })
              )}
            </div>

            {/* Sidebar Footer */}
            <div className="p-3 border-t border-slate-200/70 bg-slate-50/70 text-center">
              <p className="text-[11px] text-slate-500">
                Click any chat to switch conversations
              </p>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
