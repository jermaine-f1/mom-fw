import { list, del } from '@vercel/blob';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const { name } = req.query;
  if (!name) return res.status(400).json({ error: 'name is required' });

  try {
    const { blobs } = await list({ prefix: `portfolios/${name}.json` });
    const match = blobs.find(b => b.pathname === `portfolios/${name}.json`);

    if (req.method === 'GET') {
      if (!match) return res.status(404).json({ error: 'Portfolio not found' });
      const response = await fetch(match.downloadUrl);
      const data = await response.json();
      return res.status(200).json(data);
    }

    if (req.method === 'DELETE') {
      if (!match) return res.status(404).json({ error: 'Portfolio not found' });
      await del(match.url);
      return res.status(200).json({ deleted: name });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    console.error('Portfolio detail API error:', err);
    return res.status(500).json({ error: err.message });
  }
}
