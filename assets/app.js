// Countries and cities (IATA)
const COUNTRY_CITIES = {
  'Portugal': [ { city: 'Porto', iata: 'OPO' }, { city: 'Lissabon', iata: 'LIS' } ],
  'Kroatië':  [ { city: 'Zagreb', iata: 'ZAG' }, { city: 'Split', iata: 'SPU' } ],
  'Thailand': [ { city: 'Bangkok', iata: 'BKK' }, { city: 'Phuket', iata: 'HKT' }, { city: 'Chiang Mai', iata: 'CNX' }, { city: 'Krabi', iata: 'KBV' } ]
};

const state = { raw: [], filtered: [], chart: null };

function populateCities(){
  const c = document.getElementById('countrySelect').value;
  const citySel = document.getElementById('citySelect');
  citySel.innerHTML = '';
  (COUNTRY_CITIES[c]||[]).forEach(x=>{
    const opt = document.createElement('option');
    opt.value = x.iata; opt.textContent = `${x.city} (${x.iata})`;
    citySel.appendChild(opt);
  });
}

async function loadData(){
  try{
    const res = await fetch('data/sample_data.json', {cache:'no-store'});
    state.raw = await res.json();
  }catch(e){ state.raw = []; }
  document.getElementById('lastLoaded').textContent = new Date().toLocaleString('nl-NL');
}

document.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('countrySelect').addEventListener('change', populateCities);
  populateCities();
  await loadData();

  document.getElementById('filterForm').addEventListener('submit', (e)=>{ e.preventDefault(); runAnalysis(); });
  runAnalysis();
});

function runAnalysis(){
  const startDate = document.getElementById('startDate').value;
  const tripLength = parseInt(document.getElementById('tripLength').value, 10);
  const useAMS = document.getElementById('useAMS').checked;
  const useEIN = document.getElementById('useEIN').checked;
  const maxStops = parseInt(document.getElementById('maxStops').value, 10);
  const maxLayover = parseInt(document.getElementById('maxLayover').value, 10);
  const exclude = (document.getElementById('excludeAirlines').value||'').split(',').map(s=>s.trim().toLowerCase()).filter(Boolean);
  const dest = document.getElementById('citySelect').value;

  const start = new Date(startDate);
  const endWindow = new Date('2026-08-26');

  let rows = state.raw.filter(r => r.destination_iata === dest);
  rows = rows.filter(r => (useAMS && r.origin==='AMS') || (useEIN && r.origin==='EIN'));
  rows = rows.filter(r => {
    const out = new Date(r.outbound_date);
    if (out < start || out > endWindow) return false;
    const diff = r.trip_length_days - tripLength; return Math.abs(diff) <= 2;
  });
  rows = rows.filter(r => (maxStops===3?true:r.stops<=maxStops) && r.max_layover_hours <= maxLayover);
  if (exclude.length){ rows = rows.filter(r => !exclude.includes((r.airline||'').toLowerCase())); }

  state.filtered = rows;
  buildBuyTimingChart(rows);
  buildAirlineTable(rows);
  buildItineraryTable(rows);

  const origin = (document.getElementById('useAMS').checked ? 'AMS' : (document.getElementById('useEIN').checked ? 'EIN' : 'AMS'));
  buildCalendarChart(origin, dest);
}

function groupBy(arr, key){
  return arr.reduce((acc,cur)=>{ (acc[cur[key]] = acc[cur[key]]||[]).push(cur); return acc; },{});
}
function avg(a){ return a.length? a.reduce((x,y)=>x+y,0)/a.length : 0; }

function buildBuyTimingChart(rows){
  const byDays = groupBy(rows, 'days_before_departure');
  const labels = Object.keys(byDays).map(n=>parseInt(n,10)).sort((a,b)=>a-b);
  const prices = labels.map(d => Math.round(avg(byDays[d].map(x=>x.price_eur))));
  const ctx = document.getElementById('buyTimingChart');
  if (window._buyChart) window._buyChart.destroy();
  window._buyChart = new Chart(ctx, { type:'line', data:{ labels, datasets:[{ label:'Gemiddelde laagste prijs (€)', data:prices, borderColor:'#5db2ff', backgroundColor:'rgba(93,178,255,.18)', tension:.25, pointRadius:0 }] }, options:{ scales:{ x:{ title:{display:true,text:'Dagen vóór vertrek'}}, y:{ title:{display:true,text:'Prijs (€)'}} }, plugins:{ legend:{display:false } } } });
}

function buildAirlineTable(rows){
  const body = document.querySelector('#airlineTable tbody'); body.innerHTML = '';
  const groups = groupBy(rows, 'airline');
  const items = Object.entries(groups).map(([airline, arr])=>({ airline, price: Math.round(avg(arr.map(x=>x.price_eur))), stops: avg(arr.map(x=>x.stops)).toFixed(1), layover: avg(arr.map(x=>x.max_layover_hours)).toFixed(1) })).sort((a,b)=>a.price-b.price);
  for (const it of items){ const tr = document.createElement('tr'); tr.innerHTML = `<td>${it.airline}</td><td>€ ${it.price}</td><td>${it.stops}</td><td>${it.layover}</td>`; body.appendChild(tr); }
}

function buildItineraryTable(rows){
  const body = document.querySelector('#itineraryTable tbody'); body.innerHTML = '';
  const byDate = groupBy(rows, 'outbound_date');
  const best = Object.values(byDate).map(arr => arr.sort((a,b)=>a.price_eur-b.price_eur)[0]).sort((a,b)=> new Date(a.outbound_date) - new Date(b.outbound_date));
  for (const r of best){ const tr = document.createElement('tr'); tr.innerHTML = `<td>${r.outbound_date} → ${r.return_date}</td><td>${r.origin} → ${r.destination_iata}</td><td>${r.airline||''}</td><td>${r.stops}</td><td>${r.max_layover_hours}</td><td>€ ${r.price_eur}</td>`; body.appendChild(tr); }
}

async function buildCalendarChart(origin, dest){
  try{
    const res = await fetch('data/monthly_lowest.json', {cache:'no-store'});
    const all = await res.json();
    const key = `${origin}-${dest}`;
    const months = ["Jan","Feb","Mrt","Apr","Mei","Jun","Jul","Aug","Sep","Okt","Nov","Dec"];
    const labels = months.flatMap(m => [m+"‑W1", m+"‑W2", m+"‑W3", m+"‑W4"]);
    const nowY = '2026', prevY = '2025';

    const getSeries = (y)=> months.flatMap((_,i)=> (all?.[key]?.[y]?.[String(i+1).padStart(2,'0')] || [null,null,null,null]));
    const sNow  = getSeries(nowY);
    const sPrev = (all?.[key]?.[prevY]) ? getSeries(prevY) : null;

    const ctx = document.getElementById('calendarChart');
    if (window._calChart) window._calChart.destroy();
    const datasets = [ { label:`${key} – ${nowY}`, data:sNow, borderColor:'#4ad395', backgroundColor:'rgba(74,211,149,.18)', tension:.25, pointRadius:0 } ];
    if (sPrev) datasets.push({ label:`${key} – ${prevY}`, data:sPrev, borderColor:'#5db2ff', backgroundColor:'rgba(93,178,255,.12)', tension:.25, pointRadius:0 });

    window._calChart = new Chart(ctx, { type:'line', data:{ labels, datasets }, options:{ scales:{ y:{ title:{display:true, text:'Prijs (€)'} } }, plugins:{ legend:{display:true} } } });
  }catch(e){ /* ignore */ }
}
