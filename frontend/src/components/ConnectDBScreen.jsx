import { useState, useRef } from 'react';
import { motion } from 'framer-motion';
import { connectDB, uploadDB } from '../api/client';

export default function ConnectDBScreen({ onConnected, initialNotice }) {
  const [dbType, setDbType] = useState('postgres');
  const [connectionString, setConnectionString] = useState('postgresql://user:password@localhost:5432/hospital_db');
  const [loadingAction, setLoadingAction] = useState(null); // 'hospital' | 'ecommerce' | 'custom' | 'upload' | null
  const [error, setError] = useState(null);

  // File upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  const handleDemoClick = async (demoType) => {
    setError(null);
    setLoadingAction(demoType);

    try {
      const response = await connectDB({
        db_type: 'demo',
        connection_string: '',
        demo_name: demoType,
      });
      setLoadingAction(null);
      onConnected(response);
    } catch (err) {
      setLoadingAction(null);
      setError(err.message || 'Failed to connect to demo database.');
    }
  };

  const handleCustomConnect = async (e) => {
    e.preventDefault();
    setError(null);

    if (!connectionString.trim()) {
      setError('Connection string cannot be empty. Please provide a valid database URL.');
      return;
    }

    setLoadingAction('custom');
    try {
      const response = await connectDB({
        db_type: dbType,
        connection_string: connectionString.trim(),
        demo_name: null,
      });
      setLoadingAction(null);
      onConnected(response);
    } catch (err) {
      setLoadingAction(null);
      setError(err.message || 'Failed to connect to database.');
    }
  };

  const handleFileChange = (e) => {
    setError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    const lower = file.name.toLowerCase();
    if (!lower.endsWith('.csv') && !lower.endsWith('.sql')) {
      setError('Unsupported file type. Please select a .csv or .sql file.');
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
  };

  const handleUploadSubmit = async () => {
    if (!selectedFile) {
      setError('Please select a .csv or .sql file first.');
      return;
    }

    setError(null);
    setLoadingAction('upload');

    try {
      const response = await uploadDB(selectedFile);
      setLoadingAction(null);
      onConnected(response);
    } catch (err) {
      setLoadingAction(null);
      setError(err.message || "This file couldn't be read as a valid CSV/SQLite file.");
    }
  };

  return (
    <div className="w-full max-w-xl mx-auto p-4 sm:p-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="bg-white/80 backdrop-blur-xl rounded-3xl shadow-xl shadow-slate-200/50 border border-white/80 p-6 sm:p-8 space-y-6"
      >
        {/* Header */}
        <div className="text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-teal-500 to-teal-700 text-white mb-3 shadow-md shadow-teal-600/20">
            <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
            </svg>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-800 tracking-tight">
            NL-to-SQL Assistant
          </h1>
          <p className="mt-1.5 text-xs sm:text-sm text-slate-500 max-w-md mx-auto">
            Explore with preloaded demo datasets, upload a custom file, or connect your database.
          </p>
        </div>

        {/* Notice banner for expired sessions */}
        {initialNotice && (
          <div className="p-3.5 rounded-2xl bg-amber-50 border border-amber-200/90 text-amber-800 text-xs sm:text-sm flex items-center gap-2.5 shadow-2xs">
            <svg className="w-5 h-5 shrink-0 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span className="font-medium">{initialNotice}</span>
          </div>
        )}

        {/* Error State Banner */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            className="p-3.5 rounded-2xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start justify-between gap-3 text-xs sm:text-sm shadow-xs"
          >
            <div className="flex items-start gap-2.5">
              <svg className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <strong className="font-semibold block text-rose-900">Connection Error</strong>
                <span className="block mt-0.5 leading-relaxed">{error}</span>
              </div>
            </div>
            <button
              onClick={() => setError(null)}
              className="text-rose-400 hover:text-rose-700 text-base font-bold px-1"
              title="Dismiss error"
            >
              &times;
            </button>
          </motion.div>
        )}

        {/* SECTION 1: PRELOADED DEMO DATASETS */}
        <div className="space-y-2">
          <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Option 1: Quick Explore (Demo Datasets)
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => handleDemoClick('hospital')}
              disabled={!!loadingAction}
              className="py-3 px-4 bg-white/70 hover:bg-teal-50/80 border border-slate-200/80 hover:border-teal-300 rounded-2xl text-slate-800 text-sm font-medium transition-all flex items-center justify-center gap-2.5 shadow-2xs hover:shadow-sm disabled:opacity-50 disabled:cursor-not-allowed group"
            >
              {loadingAction === 'hospital' ? (
                <>
                  <svg className="animate-spin w-4 h-4 text-teal-600" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Loading Hospital Demo...</span>
                </>
              ) : (
                <>
                  <span className="text-xl">🏥</span>
                  <div className="text-left">
                    <span className="block font-semibold text-xs sm:text-sm text-slate-800 group-hover:text-teal-800">
                      Hospital Records
                    </span>
                    <span className="block text-[10px] text-slate-400">
                      Patients, doctors & appointments
                    </span>
                  </div>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => handleDemoClick('ecommerce')}
              disabled={!!loadingAction}
              className="py-3 px-4 bg-white/70 hover:bg-teal-50/80 border border-slate-200/80 hover:border-teal-300 rounded-2xl text-slate-800 text-sm font-medium transition-all flex items-center justify-center gap-2.5 shadow-2xs hover:shadow-sm disabled:opacity-50 disabled:cursor-not-allowed group"
            >
              {loadingAction === 'ecommerce' ? (
                <>
                  <svg className="animate-spin w-4 h-4 text-teal-600" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Loading Store Demo...</span>
                </>
              ) : (
                <>
                  <span className="text-xl">🛒</span>
                  <div className="text-left">
                    <span className="block font-semibold text-xs sm:text-sm text-slate-800 group-hover:text-teal-800">
                      E-commerce Store
                    </span>
                    <span className="block text-[10px] text-slate-400">
                      Orders, products & customers
                    </span>
                  </div>
                </>
              )}
            </button>
          </div>
        </div>

        {/* SECTION 2: FILE UPLOAD (MVP) */}
        <div className="space-y-2 pt-2 border-t border-slate-100">
          <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Option 2: Upload a File (.csv or .sql)
          </label>
          <div className="p-4 rounded-2xl bg-white/70 border border-slate-200/80 space-y-3">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".csv,.sql"
              className="hidden"
            />

            {!selectedFile ? (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-300 hover:border-teal-500 rounded-xl p-4 text-center cursor-pointer transition-colors bg-slate-50/50 hover:bg-teal-50/30 group"
              >
                <div className="w-9 h-9 mx-auto mb-1.5 rounded-full bg-slate-100 group-hover:bg-teal-100/70 text-slate-500 group-hover:text-teal-700 flex items-center justify-center transition-colors">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <p className="text-xs font-semibold text-slate-700 group-hover:text-teal-800">
                  Click to browse or drop your .csv or .sql file
                </p>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Accepts CSV spreadsheets or SQLite schema dumps
                </p>
              </div>
            ) : (
              <div className="flex items-center justify-between p-3 rounded-xl bg-teal-50/70 border border-teal-200/80">
                <div className="flex items-center gap-2.5 overflow-hidden">
                  <span className="text-lg">📄</span>
                  <div className="truncate">
                    <p className="text-xs font-semibold text-teal-900 truncate">
                      {selectedFile.name}
                    </p>
                    <p className="text-[10px] text-teal-600 font-mono">
                      {(selectedFile.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedFile(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                    className="p-1 text-slate-400 hover:text-slate-600 text-xs"
                    title="Remove file"
                  >
                    Remove
                  </button>

                  <button
                    type="button"
                    onClick={handleUploadSubmit}
                    disabled={!!loadingAction}
                    className="py-1.5 px-3 bg-teal-600 hover:bg-teal-700 text-white font-medium text-xs rounded-lg shadow-2xs transition-all flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {loadingAction === 'upload' ? (
                      <>
                        <svg className="animate-spin w-3 h-3 text-white" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span>Processing...</span>
                      </>
                    ) : (
                      'Process & Connect'
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* SECTION 3: DIRECT CONNECTION STRING */}
        <form onSubmit={handleCustomConnect} className="space-y-3 pt-2 border-t border-slate-100">
          <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Option 3: Direct Database Connection
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <div className="sm:col-span-1">
              <select
                value={dbType}
                onChange={(e) => setDbType(e.target.value)}
                disabled={!!loadingAction}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white/90 text-slate-800 text-xs focus:outline-none focus:ring-2 focus:ring-teal-500"
              >
                <option value="postgres">PostgreSQL</option>
                <option value="sqlite">SQLite</option>
              </select>
            </div>

            <div className="sm:col-span-2">
              <input
                type="text"
                value={connectionString}
                onChange={(e) => setConnectionString(e.target.value)}
                disabled={!!loadingAction}
                placeholder={dbType === 'postgres' ? 'postgresql://user:pass@localhost:5432/db' : 'sqlite:///path/to/db.db'}
                className="w-full px-3 py-2 rounded-xl border border-slate-200 bg-white/90 text-slate-800 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-teal-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!!loadingAction}
            className="w-full py-2.5 px-4 bg-slate-800 hover:bg-slate-900 text-white font-medium text-xs sm:text-sm rounded-xl shadow-sm transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loadingAction === 'custom' ? (
              <>
                <svg className="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>Connecting...</span>
              </>
            ) : (
              'Connect via Connection String'
            )}
          </button>
        </form>

      </motion.div>
    </div>
  );
}
