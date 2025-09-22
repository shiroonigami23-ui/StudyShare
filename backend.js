const express = require('express');
const multer = require('multer');
const cors = require('cors');
// Removed: const { Pool } = require('pg');

const app = express();
const PORT = process.env.PORT || 3000;

// Removed PostgreSQL pool setup for Aiven
// const pool = new Pool({...});

// Enable CORS and JSON parsing middleware
app.use(cors());
app.use(express.json());

// In-memory storage as fallback for users, comments, votes
let users = [];
let comments = [];
let votes = [];

// Admin password for frontend auth logic
const ADMINPASSWORD = 'Shiro';

// Allowed file types config
const allowedTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png',
];
const maxFileSize = 10 * 1024 * 1024; // 10 MB

// Multer setup for in-memory storage
const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: maxFileSize },
  fileFilter: (req, file, cb) => {
    cb(null, allowedTypes.includes(file.mimetype));
  },
});

function genId() {
  return Math.random().toString(36).substr(2, 9);
}

// --- AUTH LOGIN ---
app.post('/login', (req, res) => {
  const { name, password, isAnonymous } = req.body;
  if (isAnonymous) {
    const user = {
      id: genId(),
      name: `Anonymous${genId()}`,
      isAdmin: false,
      isAnonymous: true,
    };
    users.push(user);
    return res.json(user);
  }
  if (!name) return res.status(400).json({ error: 'Name required' });
  const isAdmin = name.toLowerCase() === 'admin' && password === ADMINPASSWORD;
  const user = {
    id: genId(),
    name,
    isAdmin,
    isAnonymous: false,
  };
  users.push(user);
  res.json(user);
});

// --- FILE UPLOAD ---
app.post('/upload', upload.single('file'), async (req, res) => {
  const { uploaderId, uploaderName, isAnonymous } = req.body;
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  if (!uploaderId && !isAnonymous && !uploaderName)
    return res.status(400).json({ error: 'Uploader info required' });

  // Database insert disabled - use in-memory or mock success response
  /*
  try {
    await pool.query(
      'INSERT INTO files (originalName, mimeType, fileSize, uploaderId, uploaderName, isApproved, upvotes, createdAt) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())',
      [
        req.file.originalname,
        req.file.mimetype,
        req.file.size,
        uploaderId,
        isAnonymous ? `Anonymous${genId()}` : uploaderName,
        false,
        0,
      ]
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock successful file upload response
  res.json({ success: true });
});

// --- ADMIN FILE ACTIONS ---
function getAdminByIdAndPassword(id, password) {
  return users.find((u) => u.id === id && u.isAdmin && password === ADMINPASSWORD);
}

app.post('/admin/approve', async (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });

  // DB update disabled
  /*
  try {
    await pool.query('UPDATE files SET isApproved = TRUE WHERE id = $1', [fileId]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock response
  res.json({ success: true });
});

app.post('/admin/reject', async (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });

  // DB delete disabled
  /*
  try {
    await pool.query('DELETE FROM files WHERE id = $1', [fileId]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock response
  res.json({ success: true });
});

// --- USER FILE ACTIONS ---

app.get('/download/:fileId/:userId', async (req, res) => {
  const { fileId, userId } = req.params;
  const user = users.find((u) => u.id === userId);

  // DB SELECT disabled - mock file and approval check
  /*
  try {
    const rows = await pool.query('SELECT * FROM files WHERE id = $1', [fileId]);
    let file = rows[0];
    if (!file) return res.status(404).json({ error: 'File not found' });
    if (!file.isApproved && (!user || !user.isAdmin))
      return res.status(403).json({ error: 'File not approved' });
    res.json({ success: true, file });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock response
  if (!user) return res.status(403).json({ error: 'User not found for download' });
  res.json({ success: true, file: { id: fileId, originalName: 'mockfile.pdf', isApproved: true } });
});

app.post('/upvote', async (req, res) => {
  const { fileId, userId } = req.body;

  // DB update disabled
  /*
  try {
    await pool.query('UPDATE files SET upvotes = upvotes + 1 WHERE id = $1', [fileId]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock upvote response
  res.json({ success: true });
});

app.get('/files/:userId', async (req, res) => {
  const user = users.find((u) => u.id === req.params.userId);

  // DB select disabled
  /*
  try {
    let result;
    if (user && user.isAdmin) {
      result = await pool.query('SELECT * FROM files');
    } else {
      result = await pool.query('SELECT * FROM files WHERE isApproved = TRUE');
    }
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock file list response
  if (user && user.isAdmin) {
    res.json([{ id: 'file1', originalName: 'AdminFile.pdf', isApproved: true }]);
  } else {
    res.json([{ id: 'file1', originalName: 'PublicFile.pdf', isApproved: true }]);
  }
});

// --- COMMENTS ---
app.post('/comment', (req, res) => {
  const { text, authorName, authorId } = req.body;
  if (!text || !authorName) return res.status(400).json({ error: 'Comment or name required' });
  const comment = { id: genId(), text, authorName, authorId: authorId || null, createdAt: new Date() };
  comments.push(comment);
  res.json({ success: true, comment });
});

app.get('/comments', (req, res) => {
  res.json(comments);
});

// --- ADMIN DASHBOARD ---
app.get('/admin/stats/:adminId/:adminPassword', (req, res) => {
  const { adminId, adminPassword } = req.params;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });

  // DB queries disabled, sending mock stats
  /*
  try {
    const totalFilesRes = await pool.query('SELECT COUNT(*) as count FROM files');
    const approvedRes = await pool.query('SELECT COUNT(*) as count FROM files WHERE isApproved = TRUE');
    const pendingRes = await pool.query('SELECT COUNT(*) as count FROM files WHERE isApproved = FALSE');
    const upvotesRes = await pool.query('SELECT SUM(upvotes) as sum FROM files');

    res.json({
      totalFiles: totalFilesRes.rows[0].count,
      approved: approvedRes.rows[0].count,
      pending: pendingRes.rows[0].count,
      totalUpvotes: upvotesRes.rows[0].sum || 0,
    });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
  */

  // Mock stats response
  res.json({
    totalFiles: 10,
    approved: 7,
    pending: 3,
    totalUpvotes: 15,
  });
});

app.listen(PORT, () => {
  console.log(`ShareLit backend running on port ${PORT}`);
});
