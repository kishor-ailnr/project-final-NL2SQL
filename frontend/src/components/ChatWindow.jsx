import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import MessageBubble from './MessageBubble';
import VoiceButton from './VoiceButton';
import SQLPreviewPanel from './SQLPreviewPanel';
import ChartPanel from './ChartPanel';
import ConfirmModal from './ConfirmModal';
import HistorySidebar from './HistorySidebar';
import SQLDrawer from './SQLDrawer';
import {
  sendQuery,
  confirmWrite,
  createConversation,
  getConversations,
  getConversationMessages,
  deleteConversation,
} from '../api/client';

const INITIAL_WELCOME = {
  id: 'init-1',
  role: 'assistant',
  content: 'Hello! I am your NL-to-SQL Assistant. Ask me a question about your database in natural language (e.g., "Show all patients older than 40" or "List top 5 products by revenue").',
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
};

export default function ChatWindow({ session, onDisconnect }) {
  const sessionId = session?.session_id || 'N/A';
  const tables = session?.tables || [];

  const [messages, setMessages] = useState([INITIAL_WELCOME]);
  const [inputValue, setInputValue] = useState('');
  const [isPending, setIsPending] = useState(false);
  const [showTables, setShowTables] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  // Multi-conversation state
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [conversationsError, setConversationsError] = useState(null);

  // SQL Drawer state (right-side slide-in)
  const [activeSQLQuery, setActiveSQLQuery] = useState(null);
  const [isSQLDrawerOpen, setIsSQLDrawerOpen] = useState(false);

  // Confirm Modal state for Write operations
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [pendingWriteQuery, setPendingWriteQuery] = useState(null);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isPending]);

  // Load conversations on session mount
  const fetchConversations = async (autoSelect = false) => {
    if (!sessionId || sessionId === 'N/A') return;
    setConversationsLoading(true);
    setConversationsError(null);
    try {
      const data = await getConversations(sessionId);
      const convList = data?.conversations || [];
      setConversations(convList);

      if (autoSelect) {
        if (convList.length > 0) {
          handleSelectConversation(convList[0].conversation_id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.warn('Failed to fetch conversations:', err.message);
      setConversationsError('Could not load chat history.');
    } finally {
      setConversationsLoading(false);
    }
  };

  useEffect(() => {
    fetchConversations(true);
  }, [sessionId]);

  // Handler for creating a fresh conversation
  const handleNewChat = async () => {
    if (!sessionId || sessionId === 'N/A') return;
    try {
      const res = await createConversation(sessionId);
      if (res?.conversation_id) {
        setActiveConversationId(res.conversation_id);
        setMessages([
          {
            ...INITIAL_WELCOME,
            id: `init-${Date.now()}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setConversations((prev) => [
          {
            conversation_id: res.conversation_id,
            title: 'New Chat',
            created_at: res.created_at,
          },
          ...prev.filter((c) => c.conversation_id !== res.conversation_id),
        ]);
      }
    } catch (err) {
      console.warn('Failed to create new conversation:', err.message);
    }
  };

  // Handler for switching to an existing conversation
  const handleSelectConversation = async (convId) => {
    if (!convId) return;
    setActiveConversationId(convId);
    try {
      const data = await getConversationMessages(convId);
      const msgList = data?.messages || [];

      if (msgList.length === 0) {
        setMessages([
          {
            ...INITIAL_WELCOME,
            id: `init-${Date.now()}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        return;
      }

      const formatted = [];
      msgList.forEach((m, idx) => {
        // User question message
        formatted.push({
          id: `user-${convId}-${idx}`,
          role: 'user',
          content: m.nl_query,
          raw_content: m.nl_query,
          interpreted_text: null,
          timestamp: m.timestamp,
        });

        // Assistant query response message
        const isClarif = !m.sql && m.explanation;
        formatted.push({
          id: `asst-${convId}-${idx}`,
          role: 'assistant',
          queryData: {
            query_id: `msg-${convId}-${idx}`,
            sql: m.sql,
            explanation: m.explanation,
            result: m.result || [],
            chart_type: m.chart_type || 'none',
            confidence: isClarif ? 0.3 : 1.0,
            needs_clarification: isClarif,
            clarification_question: isClarif ? m.explanation : null,
          },
          timestamp: m.timestamp,
        });
      });

      setMessages(formatted);
    } catch (err) {
      console.warn('Failed to load conversation messages:', err.message);
    }
  };

  // Handler for deleting a conversation
  const handleDeleteConversation = async (convId) => {
    if (!convId) return;
    try {
      await deleteConversation(convId);
      // Immediately remove from sidebar list
      setConversations((prev) => prev.filter((c) => c.conversation_id !== convId));

      // If the deleted conversation was the active one, reset to clean new-chat state
      if (convId === activeConversationId) {
        setActiveConversationId(null);
        setMessages([
          {
            ...INITIAL_WELCOME,
            id: `init-${Date.now()}`,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setInputValue('');
      }
    } catch (err) {
      console.warn('Failed to delete conversation:', err.message);
    }
  };

  const handleOpenSQL = (queryData) => {
    setActiveSQLQuery(queryData);
    setIsSQLDrawerOpen(true);
  };

  const handleSend = async (e) => {
    if (e) e.preventDefault();
    const text = inputValue.trim();
    if (!text || isPending) return;

    let targetConvId = activeConversationId;
    if (!targetConvId) {
      try {
        const newConv = await createConversation(sessionId);
        targetConvId = newConv.conversation_id;
        setActiveConversationId(targetConvId);
      } catch (convErr) {
        console.warn('Failed to initialize conversation before send:', convErr);
      }
    }

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsgId = `user-${Date.now()}`;
    const userMessage = {
      id: userMsgId,
      role: 'user',
      content: text,
      raw_content: text,
      interpreted_text: null,
      timestamp: timeStr,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsPending(true);

    try {
      const queryResponse = await sendQuery({
        session_id: sessionId,
        conversation_id: targetConvId,
        text,
        language: 'auto',
      });

      // Update matching user message with interpreted_text if returned
      if (queryResponse?.interpreted_text) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === userMsgId
              ? { ...msg, interpreted_text: queryResponse.interpreted_text }
              : msg
          )
        );
      }

      const assistantMessage = {
        id: `asst-${Date.now()}`,
        role: 'assistant',
        queryData: queryResponse,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      if (queryResponse.query_type === 'write') {
        setPendingWriteQuery(queryResponse);
        setIsModalOpen(true);
      }

      // Refresh conversations list to show updated title
      fetchConversations(false);
    } catch (err) {
      console.warn('sendQuery API error:', err.message);
      const errorMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `❌ ${err.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsPending(false);
    }
  };

  const handleConfirmWrite = async () => {
    try {
      const res = await confirmWrite({
        session_id: sessionId,
        query_id: pendingWriteQuery?.query_id,
        confirmed: true,
      });

      setIsModalOpen(false);
      const executionMessage = {
        id: `exec-${Date.now()}`,
        role: 'assistant',
        content: `✅ Executed — ${res?.rows_affected ?? 0} rows affected.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, executionMessage]);
      setPendingWriteQuery(null);
    } catch (err) {
      console.warn('confirmWrite API error:', err.message);
      setIsModalOpen(false);
      const errorMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: `❌ Write Execution Failed: ${err.message}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setPendingWriteQuery(null);
    }
  };

  const handleCancelWrite = async () => {
    if (pendingWriteQuery?.query_id) {
      try {
        await confirmWrite({
          session_id: sessionId,
          query_id: pendingWriteQuery.query_id,
          confirmed: false,
        });
      } catch (err) {
        console.warn('cancel confirmWrite notification failed:', err.message);
      }
    }

    setIsModalOpen(false);
    const cancelMessage = {
      id: `cancel-${Date.now()}`,
      role: 'assistant',
      content: 'Query cancelled. No changes were made to the database.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, cancelMessage]);
    setPendingWriteQuery(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleVoiceComplete = (transcript) => {
    if (!transcript) return;
    setInputValue(transcript);
  };

  return (
    <div className="w-full max-w-6xl mx-auto p-2 sm:p-4 flex gap-4 h-[calc(100vh-4.5rem)]">
      
      {/* History Drawer Component (Left Slide-in) */}
      <HistorySidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        conversations={conversations}
        activeConversationId={activeConversationId}
        loading={conversationsLoading}
        error={conversationsError}
        onRefresh={() => fetchConversations(false)}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      {/* SQL Drawer Component (Right Slide-in) */}
      <SQLDrawer
        queryData={activeSQLQuery}
        isOpen={isSQLDrawerOpen}
        onClose={() => setIsSQLDrawerOpen(false)}
      />

      {/* Main Glassmorphic Chat Workspace */}
      <div className="flex-1 bg-white/75 backdrop-blur-xl rounded-3xl shadow-xl shadow-slate-200/50 border border-white/80 flex flex-col h-full overflow-hidden transition-all duration-200">
        
        {/* Header Bar */}
        <div className="p-3.5 sm:p-4 border-b border-slate-200/70 bg-white/60 backdrop-blur-md shrink-0">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
              {/* History Toggle Button */}
              <button
                type="button"
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                className="px-2.5 py-1.5 rounded-xl bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all hover:border-teal-300"
                title="Toggle Chat History"
              >
                <svg className="w-4 h-4 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <span className="hidden sm:inline">Chats</span>
                {conversations.length > 0 && (
                  <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-600 font-mono">
                    {conversations.length}
                  </span>
                )}
              </button>

              {/* + New Chat Quick Button */}
              <button
                type="button"
                onClick={handleNewChat}
                className="px-2.5 py-1.5 rounded-xl bg-teal-50 hover:bg-teal-100 text-teal-700 border border-teal-200/80 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-all hover:border-teal-300 active:scale-95"
                title="Start a new chat"
              >
                <svg className="w-3.5 h-3.5 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
                </svg>
                <span>New Chat</span>
              </button>

              {/* Status Badge */}
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  Connected
                </span>
                <span className="text-xs text-slate-400 font-mono hidden md:inline truncate max-w-[140px]" title={sessionId}>
                  {sessionId}
                </span>
              </div>

              {/* Toggleable Table List Pills */}
              <button
                type="button"
                onClick={() => setShowTables(!showTables)}
                className="text-xs font-medium text-teal-700 hover:text-teal-900 flex items-center gap-1 bg-teal-50/60 px-2.5 py-1 rounded-lg border border-teal-200/60 transition-colors"
              >
                <span>{tables.length} tables</span>
                <svg className={`w-3.5 h-3.5 transition-transform ${showTables ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            {/* Disconnect Button */}
            <button
              onClick={onDisconnect}
              className="self-end sm:self-auto px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-rose-700 bg-white hover:bg-rose-50 border border-slate-200 hover:border-rose-200 rounded-xl transition-all flex items-center gap-1.5 shadow-2xs"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
              <span>Disconnect</span>
            </button>
          </div>

          {/* Tables Bar Drawer */}
          {showTables && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap gap-1.5"
            >
              {tables.map((table, idx) => (
                <span
                  key={idx}
                  className="px-2.5 py-1 rounded-lg text-[11px] font-mono bg-white text-slate-700 border border-slate-200 shadow-2xs"
                >
                  {table}
                </span>
              ))}
            </motion.div>
          )}
        </div>

        {/* Scrollable Message List */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-3">
          {messages.map((msg) => {
            if (msg.role === 'user') {
              return (
                <MessageBubble
                  key={msg.id}
                  role="user"
                  content={msg.content}
                  rawContent={msg.raw_content || msg.content}
                  interpretedText={msg.interpreted_text}
                  timestamp={msg.timestamp}
                />
              );
            }

            if (msg.queryData) {
              const isWrite = msg.queryData.query_type === 'write';
              return (
                <motion.div
                  key={msg.id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex w-full my-3 justify-start"
                >
                  <div className="max-w-[98%] sm:max-w-[90%] md:max-w-[85%] flex flex-col items-start w-full">
                    
                    {/* Explanation Card (SQL hidden by default, revealable via View SQL) */}
                    <SQLPreviewPanel
                      queryData={msg.queryData}
                      onViewSQL={handleOpenSQL}
                    />

                    {/* Table / Chart Result Display */}
                    {!msg.queryData.needs_clarification && !isWrite && (
                      <ChartPanel
                        result={msg.queryData.result}
                        chart_type={msg.queryData.chart_type}
                      />
                    )}

                    {msg.timestamp && (
                      <span className="text-[10px] text-slate-400 mt-1 px-1">
                        {msg.timestamp}
                      </span>
                    )}
                  </div>
                </motion.div>
              );
            }

            return (
              <MessageBubble
                key={msg.id}
                role="assistant"
                content={msg.content}
                timestamp={msg.timestamp}
              />
            );
          })}

          {/* Animated Typing Indicator */}
          {isPending && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex w-full my-2.5 justify-start"
            >
              <div className="bg-white/80 backdrop-blur-md text-slate-600 px-4 py-3 rounded-2xl rounded-bl-xs border border-slate-200/70 flex items-center gap-2.5 shadow-2xs">
                <div className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-teal-600 animate-bounce"></span>
                  <span className="w-2 h-2 rounded-full bg-teal-500 animate-bounce [animation-delay:0.2s]"></span>
                  <span className="w-2 h-2 rounded-full bg-teal-400 animate-bounce [animation-delay:0.4s]"></span>
                </div>
                <span className="text-xs font-medium text-slate-600 ml-1">
                  Assistant analyzing & generating query...
                </span>
              </div>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Bottom Bar Controls & Input */}
        <div className="p-3 sm:p-4 border-t border-slate-200/70 bg-white/60 backdrop-blur-md shrink-0">
          <form onSubmit={handleSend} className="flex items-center gap-2">
            
            {/* Text Input */}
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your database in natural language..."
              disabled={isPending}
              className="flex-1 px-4 py-2.5 sm:py-3 rounded-2xl border border-slate-200/90 bg-white/90 text-slate-900 placeholder-slate-400 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 shadow-2xs transition-all disabled:opacity-60"
            />

            {/* Voice Input Button */}
            <VoiceButton
              onTranscript={handleVoiceComplete}
              onRecordingComplete={handleVoiceComplete}
              disabled={isPending}
            />

            {/* Send Button */}
            <button
              type="submit"
              disabled={!inputValue.trim() || isPending}
              className="py-2.5 px-4 sm:py-3 sm:px-5 bg-gradient-to-r from-teal-600 to-teal-700 hover:from-teal-700 hover:to-teal-800 text-white font-semibold text-sm rounded-2xl shadow-sm shadow-teal-600/20 transition-all flex items-center justify-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              <span className="hidden sm:inline">Send</span>
              <svg className="w-4 h-4 rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>

          </form>
        </div>

      </div>

      {/* Confirm Modal Overlay for Write Operations */}
      <ConfirmModal
        isOpen={isModalOpen}
        sql={pendingWriteQuery?.sql}
        explanation={pendingWriteQuery?.explanation}
        onConfirm={handleConfirmWrite}
        onCancel={handleCancelWrite}
      />
    </div>
  );
}
