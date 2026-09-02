import React, { useState } from 'react';

/**
 * AnnouncementBanner — Header'da doimiy ko'k banner.
 * "X" bosilsa localStorage'da saqlanadi va yana ko'rinmaydi.
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

  if (!announcements || announcements.length === 0) return null;

  const visible = announcements.filter(a => !dismissed.includes(a.id));
  if (visible.length === 0) return null;

  const dismiss = (id) => {
    const updated = [...dismissed, id];
    setDismissed(updated);
    localStorage.setItem('dismissed_announcements', JSON.stringify(updated));
    if (expandedId === id) setExpandedId(null);
  };

  return (
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

