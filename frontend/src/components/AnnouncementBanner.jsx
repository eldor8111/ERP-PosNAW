import React, { useState } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';

/**
 * AnnouncementBanner — Header'da doimiy ko'k banner.
 * "X" bosilsa localStorage'da saqlanadi va yana ko'rinmaydi.
 * Shuningdek, so'rovnoma (survey) bo'lsa uni ko'rsatadi.
 */
const AnnouncementBanner = ({ announcements }) => {
  // localStorage da dismiss qilingan ID lar
  const getDismissed = () => {
    try {
      return JSON.parse(localStorage.getItem('dismissed_announcements') || '[]');
    } catch {
      return [];
    }
  };

  const [dismissed, setDismissed] = useState(getDismissed);
  const [expandedId, setExpandedId] = useState(null);
  const [surveyAnn, setSurveyAnn] = useState(null);

  if (!announcements || announcements.length === 0) return null;

  // Agar so'rovnomaga allaqachon javob bergan bo'lsa, va dismiss qilinmagan bo'lsa ko'rsatamiz.
  // Lekin bizga API dan "has_answered" keladi.
  const visible = announcements.filter(a => !dismissed.includes(a.id));
  if (visible.length === 0) return null;

  const dismiss = (id) => {
    const updated = [...dismissed, id];
    setDismissed(updated);
    localStorage.setItem('dismissed_announcements', JSON.stringify(updated));
    if (expandedId === id) setExpandedId(null);
  };

  return (
    <>
      <div style={styles.container}>
        <style>
          {`
            @keyframes swing-bell-banner {
              0% { transform: rotate(0); }
              10% { transform: rotate(15deg); }
              20% { transform: rotate(-10deg); }
              30% { transform: rotate(5deg); }
              40% { transform: rotate(-5deg); }
              50% { transform: rotate(0); }
              100% { transform: rotate(0); }
            }
            .animated-bell-banner {
              animation: swing-bell-banner 2.5s ease-in-out infinite;
              transform-origin: top center;
            }
            @keyframes pulse-bg-banner {
              0% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.35); }
              70% { box-shadow: 0 0 0 8px rgba(255, 255, 255, 0); }
              100% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0); }
            }
            .premium-icon-bg-banner {
              animation: pulse-bg-banner 2s infinite;
            }
          `}
        </style>
        {visible.map(ann => (
          <div key={ann.id} style={styles.banner}>
            <div style={styles.left}>
              <div className="premium-icon-bg-banner" style={styles.iconWrapper}>
                <svg className="animated-bell-banner" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
                  <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
                </svg>
              </div>
              <div style={styles.textWrap}>
                <span style={styles.title}>{ann.title}</span>
                {expandedId === ann.id ? (
                  <span style={styles.message}>{ann.message}</span>
                ) : (
                  <span style={styles.preview}>
                    {ann.message.length > 100 ? ann.message.slice(0, 100) + '...' : ann.message}
                  </span>
                )}
              </div>
            </div>
            <div style={styles.actions}>
              {ann.has_survey && !ann.has_answered && (
                <button
                  style={styles.surveyBtn}
                  onClick={() => setSurveyAnn(ann)}
                >
                  📝 So'rovnoma
                </button>
              )}
              {ann.message.length > 100 && (
                <button
                  style={styles.readMore}
                  onClick={() => setExpandedId(expandedId === ann.id ? null : ann.id)}
                >
                  {expandedId === ann.id ? 'Yig\'ish' : "Ko'proq"}
                </button>
              )}
              <button style={styles.closeBtn} onClick={() => dismiss(ann.id)} title="Yopish">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
              </button>
            </div>
          </div>
        ))}
      </div>

      {surveyAnn && (
        <SurveyModal ann={surveyAnn} onClose={() => setSurveyAnn(null)} onComplete={() => dismiss(surveyAnn.id)} />
      )}
    </>
  );
};

const SurveyModal = ({ ann, onClose, onComplete }) => {
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    // Validate that all required questions are answered
    for (const q of ann.questions) {
      const ans = answers[q.id];
      if (!ans || (Array.isArray(ans) && ans.length === 0)) {
        return toast.error("Iltimos, barcha savollarga javob bering");
      }
    }

    setSubmitting(true);
    try {
      await api.post(`/super-admin/announcements/active/${ann.id}/submit-survey`, { answers });
      toast.success("Javobingiz qabul qilindi. Rahmat!");
      onComplete();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Xatolik yuz berdi");
    } finally {
      setSubmitting(false);
    }
  };

  const setAnswer = (qId, val) => {
    setAnswers(prev => ({ ...prev, [qId]: val }));
  };

  const toggleMultiple = (qId, option) => {
    const current = answers[qId] || [];
    if (current.includes(option)) {
      setAnswer(qId, current.filter(x => x !== option));
    } else {
      setAnswer(qId, [...current, option]);
    }
  };

  return (
    <div className="fixed inset-0 z-[2000] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-5 shrink-0 relative">
          <button onClick={onClose} className="absolute top-4 right-4 text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-full w-8 h-8 flex items-center justify-center transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-white/20 backdrop-blur rounded-2xl flex items-center justify-center shadow-inner">
              <span className="text-2xl">📝</span>
            </div>
            <div>
              <h3 className="font-black text-xl text-white tracking-wide">So'rovnoma</h3>
              <p className="text-blue-100 text-sm mt-0.5">{ann.title}</p>
            </div>
          </div>
        </div>

        <div className="p-6 overflow-y-auto bg-slate-50 flex-1">
          <p className="text-sm text-slate-500 mb-6 bg-blue-50/50 p-4 rounded-xl border border-blue-100">
            Fikringiz biz uchun muhim. Iltimos, quyidagi savollarga javob bering.
          </p>

          <div className="space-y-6">
            {ann.questions?.map((q, idx) => (
              <div key={q.id} className="bg-white p-5 rounded-2xl shadow-sm border border-slate-100">
                <h4 className="font-bold text-slate-800 text-base mb-4 flex gap-2">
                  <span className="text-blue-600">{idx + 1}.</span> {q.text}
                </h4>

                {q.question_type === 'text' && (
                  <textarea
                    value={answers[q.id] || ''}
                    onChange={e => setAnswer(q.id, e.target.value)}
                    className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-slate-50 min-h-[100px]"
                    placeholder="Javobingizni bu yerga yozing..."
                  />
                )}

                {q.question_type === 'single_choice' && (
                  <div className="space-y-2">
                    {q.options?.map((opt, i) => (
                      <label key={i} className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${answers[q.id] === opt ? 'border-blue-500 bg-blue-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                        <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${answers[q.id] === opt ? 'border-blue-600' : 'border-slate-300'}`}>
                          {answers[q.id] === opt && <div className="w-2.5 h-2.5 bg-blue-600 rounded-full" />}
                        </div>
                        <input
                          type="radio"
                          name={`q_${q.id}`}
                          value={opt}
                          checked={answers[q.id] === opt}
                          onChange={() => setAnswer(q.id, opt)}
                          className="hidden"
                        />
                        <span className={`text-sm ${answers[q.id] === opt ? 'font-bold text-blue-900' : 'text-slate-700'}`}>{opt}</span>
                      </label>
                    ))}
                  </div>
                )}

                {q.question_type === 'multiple_choice' && (
                  <div className="space-y-2">
                    {q.options?.map((opt, i) => {
                      const isChecked = (answers[q.id] || []).includes(opt);
                      return (
                        <label key={i} className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${isChecked ? 'border-blue-500 bg-blue-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                          <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center flex-shrink-0 ${isChecked ? 'border-blue-600 bg-blue-600' : 'border-slate-300'}`}>
                            {isChecked && <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                          </div>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => toggleMultiple(q.id, opt)}
                            className="hidden"
                          />
                          <span className={`text-sm ${isChecked ? 'font-bold text-blue-900' : 'text-slate-700'}`}>{opt}</span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="p-5 border-t border-slate-100 flex gap-3 shrink-0 bg-white">
          <button onClick={onClose} className="flex-1 py-3 text-sm font-bold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors">
            Keyinroq
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="flex-1 py-3 text-sm font-bold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow-lg shadow-blue-200 disabled:opacity-60 transition-all flex justify-center items-center gap-2"
          >
            {submitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"/>
                Yuborilmoqda...
              </>
            ) : (
              <>
                Yuborish
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

const styles = {
  container: {
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    zIndex: 1000,
  },
  banner: {
    background: 'linear-gradient(90deg, #1e3a8a 0%, #2563eb 50%, #1e3a8a 100%)',
    color: '#fff',
    padding: '16px 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '16px',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  },
  left: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '16px',
    flex: 1,
  },
  iconWrapper: {
    background: 'rgba(255, 255, 255, 0.15)',
    padding: '6px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
    marginTop: '2px',
    flexShrink: 0,
  },
  textWrap: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    paddingTop: '2px',
  },
  title: {
    fontWeight: 800,
    fontSize: '17px',
    letterSpacing: '0.3px',
    textShadow: '0 1px 2px rgba(0,0,0,0.2)',
  },
  preview: {
    opacity: 0.95,
    fontSize: '15px',
    fontWeight: 500,
    lineHeight: '1.4',
  },
  message: {
    opacity: 0.95,
    fontSize: '15px',
    fontWeight: 500,
    lineHeight: '1.5',
    whiteSpace: 'pre-wrap',
  },
  actions: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    flexShrink: 0,
    marginLeft: '16px',
  },
  surveyBtn: {
    background: '#ffffff',
    color: '#1e3a8a',
    border: 'none',
    borderRadius: '8px',
    padding: '6px 14px',
    fontSize: '14px',
    cursor: 'pointer',
    fontWeight: 800,
    whiteSpace: 'nowrap',
    transition: 'all 0.2s ease',
    boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
  },
  readMore: {
    background: 'rgba(255, 255, 255, 0.15)',
    border: '1px solid rgba(255,255,255,0.3)',
    color: '#fff',
    borderRadius: '8px',
    padding: '6px 16px',
    fontSize: '14px',
    cursor: 'pointer',
    fontWeight: 700,
    whiteSpace: 'nowrap',
    transition: 'all 0.2s ease',
    backdropFilter: 'blur(4px)',
  },
  closeBtn: {
    background: 'rgba(255, 255, 255, 0.15)',
    border: 'none',
    color: '#fff',
    width: '36px',
    height: '36px',
    borderRadius: '50%',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s ease',
  },
};

export default AnnouncementBanner;

