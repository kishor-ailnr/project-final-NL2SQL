import { motion } from 'framer-motion';
import logoImg from '../assets/logo.png';

export default function SQLPreviewPanel({ queryData = {}, onViewSQL }) {
  const {
    explanation = '',
    confidence = 0,
    query_type = 'select',
    needs_clarification = false,
    clarification_question = '',
  } = queryData;

  // If clarification is required, render the clarification box
  if (needs_clarification) {
    return (
      <div className="w-full my-2 p-4 rounded-2xl bg-amber-50/80 border border-amber-200/80 text-amber-900 text-sm shadow-xs flex items-start gap-3">
        <span className="text-xl shrink-0 mt-0.5" role="img" aria-label="clarification">❓</span>
        <div className="space-y-1">
          <h4 className="font-semibold text-xs uppercase tracking-wider text-amber-800">
            Clarification Required
          </h4>
          <p className="text-sm leading-relaxed text-amber-950">
            {clarification_question || 'Could you please clarify your question?'}
          </p>
        </div>
      </div>
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
      className="w-full my-2 bg-white/80 backdrop-blur-md border border-slate-200/70 rounded-2xl p-4 shadow-sm"
    >
      {/* Top Meta Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5 pb-2.5 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <img
            src={logoImg}
            alt="NL2SQL"
            className="w-5 h-5 object-contain shrink-0"
          />
          <span className="text-xs font-semibold text-slate-700">
            Assistant Analysis
          </span>

          {isWriteQuery && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-900 border border-amber-300">
              Write Operation (Pending)
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Confidence Badge */}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${badgeColorClass}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${badgeDotClass}`}></span>
            {confPercent}% confident
          </span>

          {/* View SQL Drawer Trigger Button */}
          {onViewSQL && (
            <button
              type="button"
              onClick={() => onViewSQL(queryData)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-teal-50 hover:bg-teal-100/80 border border-teal-200/70 text-teal-800 text-xs font-semibold transition-all shadow-2xs group"
              title="Inspect generated SQL in sidebar"
            >
              <svg className="w-3.5 h-3.5 text-teal-600 font-bold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              <span>View SQL</span>
            </button>
          )}
        </div>
      </div>

      {/* Explanation text */}
      {explanation ? (
        <p className="text-xs sm:text-sm text-slate-700 leading-relaxed">
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
