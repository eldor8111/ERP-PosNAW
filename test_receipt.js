const sale = {
  before_debt_balances: '{"UZS": 140000, "USD": 10}',
  debt_amounts: { USD: 316.34 }
};

const oldDebtsList = [];
let rawBefore = sale.before_debt_balances;
if (typeof rawBefore === 'string') { try { rawBefore = JSON.parse(rawBefore); } catch(e) { rawBefore = null; } }

if (rawBefore && Object.keys(rawBefore).length > 0) {
  for (const [curr, amt] of Object.entries(rawBefore)) {
    const a = Number(amt || 0);
    if (Math.abs(a) > 0.01) {
      oldDebtsList.push({ currency: curr, amount: a });
    }
  }
} else if (Number(sale.before_debt || 0) > 0.01) {
  oldDebtsList.push({ currency: 'UZS', amount: Number(sale.before_debt) });
}

console.log("oldDebtsList:", oldDebtsList);

const currentDebtsList = [];
let rawCurrent = sale.debt_amounts;
if (typeof rawCurrent === 'string') { try { rawCurrent = JSON.parse(rawCurrent); } catch(e) { rawCurrent = null; } }

if (rawCurrent && Object.keys(rawCurrent).length > 0) {
  for (const [curr, amt] of Object.entries(rawCurrent)) {
    const a = Number(amt || 0);
    if (Math.abs(a) > 0.001) {
      currentDebtsList.push({ currency: curr, amount: a });
    }
  }
}

console.log("currentDebtsList:", currentDebtsList);
