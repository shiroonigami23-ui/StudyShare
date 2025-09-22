const express = require('express');
const multer = require('multer');
const cors = require('cors');
const mariadb = require('mariadb');
const app = express();
const PORT = process.env.PORT || 3000;

// --- MariaDB database setup ---
let pool = null;
let isDB = false;

// Try to create pool, fallback to RAM if failed
(async () => {
  try {
    pool = mariadb.createPool({
      host: 'localhost',
      user: 'shareuser',
      password: 'Shiro',
      database: 'sharelit'
    });
    // Quick test query, will throw if DB down
    await pool.query('SELECT 1');
    isDB = true;
    console.log('MariaDB detected. Using database for storage!');
  } catch (err) {
    pool = null;
    isDB = false;
    console.log('MariaDB not detected. Using in-memory storage!');
  }
})();

app.use(cors());
app.use(express.json());

// In-memory storage as fallback
let users = [];
let files = [];
let comments = [];
let votes = {};

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

  if (isDB) {
    try {
      const conn = await pool.getConnection();
      await conn.query(
        'INSERT INTO files (originalName, mimeType, fileSize, uploaderId, uploaderName, isApproved, upvotes, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?, NOW())',
        [req.file.originalname, req.file.mimetype, req.file.size, uploaderId, isAnonymous ? `Anonymous_${genId()}` : uploaderName, false, 0]
      );
      conn.release();
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    let f = {
      id: genId(),
      originalName: req.file.originalname,
      mimeType: req.file.mimetype,
      fileSize: req.file.size,
      uploaderId,
      uploaderName: isAnonymous ? `Anonymous_${genId()}` : uploaderName,
      isApproved: false,
      upvotes: 0,
      buffer: req.file.buffer,
      createdAt: new Date()
    };
    files.push(f);
    res.json({ success: true, file: f });
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

  if (isDB) {
    try {
      const conn = await pool.getConnection();
      await conn.query('UPDATE files SET isApproved=1 WHERE id=?', [fileId]);
      conn.release();
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    let file = files.find(f => f.id === fileId);
    if (!file) return res.status(404).json({ error: 'File not found' });
    file.isApproved = true;
    res.json({ success: true, file });
  }
});

// Reject file
app.post('/admin/reject', async (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  if (isDB) {
    try {
      const conn = await pool.getConnection();
      await conn.query('DELETE FROM files WHERE id=?', [fileId]);
      conn.release();
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    files = files.filter(f => f.id !== fileId);
    res.json({ success: true });
  }
});

// --- USER FILE ACTIONS ---

// Download file endpoint, only approved files or admins can download
app.get('/download/:fileId/:userId', async (req, res) => {
  const { fileId, userId } = req.params;
  const user = users.find(u => u.id === userId);

  if (isDB) {
    try {
      const conn = await pool.getConnection();
      const filesRes = await conn.query('SELECT * FROM files WHERE id=?', [fileId]);
      let file = filesRes[0];
      conn.release();
      if (!file) return res.status(404).json({ error: 'File not found' });
      if (!file.isApproved && (!user || !user.isAdmin)) {
        return res.status(403).json({ error: 'File not approved' });
      }
      // Placeholder: actual file content needs to be saved on disk or as BLOB for real download
      res.json({ success: true, file });
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    const file = files.find(f => f.id === fileId);
    if (!file) return res.status(404).json({ error: 'File not found' });
    if (!file.isApproved && (!user || !user.isAdmin)) {
      return res.status(403).json({ error: 'File not approved' });
    }
    res.setHeader('Content-Disposition', `attachment; filename="${file.originalName}"`);
    res.setHeader('Content-Type', file.mimeType);
    res.send(file.buffer);
  }
});

// Upvote file endpoint
app.post('/upvote', async (req, res) => {
  const { fileId, userId } = req.body;

  if (isDB) {
    try {
      const conn = await pool.getConnection();
      await conn.query('UPDATE files SET upvotes = upvotes + 1 WHERE id=?', [fileId]);
      conn.release();
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    if (!votes[userId]) votes[userId] = {};
    if (votes[userId][fileId]) return res.status(400).json({ error: 'Already voted' });
    let file = files.find(f => f.id === fileId && f.isApproved);
    if (!file) return res.status(404).json({ error: 'File not found or not approved' });
    file.upvotes++;
    votes[userId][fileId] = true;
    res.json({ success: true, upvotes: file.upvotes });
  }
});

// Get all files, admins get all, users get only approved
app.get('/files/:userId', async (req, res) => {
  const user = users.find(u => u.id === req.params.userId);
  if (isDB) {
    try {
      const conn = await pool.getConnection();
      let filesRows;
      if (user && user.isAdmin) {
        filesRows = await conn.query('SELECT * FROM files');
      } else {
        filesRows = await conn.query('SELECT * FROM files WHERE isApproved=1');
      }
      conn.release();
      res.json(filesRows);
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    let result = user && user.isAdmin ? files : files.filter(f => f.isApproved);
    res.json(result);
  }
});

// --- COMMENTS ---
// Add comment endpoint
app.post('/comment', async (req, res) => {
  const { text, authorName, authorId } = req.body;
  if (!text || !authorName) return res.status(400).json({ error: 'Comment or name required' });

  if (isDB) {
    // (You need to create and use a "comments" table in MariaDB for persistence)
    res.json({ success: true }); // Placeholder
  } else {
    let comment = {
      id: genId(),
      text,
      authorName,
      authorId: authorId || null,
      createdAt: new Date()
    };
    comments.push(comment);
    res.json({ success: true, comment });
  }
});

// Get all comments endpoint
app.get('/comments', (req, res) => {
  // DB version omitted; add if you create a comments table in MariaDB
  res.json(comments);
});

// --- ADMIN DASHBOARD ---
app.get('/admin/stats/:adminId/:adminPassword', async (req, res) => {
  const { adminId, adminPassword } = req.params;
  if (!getAdminByIdAndPassword(adminId, adminPassword)) {
    return res.status(403).json({ error: 'Admin only or wrong password' });
  }

  if (isDB) {
    try {
      const conn = await pool.getConnection();
      const totalFiles = await conn.query('SELECT COUNT(*) as count FROM files');
      const approved = await conn.query('SELECT COUNT(*) as count FROM files WHERE isApproved=1');
      const pending = await conn.query('SELECT COUNT(*) as count FROM files WHERE isApproved=0');
      const upvotes = await conn.query('SELECT SUM(upvotes) as sum FROM files');
      conn.release();
      res.json({
        totalFiles: totalFiles[0].count,
        approved: approved[0].count,
        pending: pending[0].count,
        totalUpvotes: upvotes[0].sum || 0
      });
    } catch (err) {
      res.status(500).json({ error: 'DB error', details: err.toString() });
    }
  } else {
    let approved = files.filter(f => f.isApproved);
    let pending = files.filter(f => !f.isApproved);
    let totalUpvotes = files.reduce((total, f) => total + f.upvotes, 0);
    res.json({
      totalFiles: files.length,
      approved: approved.length,
      pending: pending.length,
      totalUpvotes
    });
  }
});

app.listen(PORT, () => {
  console.log(`ShareLit backend running on port ${PORT}`);
});
