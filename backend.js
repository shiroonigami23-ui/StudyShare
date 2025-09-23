const express = require('express');
const multer = require('multer');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 10000;

// Middleware
app.use(cors());
app.use(express.json());

// In-memory storage as fallback
let users = [];
let comments = [];
let votes = [];

const ADMINPASSWORD = 'Shiro';

const allowedTypes = [
  'application/pdf',
  'application/epub+zip',
  'audio/mpeg',
  'image/jpeg',
  'image/jpg',
  'image/png',
];
const maxFileSize = 10 * 1024 * 1024;

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

// Auth login
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

// File upload
app.post('/upload', upload.single('file'), (req, res) => {
  const { uploaderId, uploaderName, isAnonymous } = req.body;
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });
  if (!uploaderId && !isAnonymous && !uploaderName)
    return res.status(400).json({ error: 'Uploader info required' });

  // Mock success response
  res.json({ success: true });
});

// Admin file actions helpers
function getAdminByIdAndPassword(id, password) {
  return users.find((u) => u.id === id && u.isAdmin && password === ADMINPASSWORD);
}

app.post('/admin/approve', (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });
  res.json({ success: true });
});

app.post('/admin/reject', (req, res) => {
  const { fileId, adminId, adminPassword } = req.body;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });
  res.json({ success: true });
});

// User file actions
app.get('/download/:fileId/:userId', (req, res) => {
  const { userId } = req.params;
  const user = users.find((u) => u.id === userId);
  if (!user) return res.status(403).json({ error: 'User not found' });
  res.json({ success: true, file: { id: req.params.fileId, originalName: 'mockfile.pdf', isApproved: true } });
});

app.post('/upvote', (req, res) => {
  res.json({ success: true });
});

app.get('/files/:userId', (req, res) => {
  const user = users.find((u) => u.id === req.params.userId);
  if (user && user.isAdmin) {
    res.json([{ id: 'file1', originalName: 'AdminFile.pdf', isApproved: true }]);
  } else {
    res.json([{ id: 'file1', originalName: 'PublicFile.pdf', isApproved: true }]);
  }
});

// Comments
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

// Admin dashboard stats
app.get('/admin/stats/:adminId/:adminPassword', (req, res) => {
  const { adminId, adminPassword } = req.params;
  if (!getAdminByIdAndPassword(adminId, adminPassword))
    return res.status(403).json({ error: 'Admin only or wrong password' });
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
