// Server PDF/blob javoblari uchun yordamchilar.

/** Content-Disposition'dan fayl nomini oladi (RFC 5987 `filename*` va oddiy `filename`). */
export function filenameFromDisposition(cd, fallback) {
  if (!cd) return fallback
  const star = cd.match(/filename\*\s*=\s*UTF-8''([^;]+)/i)
  if (star && star[1]) {
    try { return decodeURIComponent(star[1].trim()) } catch { /* oddiy nomga o'tamiz */ }
  }
  const plain = cd.match(/filename\s*=\s*"?([^";]+)"?/i)
  return (plain && plain[1]) ? plain[1].trim() : fallback
}

/** responseType:'blob' bilan kelgan xato javobidan server xabarini (detail) o'qiydi. */
export async function blobErrorMessage(err) {
  try {
    const data = err?.response?.data
    if (data instanceof Blob) {
      const text = await data.text()
      try {
        const j = JSON.parse(text)
        const d = j?.detail
        return typeof d === 'string' ? d : (d?.message || JSON.stringify(d || j))
      } catch { return text.slice(0, 200) }
    }
    return err?.response?.data?.detail || err?.message || 'Noma\'lum xatolik'
  } catch {
    return err?.message || 'Noma\'lum xatolik'
  }
}
