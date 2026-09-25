import { motion } from 'framer-motion';
import logoImg from '../assets/logo.png';

export default function SQLPreviewPanel({ queryData = {}, onViewSQL }) {
  const {
    explanation = '',
    confidence = 0,
    query_type = 'select',
    needs_clarification = false,
    clarification_question = '',
    data_available = true,
    unavailable_message = '',
  } = queryData;

  // If data is unavailable in database schema, render calm informational message
  if (data_available === false) {
    const unavailText =
      unavailable_message ||
      explanation ||
      'This information is not tracked in the connected database schema.';

    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="w-full my-2 bg-gradient-to-br from-sky-50/95 via-blue-50/70 to-slate-50/90 border border-sky-200/80 rounded-2xl p-3.5 sm:p-4 shadow-2xs text-slate-800 backdrop-blur-xs"
      >
        <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-sky-200/50">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-5 h-5 rounded-full bg-sky-200/80 text-sky-800 flex items-center justify-center text-xs font-bold shrink-0">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </span>
            <span className="font-semibold text-xs text-sky-950 uppercase tracking-wider">
              Information
            </span>
          </div>
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-sky-100 text-sky-800 border border-sky-200 shrink-0">
            Data Unavailable in Schema
          </span>
        </div>
        <p className="text-xs sm:text-sm text-slate-700 leading-relaxed font-normal">
          {unavailText}
        </p>
      </motion.div>
    );
  }

  // If clarification is required, render the clarification box
  if (needs_clarification) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="w-full my-2 bg-amber-50/90 border border-amber-200/90 rounded-2xl p-3.5 sm:p-4 shadow-2xs text-amber-950"
      >
        <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-amber-200/60">
          <div className="flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-amber-200/80 text-amber-900 flex items-center justify-center text-xs font-bold shrink-0">
              ?
            </span>
            <span className="font-bold text-xs uppercase tracking-wider text-amber-900">
              Clarification Required
            </span>
          </div>
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-200/60 text-amber-800">
            Ambiguous Query
          </span>
        </div>
        <p className="text-xs sm:text-sm leading-relaxed text-amber-900">
          {clarification_question || 'Could you please clarify your question?'}
        </p>
      </motion.div>
    );
  }

  // Calculate confidence badge threshold
  const confVal = typeof confidence === 'number' ? confidence : 1.0;
  const confPercent = Math.round(confVal * 100);

  let badgeColorClass = 'bg-emerald-50 text-emerald-800 border-emerald-200/80';
  let badgeDotClass = 'bg-emerald-500';

  if (confVal < 0.5) {
    badgeColorClass = 'bg-rose-50 text-rose-800 border-rose-200/80';
    badgeDotClass = 'bg-rose-500';
  } else if (confVal <= 0.8) {
    badgeColorClass = 'bg-amber-50 text-amber-800 border-amber-200/80';
    badgeDotClass = 'bg-amber-500';
  }

  const isWriteQuery = query_type === 'write';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2 }}
      className="w-full my-2 bg-white/95 border border-slate-200/80 rounded-2xl p-3.5 sm:p-4 shadow-2xs hover:border-slate-300 transition-colors"
    >
      {/* Top Meta Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pb-2.5 border-b border-slate-100">
        <div className="flex items-center gap-2 min-w-0">
          <img
            src={logoImg}
            alt="NL2SQL"
            className="w-4 h-4 sm:w-5 sm:h-5 object-contain shrink-0"
          />
          <span className="text-xs font-semibold text-slate-800 truncate">
            Assistant Analysis
          </span>

          {isWriteQuery && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-900 border border-amber-300 shrink-0">
              Write Operation (Pending)
            </span>
          )}
        </div>

        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          {/* Confidence Badge */}
          <span className={`inline-flex items-center gap-1.5 px-2 sm:px-2.5 py-0.5 rounded-full text-[11px] sm:text-xs font-medium border ${badgeColorClass}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${badgeDotClass}`}></span>
            {confPercent}% confident
          </span>

          {/* View SQL Drawer Trigger Button */}
          {onViewSQL && (
            <button
              type="button"
              onClick={() => onViewSQL(queryData)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-teal-50 hover:bg-teal-100/80 border border-teal-200/70 text-teal-800 text-xs font-semibold transition-all shadow-2xs group min-h-[30px]"
              title="Inspect generated SQL in sidebar"
            >
              <svg className="w-3.5 h-3.5 text-teal-600 font-bold shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              <span>View SQL</span>
            </button>
          )}
        </div>
      </div>

      {/* Explanation text */}
      {explanation ? (
        <p className="text-xs sm:text-sm text-slate-700 leading-relaxed font-normal">
          {explanation}
        </p>
      ) : (
        <p className="text-xs sm:text-sm text-slate-500 italic">
          Query executed successfully.
        </p>
      )}
    </motion.div>
  );
}
