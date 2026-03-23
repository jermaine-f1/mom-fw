import { list, put } from '@vercel/blob';

function parseBody(req) {
  return new Promise((resolve, reject) => {
    if (req.body) return resolve(req.body);
    let data = '';
    req.on('data', chunk => { data += chunk; });
    req.on('end', () => {
      try { resolve(JSON.parse(data)); }
      catch (e) { reject(new Error('Invalid JSON body')); }
    });
    req.on('error', reject);
  });
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  try {
    if (req.method === 'GET') {
      const { blobs } = await list({ prefix: 'portfolios/' });
      const portfolios = blobs.map(b => ({
        name: b.pathname.replace('portfolios/', '').replace('.json', ''),
        url: b.url,
        uploadedAt: b.uploadedAt,
        size: b.size,
      }));
      return res.status(200).json(portfolios);
    }

    if (req.method === 'PUT') {
      const body = await parseBody(req);
      const { name, csvText, holdings } = body;
      if (!name || !holdings) {
        return res.status(400).json({ error: 'name and holdings are required' });
      }
      const data = JSON.stringify({ name, csvText, holdings, savedAt: new Date().toISOString() });
      const blob = await put(`portfolios/${name}.json`, data, {
        contentType: 'application/json',
        access: 'public',
        addRandomSuffix: false,
      });
      return res.status(200).json({ url: blob.url, name });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    console.error('Portfolio API error:', err);
    return res.status(500).json({ error: err.message });
  }
}
