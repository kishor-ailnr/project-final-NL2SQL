import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { generateLearnSqlContent } from '../utils/learnSqlGenerator';

export default function LearnSQLModal({ isOpen, onClose, data }) {
  const [copied, setCopied] = useState(false);

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

  if (!data) return null;

  const {
    sql = '',
    explanation = '',
    queryData = null,
    rawContent = '',
    content = '',
    originalQuestion = '',
    result = [],
    rows_affected = null,
    error = null,
    isPendingWrite = false,
    notice = null,
  } = data;

  // Resolve user question from multiple fallback avenues
  const effectiveQuestion =
    originalQuestion ||
    queryData?.user_question ||
    queryData?.raw_content ||
    queryData?.interpreted_text ||
    rawContent ||
    '';

  const effectiveSql = sql || queryData?.sql || '';
  const effectiveResult = result.length > 0 ? result : (queryData?.result || []);
  const effectiveRowsAffected =
    rows_affected !== null
      ? rows_affected
      : queryData?.rows_affected !== undefined
      ? queryData.rows_affected
      : null;
  const effectiveError = error || queryData?.error || null;
  const effectiveNotice = notice || queryData?.notice || null;
  const effectiveLanguage = queryData?.detected_language || 'english';

  const learning = generateLearnSqlContent({
    question: effectiveQuestion,
    sql: effectiveSql,
    explanation: explanation || queryData?.explanation,
    result: effectiveResult,
    rows_affected: effectiveRowsAffected,
    error: effectiveError,
    isPendingWrite: isPendingWrite || queryData?.query_type === 'write',
    notice: effectiveNotice,
    detectedLanguage: effectiveLanguage,
  });

  const handleCopy = () => {
    if (effectiveSql) {
      navigator.clipboard.writeText(effectiveSql);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Syntax highlighter helper for SQL keywords
  const renderHighlightedSql = (code) => {
    if (!code) return null;
    const keywords = [
      'SELECT', 'INSERT', 'INTO', 'VALUES', 'UPDATE', 'SET', 'DELETE',
      'FROM', 'WHERE', 'JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN',
      'ON', 'GROUP BY', 'HAVING', 'ORDER BY', 'LIMIT', 'ASC', 'DESC',
      'AND', 'OR', 'NOT', 'NULL', 'IS', 'IN', 'LIKE', 'AS', 'COUNT',
      'SUM', 'AVG', 'MAX', 'MIN'
    ];
    const regex = new RegExp(`\\b(${keywords.join('|')})\\b`, 'gi');

    return code.split('\n').map((line, lIdx) => {
      const parts = line.split(regex);
      return (
        <div key={lIdx} className="leading-relaxed">
          {parts.map((part, pIdx) => {
            const upper = part.toUpperCase();
            if (keywords.includes(upper)) {
              return (
                <span key={pIdx} className="text-amber-400 font-bold">
                  {part}
                </span>
              );
            }
            if (/^'[^']*'$/.test(part) || /^"[^"]*"$/.test(part)) {
              return (
                <span key={pIdx} className="text-emerald-300">
                  {part}
                </span>
              );
            }
            if (/^\d+(\.\d+)?$/.test(part.trim())) {
              return (
                <span key={pIdx} className="text-sky-300">
                  {part}
                </span>
              );
            }
            return <span key={pIdx}>{part}</span>;
          })}
        </div>
      );
    });
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div
          onClick={handleBackdropClick}
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-50 flex items-center justify-center p-3 sm:p-5"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 14 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 14 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="bg-white rounded-2xl shadow-2xl border border-slate-200/90 max-w-3xl w-full max-h-[88vh] flex flex-col text-slate-900 overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-slate-100 bg-slate-50/70 shrink-0">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200/70 text-indigo-700 flex items-center justify-center shrink-0 shadow-2xs">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
                      Learn SQL
                    </h2>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-100/80 text-indigo-800 border border-indigo-200">
                      {learning.lang === 'tamil' ? 'தமிழ்' : learning.lang === 'tanglish' ? 'Tanglish' : 'English'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 font-normal truncate mt-0.5">
                    Understand how your question became SQL
                  </p>
                </div>
              </div>

              {/* Close Button */}
              <button
                type="button"
                onClick={onClose}
                className="w-8 h-8 rounded-xl flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
                title="Close (Esc)"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Scrollable Educational Content */}
            <div className="flex-1 overflow-y-auto px-5 sm:px-6 py-5 space-y-6 text-sm text-slate-700">
              
              {/* SECTION 1 — YOUR QUESTION */}
              <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">
                  <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-[10px]">
                    1
                  </span>
                  <span>{learning.section1.title}</span>
                </div>
                <p className="text-sm sm:text-base font-medium text-slate-900 bg-white border border-slate-200/90 rounded-lg p-3 shadow-2xs italic">
                  "{learning.section1.content}"
                </p>
              </div>

              {/* SECTION 2 — HOW THE QUESTION WAS UNDERSTOOD */}
              <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-2xs">
                <div className="flex items-center gap-2 mb-2.5 text-xs font-bold uppercase tracking-wider text-indigo-700">
                  <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-800 flex items-center justify-center text-[10px]">
                    2
                  </span>
                  <span>{learning.section2.title}</span>
                </div>
                <p className="text-xs sm:text-sm text-slate-800 mb-3 leading-relaxed">
                  {learning.section2.summary}
                </p>

                {learning.section2.mappings.length > 0 && (
                  <div className="bg-slate-50 rounded-lg p-3 border border-slate-200/70 mb-2">
                    <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
                      Extracted Entities & Mapped Columns:
                    </span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {learning.section2.mappings.map((m, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between px-2.5 py-1.5 bg-white border border-slate-200 rounded-md text-xs"
                        >
                          <span className="font-medium text-slate-700">{m.label}:</span>
                          <span className="font-mono text-indigo-700 font-semibold bg-indigo-50 px-1.5 py-0.5 rounded">
                            {m.value}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <p className="text-[11px] sm:text-xs text-slate-500 mt-2 italic">
                  {learning.section2.mappingNote}
                </p>
              </div>

              {/* SECTION 3 — GENERATED SQL */}
              <div className="bg-slate-900 text-slate-100 rounded-xl p-4 border border-slate-800 shadow-md">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-amber-400">
                    <span className="w-5 h-5 rounded-full bg-amber-400/20 text-amber-300 flex items-center justify-center text-[10px]">
                      3
                    </span>
                    <span>{learning.section3.title}</span>
                  </div>

                  <button
                    type="button"
                    onClick={handleCopy}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-all"
                    title="Copy SQL"
                  >
                    {copied ? (
                      <>
                        <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                        </svg>
                        <span className="text-emerald-400">Copied!</span>
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        <span>Copy SQL</span>
                      </>
                    )}
                  </button>
                </div>

                <div className="bg-slate-950/80 p-3.5 rounded-lg font-mono text-xs overflow-x-auto border border-slate-800">
                  {renderHighlightedSql(learning.section3.sql)}
                </div>
              </div>

              {/* SECTION 4 — SQL COMMAND EXPLANATION */}
              <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-2xs space-y-3.5">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-teal-800">
                  <span className="w-5 h-5 rounded-full bg-teal-100 text-teal-800 flex items-center justify-center text-[10px]">
                    4
                  </span>
                  <span>{learning.section4.title}</span>
                </div>

                <div className="p-3 bg-teal-50/70 border border-teal-200/80 rounded-lg">
                  <h4 className="text-xs font-bold text-teal-900 mb-1">
                    What is {learning.section4.command}?
                  </h4>
                  <p className="text-xs sm:text-sm text-teal-950 leading-relaxed mb-2">
                    {learning.section4.whatIs}
                  </p>
                  <h4 className="text-xs font-bold text-teal-900 mb-1">
                    Why was {learning.section4.command} used here?
                  </h4>
                  <p className="text-xs sm:text-sm text-teal-950 leading-relaxed">
                    {learning.section4.whyUsed}
                  </p>
                </div>

                {/* Piece by piece breakdown */}
                <div>
                  <span className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-2">
                    Piece-by-Piece Query Breakdown:
                  </span>
                  <div className="space-y-2">
                    {learning.section4.pieces.map((piece, idx) => (
                      <div
                        key={idx}
                        className="flex flex-col sm:flex-row sm:items-start gap-1 sm:gap-3 p-2.5 rounded-lg bg-slate-50 border border-slate-200/80 text-xs"
                      >
                        <span className="font-mono font-semibold text-indigo-700 bg-white px-2 py-0.5 rounded border border-slate-200 shrink-0">
                          {piece.part}
                        </span>
                        <span className="text-slate-700 sm:pt-0.5 leading-relaxed">
                          → {piece.meaning}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* SECTION 5 — QUESTION → SQL CONVERSION (Visual Flow) */}
              <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-2xs">
                <div className="flex items-center gap-2 mb-3 text-xs font-bold uppercase tracking-wider text-violet-800">
                  <span className="w-5 h-5 rounded-full bg-violet-100 text-violet-800 flex items-center justify-center text-[10px]">
                    5
                  </span>
                  <span>{learning.section5.title}</span>
                </div>

                <div className="relative pl-6 space-y-3.5 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                  {learning.section5.steps.map((s, idx) => (
                    <div key={idx} className="relative group">
                      <div className="absolute -left-6 top-1 w-3.5 h-3.5 rounded-full bg-white border-2 border-violet-500 ring-4 ring-white" />
                      <div className="bg-slate-50 hover:bg-slate-100/80 transition-colors p-2.5 rounded-lg border border-slate-200/70 text-xs">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="font-bold text-slate-800">
                            {s.step}. {s.name}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-violet-50 text-violet-700 border border-violet-200">
                            {s.badge}
                          </span>
                        </div>
                        <p className="text-slate-600 font-mono text-[11px] break-words">
                          {s.detail}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* SECTION 6 — WHAT HAPPENED WHEN SQL WAS EXECUTED? */}
              <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-2xs">
                <div className="flex items-center gap-2 mb-2.5 text-xs font-bold uppercase tracking-wider text-slate-700">
                  <span className="w-5 h-5 rounded-full bg-slate-100 text-slate-800 flex items-center justify-center text-[10px]">
                    6
                  </span>
                  <span>{learning.section6.title}</span>
                </div>

                <div
                  className={`p-3 rounded-lg border text-xs sm:text-sm leading-relaxed ${
                    learning.section6.statusType === 'error'
                      ? 'bg-rose-50 border-rose-200 text-rose-900'
                      : learning.section6.statusType === 'warning'
                      ? 'bg-amber-50 border-amber-200 text-amber-900'
                      : learning.section6.statusType === 'pending'
                      ? 'bg-sky-50 border-sky-200 text-sky-900'
                      : 'bg-emerald-50 border-emerald-200 text-emerald-900'
                  }`}
                >
                  <p className="font-bold mb-1">{learning.section6.headline}</p>
                  <p className="whitespace-pre-line text-xs">{learning.section6.details}</p>
                </div>
              </div>

              {/* SECTION 7 — FINAL RESULT */}
              <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-1.5 text-xs font-bold uppercase tracking-wider text-slate-600">
                  <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-[10px]">
                    7
                  </span>
                  <span>{learning.section7.title}</span>
                </div>
                <p className="text-xs sm:text-sm font-semibold text-slate-800 bg-white border border-slate-200 rounded-lg p-3">
                  {learning.section7.result}
                </p>
              </div>

              {/* SECTION 8 — COMPLETE LEARNING SUMMARY */}
              <div className="bg-gradient-to-br from-indigo-50/60 to-purple-50/60 border border-indigo-200/80 rounded-xl p-4 space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-indigo-900">
                  <span className="w-5 h-5 rounded-full bg-indigo-200 text-indigo-900 flex items-center justify-center text-[10px]">
                    8
                  </span>
                  <span>{learning.section8.title}</span>
                </div>

                {/* Linear summary flow */}
                <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-slate-700 bg-white/80 p-2.5 rounded-lg border border-indigo-100">
                  <span>Question</span>
                  <span>→</span>
                  <span className="text-indigo-700 font-semibold">AI/NLP Understanding</span>
                  <span>→</span>
                  <span>Schema Mapping</span>
                  <span>→</span>
                  <span className="text-teal-700 font-semibold">SQL Generation</span>
                  <span>→</span>
                  <span>Validation</span>
                  <span>→</span>
                  <span className="text-amber-700 font-semibold">Database Execution</span>
                  <span>→</span>
                  <span className="text-emerald-700 font-bold">Result Shown</span>
                </div>

                {/* What you learned bullet points */}
                <div className="bg-white p-3.5 rounded-lg border border-indigo-100 shadow-2xs">
                  <h4 className="text-xs font-bold text-indigo-950 mb-2">
                    {learning.section8.learnedTitle}
                  </h4>
                  <ul className="space-y-1.5 text-xs text-slate-700">
                    {learning.section8.learnedPoints.map((pt, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <span className="text-indigo-600 font-bold shrink-0">•</span>
                        <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

            </div>

            {/* Modal Footer */}
            <div className="px-5 sm:px-6 py-3 border-t border-slate-100 bg-slate-50/70 flex items-center justify-end shrink-0">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs sm:text-sm font-semibold text-slate-700 hover:text-slate-900 bg-white hover:bg-slate-100 border border-slate-200 rounded-xl transition-all shadow-2xs"
              >
                Close
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
