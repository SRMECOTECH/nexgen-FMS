import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export interface MapPoint { lat: number; lng: number; mv?: boolean; }
export interface MapStop { lat: number; lng: number; minutes: number; near?: string | null; }
export interface MapGeofence { lat: number; lng: number; radius_m: number; name: string; type?: string; address?: string | null; visits?: number; }

interface Props {
  points: MapPoint[];
  stops?: MapStop[];
  geofences?: MapGeofence[];
  height?: number;
}

/**
 * Vanilla-Leaflet map on OpenStreetMap tiles (no react-leaflet — avoids the
 * React-19 peer-dep issue). Draws the route split into moving (amber) / stopped
 * (grey) polylines, red stop circles sized by dwell time, and start/end pins.
 */
export default function LeafletMap({ points, stops = [], geofences = [], height = 460 }: Props) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);

  // create the map once
  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const map = L.map(elRef.current, { zoomControl: true, attributionControl: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    map.setView([22.5, 84], 7);
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // redraw when data changes
  useEffect(() => {
    const map = mapRef.current, layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const valid = points.filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lng) && (p.lat !== 0 || p.lng !== 0));
    if (valid.length === 0) return;

    // split into runs of constant motion so colour reflects moving vs stopped
    let run: L.LatLngExpression[] = [[valid[0].lat, valid[0].lng]];
    let runMoving = !!valid[0].mv;
    const flush = (moving: boolean) => {
      if (run.length > 1) {
        L.polyline(run, {
          color: moving ? '#ff9500' : '#8a8f98',
          weight: moving ? 3.5 : 2,
          opacity: moving ? 0.95 : 0.5,
        }).addTo(layer);
      }
    };
    for (let i = 1; i < valid.length; i++) {
      const p = valid[i];
      if (!!p.mv === runMoving) {
        run.push([p.lat, p.lng]);
      } else {
        run.push([p.lat, p.lng]);   // bridge the boundary so the line is continuous
        flush(runMoving);
        run = [[p.lat, p.lng]];
        runMoving = !!p.mv;
      }
    }
    flush(runMoving);

    // geofences (translucent zones, drawn under the stop pins)
    for (const gf of geofences) {
      if (!Number.isFinite(gf.lat) || !Number.isFinite(gf.lng)) continue;
      L.circle([gf.lat, gf.lng], {
        radius: Math.max(gf.radius_m || 80, 120),
        color: '#38bdf8', fillColor: '#38bdf8', fillOpacity: 0.1, weight: 1, dashArray: '4',
      }).bindPopup(
        `<b>${gf.name}</b><br/>${gf.type ?? ''}${gf.visits ? ` · ${gf.visits} visit(s)` : ''}` +
        `${gf.address ? `<br/><span style="color:#888">${gf.address}</span>` : ''}`
      ).addTo(layer);
    }

    // stop circles (red, sized by dwell minutes)
    for (const s of stops) {
      if (!Number.isFinite(s.lat) || !Number.isFinite(s.lng)) continue;
      L.circleMarker([s.lat, s.lng], {
        radius: Math.min(5 + s.minutes / 120, 16),
        color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.45, weight: 1,
      }).bindPopup(`<b>${s.near ?? 'Stop'}</b><br/>${Math.round(s.minutes)} min`).addTo(layer);
    }

    // start / end pins
    const start = valid[0], end = valid[valid.length - 1];
    L.circleMarker([start.lat, start.lng], { radius: 7, color: '#22c55e', fillColor: '#22c55e', fillOpacity: 1, weight: 2 })
      .bindPopup('Start').addTo(layer);
    L.circleMarker([end.lat, end.lng], { radius: 7, color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 1, weight: 2 })
      .bindPopup('Latest').addTo(layer);

    const bounds = L.latLngBounds(valid.map(p => [p.lat, p.lng] as L.LatLngExpression));
    map.fitBounds(bounds, { padding: [24, 24] });
    setTimeout(() => map.invalidateSize(), 100); // ensure tiles paint after layout
  }, [points, stops, geofences]);

  return <div ref={elRef} style={{ height, width: '100%', borderRadius: 8, overflow: 'hidden', background: '#1a1a1a' }} />;
}
