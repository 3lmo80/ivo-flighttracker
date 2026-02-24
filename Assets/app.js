async function loadJSON(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  return r.json();
}

function hexColor(i){
  const palette = [
    '#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd',
    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'
  ];
  return palette[i % palette.length];
}

(async () => {
  // Snel: toon “generated_at” uit sample_data.json
  try {
    const sample = await loadJSON('data/sample_data.json');
    if (sample?.generated_at) {
      document.getElementById('generatedAt').textContent =
        `Geüpdatet: ${new Date(sample.generated_at).toLocaleString()}`;
    }
  } catch {}

  const monthly = await loadJSON('data/monthly_lowest.json');
  // monthly: { "AMS-BCN": { "2026-02-01": {price: 89, currency:"EUR"}, ... }, ... }
  const routeKeys = Object.keys(monthly).sort();

  // Maak x-as als unie van alle datums:
  const allDates = new Set();
  routeKeys.forEach(rk => Object.keys(monthly[rk]).forEach(d => allDates.add(d)));
  const labels = Array.from(allDates).sort(); // ISO datums

  const datasets = routeKeys.map((rk, i) => {
    const map = monthly[rk];
    const data = labels.map(d => map[d]?.price ?? null);
    return {
      label: rk,
      data,
      borderColor: hexColor(i),
      backgroundColor: 'transparent',
      spanGaps: true,
      tension: 0.25
    };
  });

  const ctx = document.getElementById('chart');
  new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label(ctx) {
              const v = ctx.parsed.y;
              return (v == null) ? '—' : `€ ${v}`;
            }
          }
        }
      },
      scales: {
        x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } },
        y: { title: { display: true, text: 'Prijs (EUR)' } }
      }
    }
  });
})();
