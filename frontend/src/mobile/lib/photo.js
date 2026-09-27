import { Capacitor } from '@capacitor/core';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';

/** Kameradan rasm (ilovada) yoki fayl tanlash (brauzerda) — Blob qaytaradi, bekor qilinsa null */
export async function takePhoto() {
  if (Capacitor.isNativePlatform()) {
    try {
      const p = await Camera.getPhoto({
        source: CameraSource.Camera, resultType: CameraResultType.Uri,
        quality: 60, width: 1600, correctOrientation: true, saveToGallery: false,
      });
      const res = await fetch(p.webPath);
      return await res.blob();
    } catch {
      return null; // foydalanuvchi bekor qildi yoki ruxsat yo'q
    }
  }
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'environment';
    input.onchange = () => resolve(input.files?.[0] || null);
    input.click();
  });
}
