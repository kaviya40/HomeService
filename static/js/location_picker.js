(function () {
  const $ = id => document.getElementById(id);
  const mapEl = $('map');
  if (!mapEl || typeof L === 'undefined') return;

  const map = L.map('map').setView([10.9, 78.4], 7);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {attribution: '© OpenStreetMap'}).addTo(map);
  let marker = null;

  function setPos(lat, lng, zoom) {
    $('lat').value = lat.toFixed(6);
    $('lng').value = lng.toFixed(6);
    if (!marker) {
      marker = L.marker([lat, lng], {draggable: true}).addTo(map);
      marker.on('dragend', e => { const p = e.target.getLatLng(); setPos(p.lat, p.lng); });
    } else {
      marker.setLatLng([lat, lng]);
    }
    if (zoom) map.setView([lat, lng], zoom);
  }
  map.on('click', e => setPos(e.latlng.lat, e.latlng.lng));

  async function geocode(q) {
    const url = 'https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=in&q='
                + encodeURIComponent(q);
    const r = await fetch(url, {headers: {'Accept': 'application/json'}});
    const d = await r.json();
    return d.length ? d[0] : null;
  }

  async function locate() {
    const state = $('state').value.trim(), district = $('district').value.trim(),
          area = $('area').value.trim(), st = $('loc-status');
    if (!district || !area) { st.textContent = 'Please enter both district and area.'; return; }
    st.textContent = 'Searching location...';
    try {
      let res = await geocode(`${area}, ${district}, ${state}`);
      let zoom = 14, note = '';
      if (!res) res = await geocode(`${area}, ${state}`);
      if (!res) {
        res = await geocode(`${district}, ${state}`); zoom = 10;
        note = ' (Area not found, showing the district. Drag the marker to adjust.)';
      }
      if (!res) { st.textContent = 'Location not found. Check the spelling or click on the map.'; return; }
      setPos(parseFloat(res.lat), parseFloat(res.lon), zoom);
      st.textContent = '✅ ' + res.display_name + note;
    } catch (e) {
      st.textContent = 'Could not reach the location service. Click on the map to set the location.';
    }
  }

  $('locate-btn').addEventListener('click', locate);
  ['area', 'district'].forEach(id => $(id).addEventListener('change', () => {
    if ($('area').value.trim() && $('district').value.trim()) locate();
  }));

  // existing location (profile edit page)
  if ($('lat').value && $('lng').value) {
    setPos(parseFloat($('lat').value), parseFloat($('lng').value), 14);
  }

  $('pform').addEventListener('submit', async e => {
    if (!$('lat').value) {
      e.preventDefault();
      await locate();
      if ($('lat').value) e.target.submit();
    }
  });
})();
