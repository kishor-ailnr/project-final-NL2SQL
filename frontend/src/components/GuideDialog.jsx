import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from './lightswind/dialog';

export const GUIDE_STEPS = [
  {
    step: '1',
    title: 'Connect Your Data',
    icon: '🔌',
    desc: 'Pick a preloaded demo (Hospital or E-commerce), paste a database URL, or upload a .csv / .sql file to get started.',
  },
  {
    step: '2',
    title: 'Ask in English, Tamil, or Thanglish',
    icon: '💬',
    desc: 'Type questions naturally or use voice input — e.g. "list all patients older than 40" or "40 vayasuku mela irukra patients ellam kaatu".',
  },
  {
    step: '3',
    title: 'Smart Visualizations',
    icon: '📊',
    desc: 'Review structured results in formatted tables or toggle to interactive bar and line charts for aggregations.',
  },
  {
    step: '4',
    title: 'Inspect Behind the Scenes',
    icon: '🔍',
    desc: 'Click "</> View SQL" on any answer to reveal the exact query, execution explanation, and confidence score.',
  },
  {
    step: '5',
    title: 'Safe Write Confirmations',
    icon: '🛡️',
    desc: 'Any data changes (INSERT, UPDATE, DELETE) trigger a mandatory confirmation dialog before executing.',
  },
  {
    step: '6',
    title: 'Session Query History',
    icon: '⏱️',
    desc: 'Open the History drawer anytime to revisit, inspect, or re-run prior questions from your active session.',
  },
];

export default function GuideDialog({ children, open, onOpenChange }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {children && <DialogTrigger asChild>{children}</DialogTrigger>}
      <DialogContent className="max-w-2xl bg-white/95 backdrop-blur-xl border border-slate-200/90 shadow-2xl p-6 rounded-3xl">
        <DialogHeader className="border-b border-slate-100 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-teal-600 to-teal-700 text-white flex items-center justify-center font-bold text-base shadow-sm shadow-teal-700/20">
              ⚡
            </div>
            <div>
              <DialogTitle className="text-base sm:text-lg font-bold text-slate-900 tracking-tight flex items-center gap-2">
                <span>User Guide & Instructions</span>
                <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200/70">
                  Orientation
                </span>
              </DialogTitle>
              <DialogDescription className="text-xs text-slate-500 mt-0.5">
                Learn how to query, explore, and visualize your database in 6 simple steps.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* 6 Step Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 py-4 max-h-[58vh] overflow-y-auto pr-1">
          {GUIDE_STEPS.map((item) => (
            <div
              key={item.step}
              className="p-3.5 rounded-2xl bg-slate-50/80 hover:bg-teal-50/40 border border-slate-200/70 hover:border-teal-200 transition-all flex items-start gap-3 group"
            >
              <span className="w-8 h-8 rounded-xl bg-white border border-slate-200/80 flex items-center justify-center text-sm shrink-0 shadow-2xs group-hover:scale-105 transition-transform">
                {item.icon}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-slate-200/70 text-slate-700">
                    STEP {item.step}
                  </span>
                  <h4 className="text-xs font-bold text-slate-800 tracking-tight truncate">
                    {item.title}
                  </h4>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {item.desc}
                </p>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between w-full pt-3 border-t border-slate-100">
          <div className="text-[11px] text-slate-400 font-medium hidden sm:block">
            Press <kbd className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[10px]">Esc</kbd> or click outside to dismiss
          </div>
          <DialogClose asChild>
            <button
              type="button"
              className="w-full sm:w-auto px-5 py-2 rounded-xl bg-teal-600 hover:bg-teal-700 active:scale-95 text-white text-xs font-semibold shadow-sm transition-all"
            >
              Got it, let's explore!
            </button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
