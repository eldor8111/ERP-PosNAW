// xlsx (~420KB) va file-saver'ni faqat kerak bo'lganda (eksport/import
// tugmasi bosilganda) yuklaydi — statik import bo'lsa, bu og'ir kutubxona
// sahifa ochilishi bilanoq bundle'ga qo'shilib, hech kim ishlatmasa ham
// yuklab olinardi.

let xlsxPromise = null
export function loadXLSX() {
  if (!xlsxPromise) xlsxPromise = import('xlsx')
  return xlsxPromise
}

let saveAsPromise = null
export function loadSaveAs() {
  if (!saveAsPromise) saveAsPromise = import('file-saver').then(m => m.saveAs)
  return saveAsPromise
}
