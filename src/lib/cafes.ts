// src/lib/cafes.ts
import fs from 'node:fs';

const SHEET_ID = '10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI';
const urlSheet = (gid: string) =>
  `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&gid=${gid}`;

const GIDS: Record<string, string> = {
  'Mar del Plata': '0', 'CABA y Gran Buenos Aires': '1296176686', 'La Plata': '208452991', 'Córdoba': '1250014567',
  'Santa Fe': '1691979590', 'Mendoza': '2031963266', 'Interior de BS AS': '1634818534', 'Neuquén y Río Negro': '155647820',
  'Salta y Jujuy': '1993653328', 'Chubut, Santa Cruz y Tierra del Fuego': '1650814085', 'San Juan, San Luis, La Rioja y La Pampa': '1228328818',
  'Corrientes, Misiones, Entre Rios, Formosa y Chaco': '1097354687', 'Catamarca, Tucuman y Santiago del Estero': '1483010757'
};
const TOSTADORES_GID = '1590442133';
const RANKING_GIDS = { arg: '35250567', sud: '1698883223', mun: '629924037' };
const PROVINCIAS_ARGENTINA = 24;

type Fila = Record<string, string>;

const normHeader = (h: string) => h.trim().toUpperCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const normTexto = (s: string) => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();

function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cur = '';
  let enComillas = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (enComillas) {
      if (ch === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else enComillas = false; }
      else cur += ch;
    } else if (ch === '"') enComillas = true;
    else if (ch === ',') { row.push(cur); cur = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cur); cur = '';
      if (row.some(c => c.trim() !== '')) rows.push(row);
      row = [];
    } else cur += ch;
  }
  row.push(cur);
  if (row.some(c => c.trim() !== '')) rows.push(row);
  return rows;
}

async function leerHoja(gid: string, intentos = 3): Promise<Fila[]> {
  let ultimoError: unknown;
  for (let i = 0; i < intentos; i++) {
    try {
      const res = await fetch(urlSheet(gid));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const filas = parseCSV(await res.text());
      if (filas.length < 2) return [];
      const headers = filas[0].map(normHeader);
      return filas.slice(1).map(r => {
        const o: Fila = {};
        headers.forEach((h, idx) => { if (h) o[h] = (r[idx] ?? '').trim(); });
        return o;
      });
    } catch (e) {
      ultimoError = e;
      await new Promise(r => setTimeout(r, 800 * (i + 1)));
    }
  }
  throw new Error(`No se pudo leer la hoja gid=${gid}: ${ultimoError}`);
}

function numero(v?: string): number | null {
  const n = parseFloat((v ?? '').toString().replace(',', '.'));
  return isNaN(n) ? null : n;
}

function enlace(url?: string): string {
  const u = (url ?? '').trim();
  if (!u || u === '#') return '';
  if (u.startsWith('@')) return 'https://www.instagram.com/' + u.slice(1);
  return /^https?:\/\//i.test(u) ? u : 'https://' + u;
}

function slugify(s: string): string {
  return s.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

// ---------- Locales ----------
const hojasCafes = await Promise.all(
  Object.entries(GIDS).map(async ([ciudad, gid]) => ({ ciudad, filas: await leerHoja(gid) }))
);

const descartados: string[] = [];
const cafesRaw: any[] = [];

for (const { ciudad, filas } of hojasCafes) {
  for (const f of filas) {
    if (!f.CAFE) continue;
    const lat = numero(f.LAT || f.LATITUD);
    const lon = numero(f.LONG || f.LNG || f.LONGITUD);
    if (lat === null || lon === null) continue;
    if (lat < -56 || lat > -21 || lon < -74 || lon > -53) { descartados.push(`${f.CAFE} (${lat}, ${lon})`); continue; }
    cafesRaw.push({
      nombre: f.CAFE.trim(),
      ciudad,
      ciudadReal: (f.CUIDAD || f.CIUDAD || f.LOCALIDAD || '').trim(),
      zona: f.ZONA || f.BARRIO || '',
      ubicacion: f.UBICACION || '-',
      instagram: enlace(f.INSTAGRAM),
      lat, lon
    });
  }
}

if (cafesRaw.length === 0) throw new Error('[cafes] No se cargó ningún local: se cancela el build.');

cafesRaw.sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));

// ---------- Geocodificación inversa (Georef) con caché ----------
const GEO_PATH = 'src/data/geo-cache.json';
const geoCache: Record<string, string> = fs.existsSync(GEO_PATH)
  ? JSON.parse(fs.readFileSync(GEO_PATH, 'utf8'))
  : {};
const claveGeo = (c: any) => `${c.lat},${c.lon}`;

const pendientes = cafesRaw.filter(c => !(claveGeo(c) in geoCache));
for (let i = 0; i < pendientes.length; i += 200) {
  const lote = pendientes.slice(i, i + 200);
  try {
    const res = await fetch('https://apis.datos.gob.ar/georef/api/v2.0/ubicacion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ubicaciones: lote.map(c => ({ lat: c.lat, lon: c.lon, aplanar: true })) })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { resultados } = await res.json();
    resultados.forEach((r: any, idx: number) => {
      const u = r.ubicacion;
      if (!u?.provincia_nombre) return;
      const nombre = u.provincia_id === '02' ? 'CABA' : (u.municipio_nombre || u.departamento_nombre);
      if (nombre) geoCache[claveGeo(lote[idx])] = `${u.provincia_nombre}|${nombre}`;
    });
  } catch (e) {
    console.warn('[cafes] Georef falló en un lote:', e);
  }
}
try {
  fs.mkdirSync('src/data', { recursive: true });
  fs.writeFileSync(GEO_PATH, JSON.stringify(geoCache));
} catch (e) {
  console.warn('[cafes] No se pudo guardar geo-cache:', e);
}

// ---------- Diccionarios ----------
export const regiones = [...new Set(cafesRaw.map(c => c.ciudad))].sort((a, b) => a.localeCompare(b, 'es'));
export const zonasDict = [...new Set(cafesRaw.map(c => c.zona).filter(z => z && z !== '-' && z !== 'Sin Zona'))].sort((a, b) => a.localeCompare(b, 'es'));
export const ciudadesRealesDict = [...new Set(cafesRaw.map(c => c.ciudadReal).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'es'));

// ---------- Tipos ----------
export interface CafeCompact {
  id: number; n: string; r: number; z: number; c: number; u: string; s: string; a: number; o: number; slug: string;
}
export interface CafeExpanded {
  id: number; nombre: string; ubicacion: string; instagram: string; lat: number; lon: number; ciudad: string; zona: string; ciudadReal: string; slug: string;
}
export interface Tostador {
  nombre: string; ig: string; tienda: string; ciudad: string; foto: string;
}
export interface RankingItem {
  rank: number; nombre: string; ubicacion: string; ig: string; lugar: string; ciudad: string; pais: string; provincia: string; lat: number; lon: number;
}

const slugUsados = new Map<string, number>();
export const cafesCompact: CafeCompact[] = cafesRaw.map((c, id) => {
  let slug = slugify(c.nombre + '-' + c.ciudad);
  const count = (slugUsados.get(slug) || 0) + 1;
  slugUsados.set(slug, count);
  if (count > 1) slug = `${slug}-${id}`;
  return {
    id, n: c.nombre, r: regiones.indexOf(c.ciudad), z: zonasDict.indexOf(c.zona), c: ciudadesRealesDict.indexOf(c.ciudadReal),
    u: c.ubicacion, s: c.instagram, a: +c.lat.toFixed(5), o: +c.lon.toFixed(5), slug
  };
});

export const cafesExpanded: CafeExpanded[] = cafesCompact.map(c => ({
  id: c.id, nombre: c.n, ubicacion: c.u, instagram: c.s, lat: c.a, lon: c.o,
  ciudad: regiones[c.r], zona: c.z >= 0 ? zonasDict[c.z] : '', ciudadReal: c.c >= 0 ? ciudadesRealesDict[c.c] : '', slug: c.slug
}));

const tostadoresRaw = await leerHoja(TOSTADORES_GID);
export const tostadores: Tostador[] = tostadoresRaw
  .map(f => ({
    nombre: f.TOSTADOR || f.TOSTADORES || f.NOMBRE || '', ig: enlace(f.INSTAGRAM || f.IG),
    tienda: enlace(f['TIENDA ONLINE'] || f.TIENDA || f.LINK), ciudad: (f.CIUDAD || 'Varias').trim(),
    foto: enlace(f.IMAGENES || f.IMAGEN || f.FOTO || f.FOTOS)
  })).filter(t => t.nombre);

function parseRanking(filas: Fila[], tipo: 'arg' | 'sud' | 'mun'): RankingItem[] {
  let rankActual = 999;
  return filas.map(f => {
    const rawRank = (f.RANKING || f.RANK || '').trim();
    if (rawRank !== '') rankActual = parseInt(rawRank, 10);
    const lat = numero(f.LAT || f.LATITUD);
    const lon = numero(f.LONG || f.LNG || f.LONGITUD);
    const ciudad = (f.CUIDAD || f.CIUDAD || f.CITY || 'Desconocida').trim();
    const pais = (f.PAIS || f.COUNTRY || 'Desconocido').trim();
    const provincia = (f.PROVINCIA || f.PROVINCE || f.REGION || 'Desconocida').trim();
    return {
      rank: rankActual, nombre: (f.CAFETERIA || f.CAFE || '').trim(), ubicacion: f.UBICACION || f.DIRECCION || '-',
      ig: enlace(f.IG || f.INSTAGRAM), lugar: tipo === 'arg' ? ciudad : pais, ciudad, pais, provincia,
      lat: lat ?? 0, lon: lon ?? 0
    } as RankingItem;
  }).filter(r => r.nombre && r.lat !== null && r.lon !== null && (r.lat !== 0 || r.lon !== 0));
}

const [rankArg, rankSud, rankMun] = await Promise.all([
  leerHoja(RANKING_GIDS.arg), leerHoja(RANKING_GIDS.sud), leerHoja(RANKING_GIDS.mun)
]);
export const ranking = { arg: parseRanking(rankArg, 'arg'), sud: parseRanking(rankSud, 'sud'), mun: parseRanking(rankMun, 'mun') };

// ---------- MÉTRICAS CORREGIDAS ----------
export const meta = {
  cafes: cafesCompact.length,
  tostadores: tostadores.length,
  provincias: PROVINCIAS_ARGENTINA,
  // Contamos las ciudades reales. Si por alguna razón falla, usamos las regiones (13), 
  // pero NUNCA las zonas, para no mezclar barrios con ciudades.
  ciudades: ciudadesRealesDict.length || regiones.length
};

export function cafesCercanos(cafe: CafeExpanded, limit = 6): CafeExpanded[] {
  return cafesExpanded
    .filter(c => c.id !== cafe.id && ((c.ciudadReal && c.ciudadReal === cafe.ciudadReal) || (c.ciudad === cafe.ciudad)))
    .slice(0, limit);
}
