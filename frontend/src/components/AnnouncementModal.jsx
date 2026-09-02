import React, { useEffect, useState } from 'react';

/**
 * AnnouncementModal — Login qilinganda ochiladigan modal.
 * localStorage'da saqlanadi: yangi bildirishnoma qo'shilsa yoki tahrirlansa yana ko'rsatiladi.
 */
const AnnouncementModal = ({ announcements }) => {
  const [visible, setVisible] = useState(false);
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (!announcements || announcements.length === 0) return;
    
    try {
      const seen = JSON.parse(localStorage.getItem('seen_announcements_modal') || '{}');
      let hasUnseen = false;
      for (const ann of announcements) {
        const annTs = ann.updated_at || ann.created_at;
        if (seen[ann.id] !== annTs) {
          hasUnseen = true;
          break;
        }
      }
      if (hasUnseen) {
        setVisible(true);
      }
    } catch {
      setVisible(true);
    }
  }, [announcements]);

  if (!visible || !announcements || announcements.length === 0) return null;

  const ann = announcements[current];

  const handleClose = () => {
    try {
      const seen = JSON.parse(localStorage.getItem('seen_announcements_modal') || '{}');
      for (const a of announcements) {
        seen[a.id] = a.updated_at || a.created_at;
      }
      localStorage.setItem('seen_announcements_modal', JSON.stringify(seen));
    } catch (e) {
      console.error(e);
    }
    setVisible(false);
  };

  return (
    <div style={styles.overlay}>
      <style>
        {`
          @keyframes swing-bell {
            0% { transform: rotate(0); }
            10% { transform: rotate(15deg); }
            20% { transform: rotate(-10deg); }
            30% { transform: rotate(5deg); }
            40% { transform: rotate(-5deg); }
            50% { transform: rotate(0); }
            100% { transform: rotate(0); }
          }
          .animated-bell {
            animation: swing-bell 2.5s ease-in-out infinite;
            transform-origin: top center;
          }
          @keyframes pulse-bg {
            0% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(255, 255, 255, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0); }
          }
          .premium-icon-bg {
            animation: pulse-bg 2s infinite;
          }
        `}
      </style>
      <div style={styles.modal}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <div className="premium-icon-bg" style={styles.iconWrapper}>
              <svg className="animated-bell" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ffffff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>
                <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>
              </svg>
            </div>
            <span style={styles.headerTitle}>Yangi xabarnoma</span>
          </div>
          <button style={styles.closeBtn} onClick={handleClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>

        {/* Kontent */}
        <div style={styles.body}>
          <h3 style={styles.title}>{ann.title}</h3>
          <p style={styles.message}>{ann.message}</p>
          {ann.expires_at && (
            <p style={styles.expires}>
              ⏳ Amal qilish muddati: <span style={{fontWeight: 600}}>{new Date(ann.expires_at).toLocaleDateString('uz-UZ', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
            </p>
          )}
        </div>

        {/* Ko'p xabar bo'lsa navigatsiya */}
        {announcements.length > 1 && (
          <div style={styles.nav}>
            <span style={styles.navInfo}>{current + 1} / {announcements.length}</span>
            <div style={styles.navBtns}>
              <button
                style={{ ...styles.navBtn, opacity: current === 0 ? 0.3 : 1 }}
                onClick={() => setCurrent(p => Math.max(0, p - 1))}
                disabled={current === 0}
              >‹</button>
              <button
                style={{ ...styles.navBtn, opacity: current === announcements.length - 1 ? 0.3 : 1 }}
                onClick={() => setCurrent(p => Math.min(announcements.length - 1, p + 1))}
                disabled={current === announcements.length - 1}
              >›</button>
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={styles.footer}>
          <button style={styles.okBtn} onClick={handleClose}>
            Tushundim
          </button>
        </div>
      </div>
    </div>
  );
};

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(15, 23, 42, 0.65)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 99999,
    backdropFilter: 'blur(6px)',
  },
  modal: {
    background: '#ffffff',
    borderRadius: '24px',
    width: '92%',
    maxWidth: '540px',
    maxHeight: '90vh', // Prevent it from being taller than the screen
    boxShadow: '0 25px 80px rgba(0,0,0,0.4)',
    overflow: 'hidden',
    animation: 'slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
    display: 'flex',
    flexDirection: 'column',
  },
  header: {
    background: 'linear-gradient(90deg, #1e3a8a 0%, #3b82f6 100%)',
    padding: '24px 28px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0, // Keep header fixed
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  iconWrapper: {
    background: 'rgba(255, 255, 255, 0.15)',
    padding: '8px',
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
  },
  headerTitle: {
    color: '#ffffff',
    fontWeight: 800,
    fontSize: '20px',
    letterSpacing: '0.5px',
    textShadow: '0 1px 2px rgba(0,0,0,0.2)',
  },
  closeBtn: {
    background: 'rgba(255, 255, 255, 0.2)',
    border: 'none',
    color: '#ffffff',
    width: '38px',
    height: '38px',
    borderRadius: '50%',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s ease',
  },
  body: {
    padding: '32px 32px 24px',
    overflowY: 'auto', // Allow scrolling
    flex: 1,           // Take up available space
  },
  title: {
    margin: '0 0 16px',
    fontSize: '24px',
    fontWeight: 800,
    color: '#0f172a',
    lineHeight: 1.3,
  },
  message: {
    margin: 0,
    fontSize: '17px',
    lineHeight: 1.6,
    color: '#334155',
    whiteSpace: 'pre-wrap',
  },
  expires: {
    marginTop: '20px',
    padding: '12px 16px',
    background: '#f8fafc',
    borderRadius: '12px',
    border: '1px solid #e2e8f0',
    fontSize: '14px',
    color: '#64748b',
    display: 'inline-block',
  },
  nav: {
    padding: '0 32px 16px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  },
  navInfo: {
    fontSize: '15px',
    fontWeight: 600,
    color: '#64748b',
  },
  navBtns: {
    display: 'flex',
    gap: '8px',
  },
  navBtn: {
    background: '#f1f5f9',
    border: 'none',
    borderRadius: '10px',
    width: '40px',
    height: '40px',
    cursor: 'pointer',
    fontSize: '24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#3b82f6',
    fontWeight: 700,
    transition: 'all 0.2s ease',
  },
  footer: {
    padding: '16px 32px 32px',
    display: 'flex',
    justifyContent: 'flex-end',
    flexShrink: 0, // Keep footer fixed
  },

  okBtn: {
    background: 'linear-gradient(90deg, #2563eb, #1d4ed8)',
    color: '#ffffff',
    border: 'none',
    borderRadius: '14px',
    padding: '14px 40px',
    fontSize: '16px',
    fontWeight: 700,
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxShadow: '0 10px 25px -5px rgba(37, 99, 235, 0.4)',
  },
};

export default AnnouncementModal;

