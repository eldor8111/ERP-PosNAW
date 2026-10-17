// Sahifa huquqlari (user.permissions — tekis {kalit: bool}) yordamchilari.

// Route nomi va huquq kaliti mos kelmagan joylar: /admin/ombor sahifasini ham 'ombor',
// ham eski 'warehouse' (Omborxona) huquqi yopadi.
export const PERMISSION_ALIASES = { ombor: ['ombor', 'warehouse'] };

// Sahifaga (route segmenti, masalan 'ombor') kirish mumkinmi. `false` aniq belgilangan bo'lsagina yopiladi;
// super_admin yoki permissions bo'sh bo'lsa — ruxsat (undefined = ruxsat).
export function isPageAllowed(user, key) {
  if (!user) return false;
  if (user.role === 'super_admin') return true;
  const perms = user.permissions;
  if (!perms || Object.keys(perms).length === 0) return true;
  return (PERMISSION_ALIASES[key] || [key]).every(k => perms[k] !== false);
}
