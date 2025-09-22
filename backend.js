const express = require('express');
const multer = require('multer');
const cors = require('cors');
const { Pool } = require('pg');
const app = express();
const PORT = process.env.PORT || 3000;

// --- PostgreSQL pool setup for Aiven ---
const pool = new Pool({
  user: 'avnadmin',
  host: 'pg-1eb9e17f-elegance.f.aivencloud.com',
  database: 'defaultdb',
  password: 'AWS_FcMjS8qCRtOi.jNawug', // Be careful about sharing this!
  port: 25192,
  ssl: { rejectUnauthorized: false }
});

app.use(cors());
app.use(express.json());

// In-memory storage as fallback (for comments)
let users = [];
let comments = [];
let votes = {};

// Admin password from frontend (you can keep as-is for non-DB logic)
const ADMIN_PASSWORD = "Shiro";

const allowedTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png'
];
const maxFileSize = 10 * 1024 * 1024; // 10 MB

const storage = multer.memoryStorage();
const upload = multer({
  storage,
  limits: { fileSize: maxFileSize },
  fileFilter: (req, file, cb) => {
    cb(null, allowedTypes.includes(file.mimetype));
  }
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
      name: `Anonymous_${genId()}`,
      isAdmin: false,
      isAnonymous: true
    };
    users.push(user);
    return res.json(user);
  }

  if (!name) return res.status(400).json({ error: 'Name required' });
  const isAdmin = (name.toLowerCase() === 'admin' && password === ADMIN_PASSWORD);
  const user = {
    id: genId(),
    name,
    isAdmin,
    isAnonymous: false
  };
  users.push(user);
  res.json(user);
});

// --- FILE UPLOAD ---
app.post('/upload', upload.single('file'), async (req, res) => {
  const { uploaderId, uploaderName, isAnonymous } = req.body;
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

  if (!uploaderId || (!isAnonymous && !uploaderName)) {
    return res.status(400).json({ error: 'Uploader info required' });
  }

  try {
    await pool.query(
      'INSERT INTO files (originalName, mimeType, fileSize, uploaderId, uploaderName, isApproved, upvotes, createdAt) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())',
      [
        req.file.originalname,
        req.file.mimetype,
        req.file.size,
        uploaderId,
        isAnonymous ? `Anonymous_${genId()}` : uploaderName,
        false,
        0
      ]
    );
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

// --- ADMIN FILE ACTIONS ---
function getAdminByIdAndPassword(id, password) {
  return users.find(u => u.id === id && u.isAdmin && password === ADMIN_PASSWORD);
}

// Approve file
app.post('/admin/approve', async (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  try {
    await pool.query('UPDATE files SET isApproved=TRUE WHERE id=$1', [fileId]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

// Reject file
app.post('/admin/reject', async (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  try {
    await pool.query('DELETE FROM files WHERE id=$1', [fileId]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

// --- USER FILE ACTIONS ---
// Download file (metadata only - can be upgraded for real file download logic)
app.get('/download/:fileId/:userId', async (req, res) => {
  const { fileId, userId } = req.params;
  const user = users.find(u => u.id === userId);

  try {
    const { rows } = await pool.query('SELECT * FROM files WHERE id=$1', [fileId]);
    let file = rows[0];
    if (!file) return res.status(404).json({ error: 'File not found' });
    if (!file.isapproved && (!user || !user.isAdmin)) {
      return res.status(403).json({ error: 'File not approved' });
    }
    res.json({ success: true, file });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

// Upvote file endpoint
app.post('/upvote', async (req, res) => {
  const { fileId, userId } = req.body;

  try {
    await pool.query('UPDATE files SET upvotes = upvotes + 1 WHERE id=$1', [fileId]);
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

// Get all files, admins get all, users get only approved
app.get('/files/:userId', async (req, res) => {
  const user = users.find(u => u.id === req.params.userId);
  try {
    let result;
    if (user && user.isAdmin) {
      result = await pool.query('SELECT * FROM files');
    } else {
      result = await pool.query('SELECT * FROM files WHERE isApproved=TRUE');
    }
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

// --- COMMENTS ---
// Add comment endpoint
app.post('/comment', async (req, res) => {
  const { text, authorName, authorId } = req.body;
  if (!text || !authorName) return res.status(400).json({ error: 'Comment or name required' });

  let comment = {
    id: genId(),
    text,
    authorName,
    authorId: authorId || null,
    createdAt: new Date()
  };
  comments.push(comment);
  res.json({ success: true, comment });
});

// Get all comments endpoint (in-memory for demo)
app.get('/comments', (req, res) => {
  res.json(comments);
});

// --- ADMIN DASHBOARD ---
app.get('/admin/stats/:adminId/:adminPassword', async (req, res) => {
  const { adminId, adminPassword } = req.params;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  try {
    const totalFilesRes = await pool.query('SELECT COUNT(*) as count FROM files');
    const approvedRes = await pool.query('SELECT COUNT(*) as count FROM files WHERE isApproved=TRUE');
    const pendingRes = await pool.query('SELECT COUNT(*) as count FROM files WHERE isApproved=FALSE');
    const upvotesRes = await pool.query('SELECT SUM(upvotes) as sum FROM files');
    res.json({
      totalFiles: totalFilesRes.rows[0].count,
      approved: approvedRes.rows[0].count,
      pending: pendingRes.rows[0].count,
      totalUpvotes: upvotesRes.rows[0].sum || 0
    });
  } catch (err) {
    res.status(500).json({ error: 'DB error', details: err.toString() });
  }
});

app.listen(PORT, () => {
  console.log(`ShareLit backend running on port ${PORT}`);
});
